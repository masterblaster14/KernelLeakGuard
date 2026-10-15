//===- main.cpp - klg-analyze command line driver -------------------------===//
//
// Part of KernelLeakGuard.
//
//   klg-analyze module.bc -o candidates.json [--module-name NAME]
//               [--spec extra.json] [--no-escape] [--no-interproc]
//               [--no-corr] [--no-containers] [--naive]
//
//===----------------------------------------------------------------------===//
#include "Analyzer.h"

#include "llvm/IR/LLVMContext.h"
#include "llvm/IRReader/IRReader.h"
#include "llvm/Support/CommandLine.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/Path.h"
#include "llvm/Support/SourceMgr.h"
#include "llvm/Support/raw_ostream.h"

#include <chrono>

using namespace llvm;

static cl::opt<std::string> Input(cl::Positional, cl::desc("<module.bc|.ll>"),
                                  cl::Required);
static cl::opt<std::string> Output("o", cl::desc("Output JSON file"),
                                   cl::init("-"));
static cl::opt<std::string> ModuleName("module-name",
                                       cl::desc("Name used in reports"));
static cl::opt<std::string> SpecFile("spec",
                                     cl::desc("Additional API spec (JSON)"));
static cl::opt<bool> NoEscape("no-escape",
                              cl::desc("Disable ownership-transfer analysis"));
static cl::opt<bool> NoInterproc("no-interproc",
                                 cl::desc("Disable function summaries"));
static cl::opt<bool> NoCorr("no-corr",
                            cl::desc("Disable branch correlation"));
static cl::opt<bool> NoContainers(
    "no-containers", cl::desc("Do not follow pointers through stack objects"));
static cl::opt<bool> Naive("naive",
                           cl::desc("Baseline: disable all refinements"));
static cl::opt<unsigned> MaxSteps("max-steps", cl::init(200000),
                                  cl::desc("Path search budget per site"));

int main(int argc, char **argv) {
  cl::ParseCommandLineOptions(argc, argv,
                              "KernelLeakGuard early-exit leak analyser\n");

  klg::Spec S;
  if (!SpecFile.empty()) {
    std::string Err;
    if (!S.loadJSON(SpecFile, Err)) {
      errs() << "klg-analyze: " << Err << "\n";
      return 1;
    }
  }

  klg::Options O;
  O.EscapeAnalysis = !(NoEscape || Naive);
  O.Interprocedural = !(NoInterproc || Naive);
  O.BranchCorrelation = !(NoCorr || Naive);
  O.Containers = !(NoContainers || Naive);
  O.MaxStepsPerSite = MaxSteps;

  LLVMContext Ctx;
  SMDiagnostic Diag;
  std::unique_ptr<Module> M = parseIRFile(Input, Diag, Ctx);
  if (!M) {
    Diag.print("klg-analyze", errs());
    return 1;
  }

  std::string Name = ModuleName;
  if (Name.empty())
    Name = sys::path::stem(Input).str();

  auto Start = std::chrono::steady_clock::now();
  klg::Analyzer::prepare(*M);
  klg::Analyzer A(S, O);
  A.run(*M);
  double Ms = std::chrono::duration<double, std::milli>(
                  std::chrono::steady_clock::now() - Start)
                  .count();

  json::Value Report = A.toJSON(Name);
  if (json::Object *Obj = Report.getAsObject())
    if (json::Object *St = Obj->getObject("stats"))
      (*St)["analysis_ms"] = Ms;

  std::error_code EC;
  raw_fd_ostream OS(Output, EC, sys::fs::OF_Text);
  if (EC) {
    errs() << "klg-analyze: cannot write " << Output << ": " << EC.message()
           << "\n";
    return 1;
  }
  OS << formatv("{0:2}", Report) << "\n";
  return 0;
}
