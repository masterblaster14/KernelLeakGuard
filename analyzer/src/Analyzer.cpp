//===- Analyzer.cpp - Early-exit memory leak analysis ---------------------===//
//
// Part of KernelLeakGuard.
//
// For every allocation site the analysis
//   1. computes the set of SSA values that may hold the allocated pointer
//      (casts, GEPs, PHIs, and values reloaded from local stack objects),
//   2. classifies the instructions that end the caller's responsibility:
//      releases (kfree & friends, release wrappers) and ownership transfers
//      (stores to non-local memory, returning the pointer, passing it to a
//      function that captures it),
//   3. enumerates CFG paths from the allocation to a function exit that see
//      neither, skipping the path on which the allocation itself failed and
//      paths that contradict earlier decisions on the same branch condition,
//   4. reports each such path with its exit, return value and the failing
//      calls that steer execution onto it (used for fault injection).
//
//===----------------------------------------------------------------------===//
#include "Analyzer.h"

#include "llvm/ADT/SmallPtrSet.h"
#include "llvm/ADT/SmallVector.h"
#include "llvm/Analysis/LoopInfo.h"
#include "llvm/Analysis/ValueTracking.h"
#include "llvm/IR/Dominators.h"
#include "llvm/IR/CFG.h"
#include "llvm/IR/Constants.h"
#include "llvm/IR/DebugInfoMetadata.h"
#include "llvm/IR/IntrinsicInst.h"
#include "llvm/IR/PassManager.h"
#include "llvm/Passes/PassBuilder.h"
#include "llvm/Transforms/Scalar/InstSimplifyPass.h"
#include "llvm/Transforms/Scalar/LowerExpectIntrinsic.h"
#include "llvm/Transforms/Utils/Local.h"
#include "llvm/Transforms/Utils/Mem2Reg.h"

#include <map>
#include <optional>
#include <set>
#include <tuple>

using namespace llvm;

namespace klg {

//===----------------------------------------------------------------------===//
// Helpers
//===----------------------------------------------------------------------===//

static const Function *calledFunction(const CallBase &CB) {
  return dyn_cast<Function>(CB.getCalledOperand()->stripPointerCasts());
}

static SourceLoc locOf(const Instruction *I) {
  SourceLoc L;
  if (!I)
    return L;
  if (const DILocation *DL = I->getDebugLoc().get()) {
    L.File = DL->getFilename().str();
    L.Line = DL->getLine();
    L.Col = DL->getColumn();
  }
  return L;
}

static unsigned firstLine(const BasicBlock *BB) {
  for (const Instruction &I : *BB)
    if (const DILocation *DL = I.getDebugLoc().get())
      if (DL->getLine())
        return DL->getLine();
  return 0;
}

/// A field of a stack object: (alloca, byte offset), offset -1 = unknown
/// (e.g. an array element indexed by a loop variable).
using Slot = std::pair<const AllocaInst *, int64_t>;

static std::optional<Slot> stackSlot(const Function &F, const Value *Ptr) {
  const DataLayout &DL = F.getDataLayout();
  APInt Off(DL.getIndexTypeSizeInBits(Ptr->getType()), 0);
  const Value *Base =
      Ptr->stripAndAccumulateConstantOffsets(DL, Off, /*AllowNonInbounds=*/true);
  if (const auto *AI = dyn_cast<AllocaInst>(Base); AI && AI->getFunction() == &F)
    return Slot{AI, Off.getSExtValue()};
  const auto *AI = dyn_cast<AllocaInst>(getUnderlyingObject(Ptr, 12));
  if (AI && AI->getFunction() == &F)
    return Slot{AI, -1};
  return std::nullopt;
}

static bool isSourceFunction(const Function &F) {
  if (F.isDeclaration())
    return false;
  const DISubprogram *SP = F.getSubprogram();
  return SP && SP->getFilename().ends_with(".c");
}

static std::string errnoName(int64_t V) {
  static const std::map<int64_t, const char *> Names = {
      {1, "EPERM"},       {2, "ENOENT"},        {5, "EIO"},
      {11, "EAGAIN"},     {12, "ENOMEM"},       {14, "EFAULT"},
      {16, "EBUSY"},      {17, "EEXIST"},       {19, "ENODEV"},
      {22, "EINVAL"},     {28, "ENOSPC"},       {34, "ERANGE"},
      {98, "EADDRINUSE"}, {111, "ECONNREFUSED"}, {113, "EHOSTUNREACH"}};
  auto It = Names.find(-V);
  return It == Names.end() ? std::to_string(V)
                           : "-" + std::string(It->second);
}

/// Requested size of an allocation when it is a compile-time constant. The
/// runtime verifier compares it with the object size kmemleak reports.
static int64_t constantAllocSize(const CallBase &CB, StringRef Allocator) {
  auto Arg = [&](unsigned I) -> int64_t {
    if (I >= CB.arg_size())
      return -1;
    const auto *C = dyn_cast<ConstantInt>(CB.getArgOperand(I));
    return C ? static_cast<int64_t>(C->getZExtValue()) : -1;
  };
  static const std::set<std::string> SizeFirst = {
      "kmalloc",  "kzalloc",  "kmalloc_node", "kzalloc_node", "kvmalloc",
      "kvzalloc", "vmalloc",  "vzalloc",      "__kmalloc",    "kmalloc_large",
      "__vmalloc", "kvmalloc_node", "kvzalloc_node"};
  static const std::set<std::string> CountTimesSize = {
      "kcalloc", "kmalloc_array", "kvcalloc", "kvmalloc_array", "vcalloc",
      "vmalloc_array"};
  std::string N = Allocator.str();
  if (SizeFirst.count(N))
    return Arg(0);
  if (CountTimesSize.count(N)) {
    int64_t A = Arg(0), B = Arg(1);
    return A >= 0 && B >= 0 ? A * B : -1;
  }
  if (N == "kmemdup" || N == "kmemdup_nul")
    return Arg(1);
  return -1;
}

//===----------------------------------------------------------------------===//
// Branch condition normalisation
//===----------------------------------------------------------------------===//

/// Canonical identity of a branch condition, so that two tests of the same
/// predicate on the same operands are recognised as correlated.
struct CondKey {
  const Value *A = nullptr;
  const Value *B = nullptr;
  unsigned Pred = 0;
  bool operator<(const CondKey &O) const {
    return std::tie(A, B, Pred) < std::tie(O.A, O.B, O.Pred);
  }
  bool operator==(const CondKey &O) const {
    return A == O.A && B == O.B && Pred == O.Pred;
  }
};

static bool isZero(const Value *V) {
  if (const auto *C = dyn_cast<Constant>(V))
    return C->isNullValue();
  return false;
}

static bool isBoolLike(const Value *V) {
  if (isa<ZExtInst>(V) || isa<SExtInst>(V) || isa<TruncInst>(V) ||
      isa<CmpInst>(V))
    return true;
  if (const auto *BO = dyn_cast<BinaryOperator>(V))
    return BO->getOpcode() == Instruction::Xor;
  if (const auto *II = dyn_cast<IntrinsicInst>(V))
    return II->getIntrinsicID() == Intrinsic::expect;
  return false;
}

/// Strip boolean plumbing produced by clang (!x, unlikely(), zext, ...).
/// Returns the key and sets Neg if the branch value is the negation of it.
static CondKey normalizeCond(const Value *V, bool &Neg) {
  Neg = false;
  for (unsigned Guard = 0; Guard < 32; ++Guard) {
    if (isa<ZExtInst>(V) || isa<SExtInst>(V) || isa<TruncInst>(V)) {
      V = cast<Instruction>(V)->getOperand(0);
      continue;
    }
    if (const auto *II = dyn_cast<IntrinsicInst>(V))
      if (II->getIntrinsicID() == Intrinsic::expect) {
        V = II->getArgOperand(0);
        continue;
      }
    if (const auto *BO = dyn_cast<BinaryOperator>(V))
      if (BO->getOpcode() == Instruction::Xor) {
        const auto *C = dyn_cast<ConstantInt>(BO->getOperand(1));
        if (C && (C->isAllOnesValue() || C->isOne())) {
          Neg = !Neg;
          V = BO->getOperand(0);
          continue;
        }
      }
    if (const auto *IC = dyn_cast<ICmpInst>(V))
      if (IC->isEquality() && isZero(IC->getOperand(1)) &&
          IC->getOperand(0)->getType()->isIntegerTy() &&
          isBoolLike(IC->getOperand(0))) {
        if (IC->getPredicate() == CmpInst::ICMP_EQ)
          Neg = !Neg;
        V = IC->getOperand(0);
        continue;
      }
    break;
  }
  CondKey K;
  if (const auto *IC = dyn_cast<ICmpInst>(V)) {
    CmpInst::Predicate P = IC->getPredicate();
    CmpInst::Predicate Inv = CmpInst::getInversePredicate(P);
    if (Inv < P) {
      P = Inv;
      Neg = !Neg;
    }
    K.A = IC->getOperand(0);
    K.B = IC->getOperand(1);
    K.Pred = P;
  } else {
    K.A = V;
  }
  return K;
}

//===----------------------------------------------------------------------===//
// FlowTracker: where can a pointer go, and what ends our responsibility?
//===----------------------------------------------------------------------===//

enum class EvKind { Release, Escape, Return };

struct Event {
  EvKind Kind;
  bool ViaContainer; ///< the pointer was reloaded from a stack object
};

class FlowTracker {
public:
  FlowTracker(const Analyzer &A, const Function &F,
              ArrayRef<const Value *> Seeds)
      : A(A), F(F) {
    for (const Value *S : Seeds)
      Direct.insert(S);
    close(Direct);
    // Reloads from stack objects may be stored into further stack objects.
    for (bool Changed = true; Changed;) {
      Changed = false;
      for (const Slot &C : std::vector<Slot>(Containers.begin(), Containers.end()))
        for (const Value *L : loadsFrom(C))
          if (Loaded.insert(L).second)
            Changed = true;
      if (Changed)
        close(Loaded);
    }
    classify();
  }

  bool isAlias(const Value *V) const {
    return Direct.count(V) || Loaded.count(V);
  }
  bool isLoaded(const Value *V) const { return Loaded.count(V); }
  const Event *eventAt(const Instruction *I) const {
    auto It = Events.find(I);
    return It == Events.end() ? nullptr : &It->second;
  }
  /// The object is stored into memory outside this function (linked into a
  /// list or hash table, assigned to a global or to another object): it is
  /// published, not merely handed to a callee.
  bool publishes() const {
    for (const auto &E : Events) {
      const auto *SI = dyn_cast<StoreInst>(E.first);
      if (E.second.Kind != EvKind::Escape || !SI)
        continue;
      // A store into a scratch object allocated by this same function (e.g.
      // a page-pointer array filled and freed again) publishes nothing.
      const auto *Dst = dyn_cast<CallBase>(getUnderlyingObject(SI->getPointerOperand(), 12));
      if (Dst && A.isAllocCall(*Dst))
        continue;
      return true;
    }
    // Handed to a module-defined function that provably publishes it (e.g.
    // list_add_tail(), which kbuild IR keeps as a call). Escapes assumed for
    // unknown external functions do not count.
    for (const auto &E : Events) {
      const auto *CB = dyn_cast<CallBase>(E.first);
      if (E.second.Kind != EvKind::Escape || !CB)
        continue;
      const Function *Callee = calledFunction(*CB);
      if (!Callee || Callee->isDeclaration())
        continue;
      auto It = A.Summaries.find(Callee);
      if (It == A.Summaries.end())
        continue;
      for (unsigned I = 0; I < CB->arg_size() && I < It->second.PublishesParam.size(); ++I)
        if (It->second.PublishesParam[I] && isAlias(CB->getArgOperand(I)))
          return true;
    }
    return false;
  }
  bool hasKind(EvKind K) const {
    for (const auto &E : Events)
      if (E.second.Kind == K)
        return true;
    return false;
  }

  /// Source locations of the statements that release the object.
  std::vector<SourceLoc> releaseLocs() const {
    std::map<std::pair<std::string, unsigned>, SourceLoc> Out;
    for (const auto &E : Events)
      if (E.second.Kind == EvKind::Release) {
        SourceLoc L = locOf(E.first);
        if (L.Line)
          Out[{L.File, L.Line}] = L;
      }
    std::vector<SourceLoc> V;
    for (auto &KV : Out)
      V.push_back(KV.second);
    return V;
  }

private:
  const Analyzer &A;
  const Function &F;
  SmallPtrSet<const Value *, 32> Direct, Loaded;
  std::set<Slot> Containers;
  DenseMap<const Instruction *, Event> Events;

  const AllocaInst *localObject(const Value *Ptr) const {
    const auto *AI = dyn_cast<AllocaInst>(getUnderlyingObject(Ptr, 12));
    return AI && AI->getFunction() == &F ? AI : nullptr;
  }

  std::optional<Slot> slotOf(const Value *Ptr) const {
    return stackSlot(F, Ptr);
  }

  static bool overlaps(const Slot &X, const Slot &Y) {
    return X.first == Y.first &&
           (X.second < 0 || Y.second < 0 || X.second == Y.second);
  }

  std::vector<const Value *> loadsFrom(const Slot &C) const {
    std::vector<const Value *> Out;
    for (const BasicBlock &BB : F)
      for (const Instruction &I : BB)
        if (const auto *LI = dyn_cast<LoadInst>(&I))
          if (LI->getType()->isPointerTy())
            if (std::optional<Slot> S = slotOf(LI->getPointerOperand());
                S && overlaps(*S, C))
              Out.push_back(LI);
    return Out;
  }

  void close(SmallPtrSet<const Value *, 32> &Set) {
    SmallVector<const Value *, 32> Work(Set.begin(), Set.end());
    auto Add = [&](const Value *V) {
      if (Set.insert(V).second)
        Work.push_back(V);
    };
    while (!Work.empty()) {
      const Value *V = Work.pop_back_val();
      for (const User *U : V->users()) {
        if (isa<CastInst>(U) && !isa<PtrToIntInst>(U))
          Add(U);
        else if (const auto *G = dyn_cast<GetElementPtrInst>(U)) {
          if (G->getPointerOperand() == V)
            Add(U);
        } else if (isa<PHINode>(U) || isa<SelectInst>(U)) {
          Add(U);
        } else if (const auto *SI = dyn_cast<StoreInst>(U)) {
          if (SI->getValueOperand() == V && A.O.Containers)
            if (std::optional<Slot> C = slotOf(SI->getPointerOperand()))
              Containers.insert(*C);
        } else if (const auto *CB = dyn_cast<CallBase>(U)) {
          // f(p) returning p: the result is the same object.
          const Function *Callee = calledFunction(*CB);
          if (!Callee || Callee->isDeclaration() || !A.O.Interprocedural)
            continue;
          auto It = A.Summaries.find(Callee);
          if (It == A.Summaries.end())
            continue;
          for (unsigned I = 0; I < CB->arg_size(); ++I)
            if (CB->getArgOperand(I) == V && I < It->second.ReturnsParam.size() &&
                It->second.ReturnsParam[I])
              Add(CB);
        }
      }
    }
  }

  void record(const Instruction *I, EvKind K, bool Via) {
    if (K == EvKind::Escape && !A.O.EscapeAnalysis)
      return;
    auto It = Events.find(I);
    // Release is the strongest evidence; never downgrade it.
    if (It != Events.end() && It->second.Kind == EvKind::Release)
      return;
    Events[I] = Event{K, Via};
  }

  void classifyCall(const CallBase &CB, unsigned ArgNo, bool Via) {
    if (CB.isInlineAsm())
      return;
    const Function *Callee = calledFunction(CB);
    if (!Callee) {
      record(&CB, EvKind::Escape, Via); // indirect call may capture
      return;
    }
    if (Callee->isIntrinsic())
      return;
    StringRef Name = Callee->getName();
    if (const std::vector<int> *Args = A.S.releasedArgs(Name)) {
      for (int Idx : *Args)
        if (Idx == Spec::AnyArg || Idx == static_cast<int>(ArgNo)) {
          record(&CB, EvKind::Release, Via);
          return;
        }
      return;
    }
    if (!Callee->isDeclaration()) {
      if (A.O.Interprocedural) {
        auto It = A.Summaries.find(Callee);
        if (It == A.Summaries.end() || ArgNo >= It->second.FreesParam.size())
          return;
        if (It->second.FreesParam[ArgNo])
          record(&CB, EvKind::Release, Via);
        else if (It->second.EscapesParam[ArgNo])
          record(&CB, EvKind::Escape, Via);
        return;
      }
      if (!A.S.isNonEscaping(Name))
        record(&CB, EvKind::Escape, Via);
      return;
    }
    if (A.S.isNonEscaping(Name) || A.S.isAllocator(Name))
      return;
    record(&CB, EvKind::Escape, Via);
  }

  void classifyUser(const Value *V, const User *U, bool Via) {
    if (const auto *SI = dyn_cast<StoreInst>(U)) {
      if (SI->getValueOperand() != V)
        return; // writing into the object is fine
      const Value *Dst = SI->getPointerOperand();
      if (A.O.Containers && localObject(Dst))
        return; // tracked as a container
      if (isAlias(getUnderlyingObject(Dst, 12)))
        return; // self-reference inside the same object
      record(SI, EvKind::Escape, Via);
    } else if (isa<ReturnInst>(U)) {
      record(cast<Instruction>(U), EvKind::Return, Via);
    } else if (const auto *CB = dyn_cast<CallBase>(U)) {
      for (unsigned I = 0; I < CB->arg_size(); ++I)
        if (CB->getArgOperand(I) == V)
          classifyCall(*CB, I, Via);
    }
  }

  void classify() {
    for (const Value *V : Direct)
      for (const User *U : V->users())
        classifyUser(V, U, false);
    for (const Value *V : Loaded)
      for (const User *U : V->users())
        classifyUser(V, U, true);
    // A stack object holding the pointer handed to a real call (not an
    // intrinsic such as memset) may let the callee take the pointer over.
    SmallPtrSet<const AllocaInst *, 8> Objects;
    for (const Slot &C : Containers)
      Objects.insert(C.first);
    for (const AllocaInst *C : Objects) {
      SmallVector<const Value *, 16> Work{C};
      SmallPtrSet<const Value *, 16> Seen;
      while (!Work.empty()) {
        const Value *V = Work.pop_back_val();
        if (!Seen.insert(V).second)
          continue;
        for (const User *U : V->users()) {
          if (isa<GetElementPtrInst>(U) || isa<BitCastInst>(U))
            Work.push_back(U);
          else if (const auto *CB = dyn_cast<CallBase>(U)) {
            const Function *Callee = calledFunction(*CB);
            if (Callee && (Callee->isIntrinsic() ||
                           A.S.isNonEscaping(Callee->getName())))
              continue;
            record(CB, EvKind::Escape, true);
          }
        }
      }
    }
  }
};

//===----------------------------------------------------------------------===//
// Analyzer
//===----------------------------------------------------------------------===//

/// A defined function whose body is just "return <constant>", e.g. the
/// mem_alloc_profiling_enabled() stub that kmalloc()'s macro tests when
/// allocation profiling is configured out.
static Constant *constantReturn(const Function &F) {
  if (F.isDeclaration() || F.size() != 1)
    return nullptr;
  const auto *RI = dyn_cast<ReturnInst>(F.getEntryBlock().getTerminator());
  if (!RI || !RI->getReturnValue())
    return nullptr;
  for (const Instruction &I : F.getEntryBlock())
    if (&I != RI && !isa<DbgInfoIntrinsic>(&I))
      return nullptr;
  return dyn_cast<Constant>(RI->getReturnValue());
}

void Analyzer::prepare(Module &M) {
  // Fold configuration stubs so that compile-time-dead branches disappear
  // exactly as they would in the optimised kernel module.
  for (Function &F : M)
    for (BasicBlock &BB : F)
      for (Instruction &I : make_early_inc_range(BB))
        if (auto *CB = dyn_cast<CallBase>(&I))
          if (const Function *Callee = calledFunction(*CB))
            if (Constant *C = constantReturn(*Callee))
              if (!CB->getType()->isVoidTy()) {
                CB->replaceAllUsesWith(C);
                CB->eraseFromParent();
              }

  PassBuilder PB;
  LoopAnalysisManager LAM;
  FunctionAnalysisManager FAM;
  CGSCCAnalysisManager CGAM;
  ModuleAnalysisManager MAM;
  PB.registerModuleAnalyses(MAM);
  PB.registerCGSCCAnalyses(CGAM);
  PB.registerFunctionAnalyses(FAM);
  PB.registerLoopAnalyses(LAM);
  PB.crossRegisterProxies(LAM, FAM, CGAM, MAM);
  FunctionPassManager FPM;
  FPM.addPass(PromotePass());
  FPM.addPass(LowerExpectIntrinsicPass());
  FPM.addPass(InstSimplifyPass());
  ModulePassManager MPM;
  MPM.addPass(createModuleToFunctionPassAdaptor(std::move(FPM)));
  MPM.run(M, MAM);

  // Fold branches on constants and drop the blocks that became unreachable.
  // (Only the CFG is cleaned up; no code motion or block merging happens, so
  // source locations of statements are preserved.)
  for (Function &F : M) {
    if (F.isDeclaration())
      continue;
    for (BasicBlock &BB : F)
      ConstantFoldTerminator(&BB, /*DeleteDeadConditions=*/true);
    removeUnreachableBlocks(F);
  }
}

bool Analyzer::isAllocCall(const CallBase &CB) const {
  if (!CB.getType()->isPointerTy())
    return false;
  const Function *Callee = calledFunction(CB);
  if (!Callee)
    return false;
  if (S.isManaged(Callee->getName()))
    return false;
  if (S.isAllocator(Callee->getName()))
    return true;
  if (O.Interprocedural && !Callee->isDeclaration()) {
    auto It = Summaries.find(Callee);
    return It != Summaries.end() && It->second.ReturnsAlloc;
  }
  return false;
}

/// Does V (through casts, PHIs and selects) come from an allocation call?
static bool fromAllocation(const Analyzer &A, const Value *V,
                           SmallPtrSetImpl<const Value *> &Seen,
                           bool (Analyzer::*IsAlloc)(const CallBase &) const) {
  if (!Seen.insert(V).second)
    return false;
  if (const auto *CB = dyn_cast<CallBase>(V))
    return (A.*IsAlloc)(*CB);
  if (const auto *CI = dyn_cast<CastInst>(V))
    return fromAllocation(A, CI->getOperand(0), Seen, IsAlloc);
  if (const auto *P = dyn_cast<PHINode>(V)) {
    for (const Value *In : P->incoming_values())
      if (fromAllocation(A, In, Seen, IsAlloc))
        return true;
    return false;
  }
  if (const auto *Sel = dyn_cast<SelectInst>(V))
    return fromAllocation(A, Sel->getTrueValue(), Seen, IsAlloc) ||
           fromAllocation(A, Sel->getFalseValue(), Seen, IsAlloc);
  return false;
}

void Analyzer::computeSummaries(Module &M) {
  for (Function &F : M)
    if (!F.isDeclaration()) {
      Summary &Su = Summaries[&F];
      Su.FreesParam.assign(F.arg_size(), false);
      Su.EscapesParam.assign(F.arg_size(), false);
      Su.ReturnsParam.assign(F.arg_size(), false);
      Su.PublishesParam.assign(F.arg_size(), false);
    }
  if (!O.Interprocedural)
    return;

  // Monotone fixpoints: facts only ever flip from false to true.
  // 1. What each function does with its pointer parameters.
  for (unsigned Iter = 0; Iter < 10; ++Iter) {
    bool Changed = false;
    for (Function &F : M) {
      if (F.isDeclaration())
        continue;
      Summary &Su = Summaries[&F];
      for (const Argument &Arg : F.args()) {
        if (!Arg.getType()->isPointerTy())
          continue;
        unsigned I = Arg.getArgNo();
        FlowTracker FT(*this, F, {&Arg});
        bool Frees = FT.hasKind(EvKind::Release);
        bool Escapes = FT.hasKind(EvKind::Escape);
        bool Returns = FT.hasKind(EvKind::Return);
        if (Escapes && !Su.PublishesParam[I] && FT.publishes()) {
          Su.PublishesParam[I] = true;
          Changed = true;
        }
        if (Frees && !Su.FreesParam[I]) {
          Su.FreesParam[I] = true;
          Changed = true;
        }
        if (Escapes && !Su.EscapesParam[I]) {
          Su.EscapesParam[I] = true;
          Changed = true;
        }
        if (Returns && !Su.ReturnsParam[I]) {
          Su.ReturnsParam[I] = true;
          Changed = true;
        }
      }
    }
    if (!Changed)
      break;
  }

  // 2. Which functions return a fresh allocation the caller owns. After 1,
  //    so that a helper publishing the object (PublishesParam) is known.
  for (unsigned Iter = 0; Iter < 10; ++Iter) {
    bool Changed = false;
    for (Function &F : M) {
      if (F.isDeclaration())
        continue;
      Summary &Su = Summaries[&F];
      if (!Su.ReturnsAlloc && F.getReturnType()->isPointerTy()) {
        for (const BasicBlock &BB : F)
          if (const auto *RI = dyn_cast<ReturnInst>(BB.getTerminator()))
            if (const Value *RV = RI->getReturnValue()) {
              SmallPtrSet<const Value *, 16> Seen;
              if (!fromAllocation(*this, RV, Seen, &Analyzer::isAllocCall))
                continue;
              // A helper that publishes the new object before returning it
              // (list_add into a global list, hash insertion) or returns a
              // shared, reference-counted one does not give the caller sole
              // ownership: it is a lookup, not an allocator.
              bool Published = false;
              for (const Value *V : Seen)
                if (const auto *CB = dyn_cast<CallBase>(V); CB && isAllocCall(*CB))
                  Published |= FlowTracker(*this, F, {CB}).publishes();
              if (Published)
                continue;
              Su.ReturnsAlloc = true;
              Changed = true;
              break;
            }
      }
    }
    if (!Changed)
      break;
  }
}

void Analyzer::run(Module &M) {
  computeSummaries(M);
  for (Function &F : M) {
    if (!isSourceFunction(F))
      continue;
    ++St.Functions;
    SmallVector<CallBase *, 16> Sites;
    for (BasicBlock &BB : F)
      for (Instruction &I : BB)
        if (auto *CB = dyn_cast<CallBase>(&I))
          if (isAllocCall(*CB) && !CB->use_empty())
            Sites.push_back(CB);
    for (CallBase *CB : Sites) {
      ++St.AllocSites;
      const Function *Callee = calledFunction(*CB);
      AllocSites[F.getName().str()].push_back(
          {locOf(CB), Callee ? Spec::normalize(Callee->getName()) : ""});
      analyzeSite(F, *CB);
    }
  }
  St.Candidates = Cands.size();
}

//===----------------------------------------------------------------------===//
// Per-site path search
//===----------------------------------------------------------------------===//

class SiteAnalysis {
public:
  SiteAnalysis(const Analyzer &A, Function &F, CallBase &Site)
      : A(A), F(F), Site(Site), FT(A, F, {&Site}) {}

  void run() {
    BasicBlock *BB = Site.getParent();
    if (A.O.BranchCorrelation)
      seedDominatingDecisions(BB);
    Visits[BB] = 1;
    Blocks.push_back(BB);
    DecAtBlock.push_back(Decisions.size());
    dfs(BB, std::next(Site.getIterator()));
  }

  std::vector<Candidate> Results;
  bool Exhausted = false;

private:
  struct Decision {
    CondKey Key;
    bool Value;
  };

  const Analyzer &A;
  Function &F;
  CallBase &Site;
  FlowTracker FT;

  unsigned Steps = 0;
  bool Reallocated = false;
  SmallVector<BasicBlock *, 32> Blocks;
  SmallVector<size_t, 32> DecAtBlock; ///< Decisions.size() when block entered
  SmallVector<Decision, 16> Decisions;
  /// Decision index ranges made stale by going round a loop again: the
  /// conditions are re-evaluated with new values in the next iteration.
  SmallVector<std::pair<size_t, size_t>, 4> Stale;
  SmallVector<const CallBase *, 8> Trigs;
  /// Calls that take ownership only on success, reached on this path and not
  /// yet decided by a branch on their result.
  SmallVector<const CallBase *, 4> Pending;
  SmallVector<const BasicBlock *, 8> TrigSucc; ///< error branch of each trigger
  DenseMap<const BasicBlock *, unsigned> Visits;
  std::set<unsigned> SeenExits;

  /// Branch outcomes that must hold for execution to reach the allocation
  /// at all (e.g. "if (verbose)" around it). Branches inside a loop that
  /// contains the allocation are skipped: they are re-evaluated per iteration.
  void seedDominatingDecisions(BasicBlock *SiteBB) {
    DominatorTree DT(F);
    LoopInfo LI(DT);
    const Loop *L = LI.getLoopFor(SiteBB);
    for (DomTreeNode *N = DT.getNode(SiteBB); N && N->getIDom();
         N = N->getIDom()) {
      BasicBlock *D = N->getIDom()->getBlock();
      if (L && L->contains(D))
        continue;
      auto *BR = dyn_cast<BranchInst>(D->getTerminator());
      if (!BR || !BR->isConditional())
        continue;
      for (unsigned S = 0; S < 2; ++S)
        if (DT.dominates(BasicBlockEdge(D, BR->getSuccessor(S)), SiteBB)) {
          bool Neg;
          CondKey K = normalizeCond(BR->getCondition(), Neg);
          Decisions.push_back({K, (S == 0) != Neg});
        }
    }
  }

  bool isStale(size_t Idx) const {
    for (const auto &R : Stale)
      if (Idx >= R.first && Idx < R.second)
        return true;
    return false;
  }

  /// The single call whose result was stored into the stack slot Ptr points
  /// to (e.g. "ws.out = kmalloc(...)" followed by "if (!ws.out)").
  const CallBase *storedCall(const Value *Ptr) const {
    std::optional<Slot> S = stackSlot(F, Ptr);
    if (!S || S->second < 0)
      return nullptr;
    const CallBase *Found = nullptr;
    for (const BasicBlock &BB : F)
      for (const Instruction &I : BB)
        if (const auto *SI = dyn_cast<StoreInst>(&I)) {
          std::optional<Slot> T = stackSlot(F, SI->getPointerOperand());
          if (!T || T->first != S->first || T->second != S->second)
            continue;
          if (isa<Constant>(SI->getValueOperand()))
            continue; // initialisation such as "= NULL"
          const auto *CB = dyn_cast<CallBase>(SI->getValueOperand());
          if (!CB || (Found && Found != CB))
            return nullptr;
          Found = CB;
        }
    return Found;
  }

  /// For a null test of the tracked pointer: true if KeyValue means NULL.
  std::optional<bool> nullTest(const CondKey &K, bool KeyValue) const {
    if (K.Pred != CmpInst::ICMP_EQ)
      return std::nullopt;
    bool AIsPtr = FT.isAlias(K.A) && isZero(K.B);
    bool BIsPtr = FT.isAlias(K.B) && isZero(K.A);
    if (!AIsPtr && !BIsPtr)
      return std::nullopt;
    return KeyValue;
  }

  /// True if (K, KeyValue) is the "IS_ERR(tracked) is true" branch: the tracked
  /// pointer holds an ERR_PTR error code here, not a heap object, so there is
  /// nothing to free (the same situation as a failed allocation). This removes
  /// the dominant false-positive class on real kernel code, where lookup/
  /// factory helpers return an ERR_PTR on failure.
  bool errPtrTest(const CondKey &K, bool KeyValue) const {
    if (K.B || !KeyValue)              // IS_ERR(x) is a 1-operand boolean test
      return false;
    const auto *CB = dyn_cast_or_null<CallBase>(K.A);
    const Function *Callee = CB ? calledFunction(*CB) : nullptr;
    if (!Callee || !Callee->getName().starts_with("IS_ERR") || CB->arg_size() != 1)
      return false;                    // covers IS_ERR and IS_ERR_OR_NULL
    const Value *Arg = CB->getArgOperand(0)->stripPointerCasts();
    if (FT.isAlias(Arg))
      return true;
    if (const auto *LI = dyn_cast<LoadInst>(Arg))
      return storedCall(LI->getPointerOperand()) == &Site;
    return false;
  }

  /// Find the call whose result the condition tests.
  const CallBase *controllingCall(const Value *V) const {
    for (unsigned Guard = 0; Guard < 16 && V; ++Guard) {
      if (FT.isLoaded(V) || V == &Site)
        return &Site;
      if (const auto *CI = dyn_cast<CastInst>(V)) {
        V = CI->getOperand(0);
        continue;
      }
      if (const auto *LI = dyn_cast<LoadInst>(V)) {
        V = storedCall(LI->getPointerOperand());
        continue;
      }
      if (const auto *CB = dyn_cast<CallBase>(V)) {
        const Function *Callee = calledFunction(*CB);
        if (Callee && Callee->isIntrinsic())
          return nullptr;
        // IS_ERR(x) / IS_ERR_OR_NULL(x): the interesting call produced x.
        if (Callee && Callee->getName().starts_with("IS_ERR") &&
            CB->arg_size() == 1) {
          V = CB->getArgOperand(0);
          continue;
        }
        return CB;
      }
      return nullptr;
    }
    return nullptr;
  }

  /// If taking this edge means "the call failed", return that call.
  const CallBase *errorTrigger(const CondKey &K, bool KeyValue) const {
    const Value *Other = K.B;
    const CallBase *C = controllingCall(K.A);
    if (!C && K.B) {
      C = controllingCall(K.B);
      Other = K.A;
    }
    if (!C)
      return nullptr;
    if (!K.B) // the call's boolean result is the condition (IS_ERR)
      return KeyValue ? C : nullptr;
    if (!Other || !isZero(Other))
      return nullptr;
    if (C->getType()->isPointerTy() || C == &Site)
      return K.Pred == CmpInst::ICMP_EQ && KeyValue ? C : nullptr;
    switch (K.Pred) {
    case CmpInst::ICMP_EQ: // x == 0 is false: non-zero error code
      return KeyValue ? nullptr : C;
    case CmpInst::ICMP_SGE: // x >= 0 is false: negative errno
      return K.A != Other && !KeyValue ? C : nullptr;
    default:
      return nullptr;
    }
  }

  std::optional<bool> constantOnPath(const Value *C) const {
    if (const auto *CI = dyn_cast<ConstantInt>(C))
      return !CI->isZero();
    const auto *IC = dyn_cast<ICmpInst>(C);
    if (!IC)
      return std::nullopt;
    const auto *L = dyn_cast<ConstantInt>(resolveOnPath(IC->getOperand(0)));
    const auto *R = dyn_cast<ConstantInt>(resolveOnPath(IC->getOperand(1)));
    if (!L || !R)
      return std::nullopt;
    return ICmpInst::compare(L->getValue(), R->getValue(), IC->getPredicate());
  }

  const Value *resolveOnPath(const Value *V) const {
    for (unsigned Guard = 0; Guard < 32; ++Guard) {
      const auto *P = dyn_cast<PHINode>(V);
      if (!P)
        return V;
      int Idx = -1;
      for (int J = static_cast<int>(Blocks.size()) - 1; J > 0; --J)
        if (Blocks[J] == P->getParent()) {
          Idx = J;
          break;
        }
      if (Idx <= 0)
        return V;
      int BI = P->getBasicBlockIndex(Blocks[Idx - 1]);
      if (BI < 0)
        return V;
      V = P->getIncomingValue(BI);
    }
    return V;
  }

  void describeExit(const ReturnInst &RI, Candidate &C) const {
    const BasicBlock *R = RI.getParent();
    const Instruction *ExitI = &RI;
    if (Blocks.size() >= 2 && !R->getSinglePredecessor()) {
      const Instruction *T = Blocks[Blocks.size() - 2]->getTerminator();
      if (T->getDebugLoc())
        ExitI = T;
    }
    C.Exit = locOf(ExitI);
    if (!C.Exit.Line)
      C.Exit = locOf(&RI);

    const Value *RV = RI.getReturnValue();
    if (!RV) {
      C.ExitKind = "void";
      return;
    }
    RV = resolveOnPath(RV);
    if (const auto *CI = dyn_cast<ConstantInt>(RV)) {
      int64_t Val = CI->getSExtValue();
      C.ReturnValue = errnoName(Val);
      C.ExitKind = Val < 0 ? "error" : "normal";
      return;
    }
    if (isa<ConstantPointerNull>(RV)) {
      C.ReturnValue = "NULL";
      C.ExitKind = "error";
      return;
    }
    // Propagated error code: the path tested this value and found it bad.
    for (const Decision &D : Decisions) {
      if (D.Key.A != RV && D.Key.B != RV)
        continue;
      bool Bad = (D.Key.Pred == CmpInst::ICMP_EQ && !D.Value) ||
                 (D.Key.Pred == CmpInst::ICMP_SGE && !D.Value);
      if (Bad) {
        C.ExitKind = "error";
        const CallBase *Src = dyn_cast<CallBase>(RV);
        const Function *Fn = Src ? calledFunction(*Src) : nullptr;
        C.ReturnValue = Fn ? "error from " + Spec::normalize(Fn->getName())
                           : "propagated error";
        return;
      }
    }
    C.ExitKind = "unknown";
    C.ReturnValue = "?";
  }

  // A return of phi(obj, NULL) hands the object to the caller only on paths
  // that bring obj into the phi; on the others (allocation kept, NULL or an
  // ERR_PTR returned) the object is not transferred.
  bool returnsOtherOnPath(const Instruction &I, const Event &E) const {
    const auto *RI = dyn_cast<ReturnInst>(&I);
    if (!RI || E.Kind != EvKind::Return || !RI->getReturnValue())
      return false;
    const Value *V = RI->getReturnValue();
    const Value *R = resolveOnPath(V);
    // undef: no return value was set on this path, i.e. the edge is
    // infeasible (e.g. the default of clang's cleanup-destination switch).
    return R != V && !isa<UndefValue>(R) && !FT.isAlias(R);
  }

  void recordLeak(const ReturnInst &RI) {
    Candidate C;
    describeExit(RI, C);
    if (!SeenExits.insert(C.Exit.Line).second)
      return;
    C.Function = F.getName().str();
    if (const Function *Callee = calledFunction(Site))
      C.Allocator = Spec::normalize(Callee->getName());
    C.Alloc = locOf(&Site);
    C.AllocSize = constantAllocSize(Site, C.Allocator);
    for (const CallBase *T : Trigs) {
      Trigger Tr;
      if (const Function *Fn = calledFunction(*T))
        Tr.Callee = Spec::normalize(Fn->getName());
      Tr.Loc = locOf(T);
      Tr.Kind = A.isAllocCall(*T) ? "alloc" : "call";
      C.Triggers.push_back(Tr);
    }
    // Fix point: first statement of the error branch taken after the primary
    // trigger failed. Exclusive if only that edge reaches it, so a release
    // inserted there runs on this path alone.
    if (!TrigSucc.empty()) {
      const BasicBlock *S = TrigSucc.back();
      for (const Instruction &I : *S)
        if (const DILocation *DL = I.getDebugLoc().get(); DL && DL->getLine()) {
          C.Fix = locOf(&I);
          break;
        }
      C.FixExclusive = S->getSinglePredecessor() != nullptr;
    }
    C.ReleaseSites = FT.releaseLocs();
    std::set<unsigned> SeenLines;
    for (const BasicBlock *BB : Blocks)
      if (unsigned L = firstLine(BB); L && SeenLines.insert(L).second)
        C.PathLines.push_back(L);

    bool Releases = FT.hasKind(EvKind::Release);
    bool Transfers = FT.hasKind(EvKind::Escape) || FT.hasKind(EvKind::Return);
    if (C.ExitKind == "error" && Releases) {
      C.Confidence = "high";
      C.Category = "missing-release-on-error-path";
    } else if (C.ExitKind == "error" && Transfers) {
      C.Confidence = "medium";
      C.Category = "ownership-not-transferred-on-error-path";
    } else if (!Releases && !Transfers) {
      C.Confidence = "medium";
      C.Category = "never-released";
    } else {
      C.Confidence = "low";
      C.Category = "missing-release-on-other-path";
    }
    Results.push_back(std::move(C));
  }

  bool done() const {
    return Exhausted || Results.size() >= A.O.MaxPathsPerSite;
  }

  void follow(BasicBlock *Succ) {
    unsigned &V = Visits[Succ];
    if (V >= 2) // explore each loop at most twice per path
      return;
    bool BackEdge = V > 0;
    ++V;
    if (BackEdge) {
      // Decisions taken since the first visit of Succ belong to the previous
      // loop iteration and no longer constrain the next one.
      size_t First = 0;
      while (Blocks[First] != Succ)
        ++First;
      Stale.push_back({DecAtBlock[First], Decisions.size()});
    }
    Blocks.push_back(Succ);
    DecAtBlock.push_back(Decisions.size());
    dfs(Succ, Succ->begin());
    DecAtBlock.pop_back();
    Blocks.pop_back();
    if (BackEdge)
      Stale.pop_back();
    --Visits[Succ];
  }

  void dfs(BasicBlock *BB, BasicBlock::iterator It) {
    size_t NPending = Pending.size();
    dfsBlock(BB, It);
    Pending.resize(NPending);
  }

  bool isPending(const CallBase *C) const { return C && is_contained(Pending, C); }

  void dfsBlock(BasicBlock *BB, BasicBlock::iterator It) {
    if (done())
      return;
    if (++Steps > A.O.MaxStepsPerSite) {
      Exhausted = true;
      return;
    }
    bool SavedRealloc = Reallocated;
    for (; It != BB->end(); ++It) {
      Instruction &I = *It;
      if (&I == &Site)
        Reallocated = true; // a new instance; the old one lives on in memory
      if (const Event *E = FT.eventAt(&I))
        if ((!Reallocated || E->ViaContainer) && !returnsOtherOnPath(I, *E)) {
          const auto *CB = dyn_cast<CallBase>(&I);
          const Function *Callee = CB ? calledFunction(*CB) : nullptr;
          if (E->Kind == EvKind::Escape && Callee &&
              A.S.transfersOnSuccess(Callee->getName())) {
            Pending.push_back(CB); // decided by the branch on its result
          } else {
            Reallocated = SavedRealloc;
            return; // released or handed over: no leak on this path
          }
        }
      if (const auto *CB = dyn_cast<CallBase>(&I))
        if (CB->doesNotReturn()) {
          Reallocated = SavedRealloc;
          return;
        }
      if (const auto *RI = dyn_cast<ReturnInst>(&I)) {
        if (!Pending.empty()) { // result never checked: assume it succeeded
          Reallocated = SavedRealloc;
          return;
        }
        recordLeak(*RI);
        Reallocated = SavedRealloc;
        return;
      }
      if (isa<UnreachableInst>(&I)) {
        Reallocated = SavedRealloc;
        return;
      }
    }

    Instruction *T = BB->getTerminator();
    if (auto *BR = dyn_cast<BranchInst>(T); BR && BR->isConditional()) {
      bool Neg;
      CondKey K = normalizeCond(BR->getCondition(), Neg);
      // Compare the values the operands have on this path, so that a test of
      // phi(err1, err2) correlates with an earlier test of err2 itself.
      if (A.O.BranchCorrelation) {
        K.A = resolveOnPath(K.A);
        if (K.B)
          K.B = resolveOnPath(K.B);
      }
      // A condition on values that are constants on this path (a one-case
      // cleanup-destination switch becomes such a branch) decides the edge.
      std::optional<bool> Known =
          A.O.BranchCorrelation ? constantOnPath(BR->getCondition()) : std::nullopt;
      for (unsigned S = 0; S < 2 && !done(); ++S) {
        if (Known && *Known != (S == 0))
          continue;
        bool KeyValue = (S == 0) != Neg;
        if (A.O.BranchCorrelation) {
          bool Contradicts = false;
          for (size_t Idx = 0; Idx < Decisions.size(); ++Idx)
            if (Decisions[Idx].Key == K && Decisions[Idx].Value != KeyValue &&
                !isStale(Idx))
              Contradicts = true;
          if (Contradicts)
            continue;
        }
        if (std::optional<bool> IsNull = nullTest(K, KeyValue))
          if (*IsNull && !Reallocated)
            continue; // the allocation itself failed: nothing to leak
        if (errPtrTest(K, KeyValue) && !Reallocated)
          continue; // tracked pointer is an ERR_PTR here: nothing to free
        const CallBase *Trig = errorTrigger(K, KeyValue);
        if (isPending(errorTrigger(K, !KeyValue)))
          continue; // the call succeeded: it took ownership
        const CallBase *Undecided = isPending(Trig) ? Trig : nullptr;
        if (Undecided) // the call failed: the object is still ours
          Pending.erase(find(Pending, Undecided));
        Decisions.push_back({K, KeyValue});
        if (Trig) {
          Trigs.push_back(Trig);
          TrigSucc.push_back(BR->getSuccessor(S));
        }
        follow(BR->getSuccessor(S));
        if (Trig) {
          Trigs.pop_back();
          TrigSucc.pop_back();
        }
        if (Undecided)
          Pending.push_back(Undecided);
        Decisions.pop_back();
      }
    } else if (auto *SW = dyn_cast<SwitchInst>(T);
               SW && A.O.BranchCorrelation &&
               isa<ConstantInt>(resolveOnPath(SW->getCondition()))) {
      // The selector is a constant on this path (e.g. clang's cleanup
      // destination after a scoped goto): only one successor is feasible.
      auto *CI = cast<ConstantInt>(resolveOnPath(SW->getCondition()));
      follow(SW->findCaseValue(CI)->getCaseSuccessor());
    } else {
      for (BasicBlock *Succ : successors(BB)) {
        if (done())
          break;
        follow(Succ);
      }
    }
    Reallocated = SavedRealloc;
  }
};

void Analyzer::analyzeSite(Function &F, CallBase &Site) {
  SiteAnalysis SA(*this, F, Site);
  SA.run();
  if (SA.Exhausted)
    ++St.BudgetExhausted;
  for (Candidate &C : SA.Results) {
    C.Approximate = SA.Exhausted;
    Cands.push_back(std::move(C));
  }
}

//===----------------------------------------------------------------------===//
// JSON report
//===----------------------------------------------------------------------===//

static json::Object locJSON(const SourceLoc &L) {
  return json::Object{{"file", L.File}, {"line", L.Line}, {"col", L.Col}};
}

json::Value Analyzer::toJSON(const std::string &ModuleName) const {
  json::Array Arr;
  for (const Candidate &C : Cands) {
    json::Array Trigs;
    for (const Trigger &T : C.Triggers)
      Trigs.push_back(json::Object{{"callee", T.Callee},
                                   {"file", T.Loc.File},
                                   {"line", T.Loc.Line},
                                   {"kind", T.Kind}});
    json::Array Lines;
    for (unsigned L : C.PathLines)
      Lines.push_back(L);
    json::Array Rel;
    for (const SourceLoc &L : C.ReleaseSites)
      Rel.push_back(locJSON(L));
    json::Value Fix = nullptr;
    if (C.Fix.Line) {
      json::Object FO = locJSON(C.Fix);
      FO["exclusive"] = C.FixExclusive;
      Fix = std::move(FO);
    }
    std::string Id = ModuleName + ":" + C.Function + ":" +
                     std::to_string(C.Alloc.Line) + ":" +
                     std::to_string(C.Exit.Line);
    Arr.push_back(json::Object{{"id", Id},
                               {"module", ModuleName},
                               {"function", C.Function},
                               {"allocator", C.Allocator},
                               {"alloc", locJSON(C.Alloc)},
                               {"alloc_size", C.AllocSize},
                               {"exit", locJSON(C.Exit)},
                               {"exit_kind", C.ExitKind},
                               {"return_value", C.ReturnValue},
                               {"confidence", C.Confidence},
                               {"category", C.Category},
                               {"triggers", std::move(Trigs)},
                               {"path_lines", std::move(Lines)},
                               {"fix", std::move(Fix)},
                               {"release_sites", std::move(Rel)},
                               {"approximate", C.Approximate}});
  }
  json::Object Sites;
  for (const auto &KV : AllocSites) {
    json::Array A;
    for (const auto &S : KV.second)
      A.push_back(json::Object{{"file", S.first.File},
                               {"line", S.first.Line},
                               {"allocator", S.second}});
    Sites[KV.first] = std::move(A);
  }
  return json::Object{
      {"module", ModuleName},
      {"tool", "klg-analyze"},
      {"alloc_sites", std::move(Sites)},
      {"options", json::Object{{"escape", O.EscapeAnalysis},
                               {"interprocedural", O.Interprocedural},
                               {"branch_correlation", O.BranchCorrelation},
                               {"containers", O.Containers}}},
      {"stats", json::Object{{"functions", St.Functions},
                             {"alloc_sites", St.AllocSites},
                             {"candidates", St.Candidates},
                             {"budget_exhausted", St.BudgetExhausted}}},
      {"candidates", std::move(Arr)}};
}

} // namespace klg
