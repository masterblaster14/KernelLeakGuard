//===- Analyzer.h - Early-exit memory leak analysis -----------------------===//
//
// Part of KernelLeakGuard. MLEE-inspired detection of allocations that are
// neither released nor handed over on some path to a function exit.
//
//===----------------------------------------------------------------------===//
#ifndef KLG_ANALYZER_H
#define KLG_ANALYZER_H

#include "Spec.h"

#include "llvm/ADT/DenseMap.h"
#include "llvm/IR/Instructions.h"
#include "llvm/IR/Module.h"
#include "llvm/Support/JSON.h"

#include <map>
#include <string>
#include <vector>

namespace klg {

struct Options {
  bool EscapeAnalysis = true;  ///< ownership transfer ends tracking
  bool Interprocedural = true; ///< summaries of module-defined functions
  bool BranchCorrelation = true;
  bool Containers = true;      ///< follow pointers through stack objects
  unsigned MaxStepsPerSite = 200000;
  unsigned MaxPathsPerSite = 8;
};

/// What a module-defined function does with each pointer parameter.
struct Summary {
  bool ReturnsAlloc = false;
  std::vector<bool> FreesParam;
  std::vector<bool> EscapesParam;
  std::vector<bool> ReturnsParam;
};

struct SourceLoc {
  std::string File;
  unsigned Line = 0;
  unsigned Col = 0;
};

/// A call whose failure leads the program down the leaking path.
struct Trigger {
  std::string Callee;
  SourceLoc Loc;
  std::string Kind; ///< "alloc", "call"
};

struct Candidate {
  std::string Function;
  std::string Allocator;
  SourceLoc Alloc;
  int64_t AllocSize = -1; ///< bytes requested, -1 if not a constant
  SourceLoc Exit;
  std::string ExitKind;   ///< error | normal | void | unknown
  std::string ReturnValue;
  std::string Confidence; ///< high | medium | low
  std::string Category;
  std::vector<Trigger> Triggers; ///< in path order; last is primary
  std::vector<unsigned> PathLines;
  SourceLoc Fix;                     ///< first statement of the error branch
  bool FixExclusive = false;         ///< only the error edge reaches Fix
  std::vector<SourceLoc> ReleaseSites; ///< existing releases of the object
  bool Approximate = false;
};

struct Stats {
  unsigned Functions = 0;
  unsigned AllocSites = 0;
  unsigned Candidates = 0;
  unsigned BudgetExhausted = 0;
};

class Analyzer {
public:
  Analyzer(const Spec &S, const Options &O) : S(S), O(O) {}

  /// Promote stack slots to SSA so that pointer flows become explicit.
  static void prepare(llvm::Module &M);

  void run(llvm::Module &M);

  /// Every tracked allocation site: function -> (line, allocator) pairs.
  /// The runtime verifier uses it when a stack frame resolves only to a
  /// function (e.g. merged debug locations after loop unrolling).
  std::map<std::string, std::vector<std::pair<SourceLoc, std::string>>> AllocSites;

  const std::vector<Candidate> &candidates() const { return Cands; }
  const Stats &stats() const { return St; }
  llvm::json::Value toJSON(const std::string &ModuleName) const;

private:
  const Spec &S;
  Options O;
  llvm::DenseMap<const llvm::Function *, Summary> Summaries;
  std::vector<Candidate> Cands;
  Stats St;

  void computeSummaries(llvm::Module &M);
  bool isAllocCall(const llvm::CallBase &CB) const;
  void analyzeSite(llvm::Function &F, llvm::CallBase &Site);

  friend class SiteAnalysis;
  friend class FlowTracker;
};

} // namespace klg

#endif // KLG_ANALYZER_H
