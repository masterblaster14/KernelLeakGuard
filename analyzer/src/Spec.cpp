//===- Spec.cpp - Kernel memory API specification -------------------------===//
//
// Part of KernelLeakGuard.
//
//===----------------------------------------------------------------------===//
#include "Spec.h"

#include "llvm/Support/JSON.h"
#include "llvm/Support/MemoryBuffer.h"

using namespace llvm;

namespace klg {

namespace {

const char *const DefaultAllocators[] = {
    // slab
    "kmalloc", "kzalloc", "kcalloc", "kmalloc_array", "kmalloc_node",
    "kzalloc_node", "kcalloc_node", "kmalloc_array_node", "krealloc",
    "krealloc_array", "__kmalloc", "__kmalloc_node", "__kmalloc_cache",
    "__kmalloc_cache_node", "__kmalloc_node_track_caller",
    "__kmalloc_large_node", "kmalloc_large", "kmalloc_large_node",
    "kmalloc_trace", "kmalloc_node_trace", "kmalloc_track_caller",
    "kmem_cache_alloc", "kmem_cache_zalloc", "kmem_cache_alloc_node",
    "kmem_cache_alloc_lru",
    // kv*/vmalloc
    "kvmalloc", "kvzalloc", "kvcalloc", "kvmalloc_array", "kvmalloc_node",
    "kvzalloc_node", "kvrealloc", "__kvmalloc_node", "vmalloc", "vzalloc",
    "vmalloc_node", "vzalloc_node", "vmalloc_user", "vmalloc_32",
    "vmalloc_array", "vcalloc", "__vmalloc", "__vmalloc_node",
    "__vmalloc_node_range",
    // duplication helpers
    "kstrdup", "kstrndup", "kmemdup", "kmemdup_nul", "kmemdup_array",
    "kasprintf", "kvasprintf", "memdup_user", "memdup_user_nul",
    "vmemdup_user", "strndup_user",
    // network devices (alloc_netdev*(), alloc_etherdev*() expand to these)
    "alloc_netdev_mqs", "alloc_etherdev_mqs",
};

const char *const DefaultManagedPrefixes[] = {"devm_", "pcim_", "drmm_",
                                             "dmam_"};

struct Dealloc {
  const char *Name;
  int Arg;
};

const Dealloc DefaultDeallocators[] = {
    {"kfree", 0},           {"kvfree", 0},
    {"vfree", 0},           {"vfree_atomic", 0},
    {"kfree_sensitive", 0}, {"kvfree_sensitive", 0},
    {"kfree_const", 0},     {"kmem_cache_free", 1},
    {"krealloc", 0},        {"kvfree_call_rcu", Spec::AnyArg},
    {"free_netdev", 0},
};

// External functions that only read or write through their pointer
// arguments and never store the pointer itself somewhere else.
const char *const DefaultNonEscaping[] = {
    "memset", "memcpy", "memmove", "__memset", "__memcpy", "__memmove",
    "memcmp", "bcmp", "memchr", "memscan", "strcmp", "strncmp", "strcasecmp",
    "strlen", "strnlen", "strcpy", "strncpy", "strscpy", "sized_strscpy",
    "strscpy_pad", "strlcpy", "strlcat", "strcat", "strncat", "strchr",
    "strrchr", "strstr", "strsep", "sprintf", "snprintf", "scnprintf",
    "vsnprintf", "vscnprintf", "sscanf", "kstrtoul", "kstrtol", "kstrtoint",
    "kstrtouint", "kstrtou8", "kstrtou16", "kstrtos8", "kstrtobool",
    "kstrtoull", "kstrtoll", "_kstrtoul", "_kstrtol", "simple_strtoul",
    "simple_strtol", "crc32_le", "crc32_be", "crc32c", "hex_dump_to_buffer",
    "print_hex_dump", "_printk", "printk", "__dynamic_pr_debug",
    "__dynamic_dev_dbg", "__warn_printk", "dump_stack", "_dev_err",
    "_dev_warn", "_dev_info", "_dev_notice", "dev_err_probe",
    "__check_object_size", "check_object_size", "should_fail_usercopy",
    "_copy_from_user", "_copy_to_user", "copy_user_generic",
    "rep_movs_alternative", "__copy_user_nocache", "__clear_user",
    "clear_user", "strncpy_from_user", "strnlen_user", "__mutex_init",
    "mutex_lock", "mutex_unlock", "mutex_lock_interruptible",
    "mutex_trylock", "_raw_spin_lock", "_raw_spin_unlock",
    "_raw_spin_lock_irqsave", "_raw_spin_unlock_irqrestore",
    "_raw_spin_lock_irq", "_raw_spin_unlock_irq", "_raw_spin_lock_bh",
    "_raw_spin_unlock_bh", "__raw_spin_lock_init", "__init_waitqueue_head",
    "__init_rwsem", "down_read", "up_read", "down_write", "up_write",
    "refcount_warn_saturate", "__list_add_valid_or_report",
    "__list_del_entry_valid_or_report", "get_random_bytes", "ktime_get",
    "ktime_get_real_ts64", "msleep", "usleep_range_state", "__udelay",
    "__const_udelay", "schedule", "cond_resched", "__cond_resched",
    // initialise / tear down an embedded struct badblocks; never retain it
    "badblocks_init", "badblocks_exit",
};

const char *const DefaultNonEscapingPrefixes[] = {
    "__sanitizer", "__ubsan_handle", "__asan", "__kasan", "__kcsan", "__tsan",
    "__msan", "kasan_", "kcsan_", "kmsan_", "__might_", "__fortify",
    "fortify_", "__write_overflow", "__read_overflow", "__x86_indirect",
    "__x86_return",
};

} // namespace

Spec::Spec() {
  for (const char *A : DefaultAllocators)
    Allocators.insert(A);
  for (const char *P : DefaultManagedPrefixes)
    ManagedPrefixes.emplace_back(P);
  for (const Dealloc &D : DefaultDeallocators)
    Deallocators[D.Name].push_back(D.Arg);
  for (const char *N : DefaultNonEscaping)
    NonEscaping.insert(N);
  for (const char *P : DefaultNonEscapingPrefixes)
    NonEscapingPrefixes.emplace_back(P);
}

std::string Spec::normalize(StringRef Name) {
  Name.consume_front("\01");
  // Compiler clones such as foo.constprop.0 or foo.isra.1.
  Name = Name.split('.').first;
  Name.consume_back("_noprof");
  return Name.str();
}

bool Spec::isAllocator(StringRef Name) const {
  return Allocators.contains(normalize(Name));
}

bool Spec::isManaged(StringRef Name) const {
  std::string N = normalize(Name);
  for (const std::string &P : ManagedPrefixes)
    if (StringRef(N).starts_with(P))
      return true;
  return false;
}

const std::vector<int> *Spec::releasedArgs(StringRef Name) const {
  auto It = Deallocators.find(normalize(Name));
  return It == Deallocators.end() ? nullptr : &It->second;
}

bool Spec::isNonEscaping(StringRef Name) const {
  std::string N = normalize(Name);
  if (NonEscaping.contains(N))
    return true;
  for (const std::string &P : NonEscapingPrefixes)
    if (StringRef(N).starts_with(P))
      return true;
  return false;
}

bool Spec::transfersOnSuccess(StringRef Name) const {
  // register_netdevice(): "the caller must free the device with
  // free_netdev()" when registration fails.
  static const StringSet<> Names = {"register_netdevice", "register_netdev"};
  return Names.contains(normalize(Name));
}

bool Spec::loadJSON(const std::string &Path, std::string &Err) {
  auto Buf = MemoryBuffer::getFile(Path);
  if (!Buf) {
    Err = "cannot read " + Path;
    return false;
  }
  Expected<json::Value> V = json::parse((*Buf)->getBuffer());
  if (!V) {
    Err = toString(V.takeError());
    return false;
  }
  const json::Object *O = V->getAsObject();
  if (!O) {
    Err = "spec root must be an object";
    return false;
  }
  if (const json::Array *A = O->getArray("allocators"))
    for (const json::Value &E : *A)
      if (auto S = E.getAsString())
        Allocators.insert(*S);
  if (const json::Array *A = O->getArray("managed_prefixes"))
    for (const json::Value &E : *A)
      if (auto S = E.getAsString())
        ManagedPrefixes.push_back(S->str());
  if (const json::Array *A = O->getArray("non_escaping"))
    for (const json::Value &E : *A)
      if (auto S = E.getAsString())
        NonEscaping.insert(*S);
  if (const json::Object *D = O->getObject("deallocators"))
    for (const auto &KV : *D)
      if (auto I = KV.second.getAsInteger())
        Deallocators[KV.first.str()].push_back(static_cast<int>(*I));
  return true;
}

} // namespace klg
