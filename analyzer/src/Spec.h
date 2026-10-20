//===- Spec.h - Kernel memory API specification ---------------------------===//
//
// Part of KernelLeakGuard. Describes which kernel functions allocate memory,
// which release it, and which external functions are known not to capture
// (take ownership of) their pointer arguments.
//
//===----------------------------------------------------------------------===//
#ifndef KLG_SPEC_H
#define KLG_SPEC_H

#include "llvm/ADT/StringMap.h"
#include "llvm/ADT/StringRef.h"
#include "llvm/ADT/StringSet.h"
#include <string>
#include <vector>

namespace klg {

class Spec {
public:
  /// Argument index meaning "any pointer argument releases the object".
  static constexpr int AnyArg = -1;

  Spec();

  /// Canonical name used for lookups: strips the asm-label marker, the
  /// memory-allocation-profiling suffix "_noprof" and trailing clone suffixes.
  static std::string normalize(llvm::StringRef Name);

  bool isAllocator(llvm::StringRef Name) const;
  /// Device-/resource-managed allocations (devm_*, pcim_*, ...) are freed by
  /// the driver core and are therefore never tracked as leak candidates.
  bool isManaged(llvm::StringRef Name) const;
  /// Returns the released argument indices, or nullptr if not a deallocator.
  const std::vector<int> *releasedArgs(llvm::StringRef Name) const;
  bool isNonEscaping(llvm::StringRef Name) const;
  /// Takes ownership of its pointer argument only when it succeeds; on
  /// failure the caller still owns (and must release) the object.
  bool transfersOnSuccess(llvm::StringRef Name) const;

  /// Merge additional entries from a JSON file:
  ///   {"allocators": [..], "managed_prefixes": [..],
  ///    "deallocators": {"name": argIndex}, "non_escaping": [..]}
  bool loadJSON(const std::string &Path, std::string &Err);

private:
  llvm::StringSet<> Allocators;
  std::vector<std::string> ManagedPrefixes;
  llvm::StringMap<std::vector<int>> Deallocators;
  llvm::StringSet<> NonEscaping;
  std::vector<std::string> NonEscapingPrefixes;
};

} // namespace klg

#endif // KLG_SPEC_H
