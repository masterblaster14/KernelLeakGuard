"""Write results/real/root_causes.json: the root-cause analysis of the kernel
defects found on real modules (SLUB slab-cache leak, f2fs kobject-name leak,
null_blk use-after-free crash; ntfs3 and ufs leaks found statically).

Every number is read from the evidence kept under results/real/: fault-probe
runs (scripts/fault_probe.py) erofs_bisect, erofs_n85, erofs_slubfix (kernel
built by scripts/build_patched_kernel.sh with patches/0001), f2fs_stock,
f2fs_patched (module with patches/0003), nullblk_probe, nullblk_739; and the
static patch validations (scripts/validate_patch.py) ntfs3_fix, ufs_fix.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from klg import config  # noqa: E402

REAL = config.RESULTS / "real"


def batches(run: str) -> list[dict]:
    out = []
    for f in sorted((REAL / run / "out").glob("kml_*.txt"), key=lambda p: int(p.stem.split("_")[1])):
        lo, hi = (int(x) for x in f.stem.split("_")[1:3])
        txt = f.read_text(errors="replace")
        out.append({"faults": [lo, hi], "unreferenced": txt.count("unreferenced object"),
                    "caches": sorted(set(re.findall(r"erofs_pcluster-\d+", txt)))})
    return out


def grep_count(run: str, pattern: str) -> int:
    # dmesg is cumulative over the run: count in the last batch's capture.
    last = max((REAL / run / "out").glob("dmesg_*.txt"), key=lambda p: int(p.stem.split("_")[1]))
    return len(re.findall(pattern, last.read_text(errors="replace")))


def main():
    stock, fixed = batches("erofs_bisect"), batches("erofs_slubfix")
    n85 = (REAL / "erofs_n85" / "out" / "dmesg_85.txt").read_text(errors="replace")
    trace = re.findall(r"\]  (\S+\+0x[0-9a-f]+/0x[0-9a-f]+(?: \[\w+\])?)",
                       n85.split("is not initialized, yet kobject_put")[1])[:6]
    slub = {
        "module": "erofs",
        "component": "mm/slub.c (sysfs_slab_add / sysfs_slab_release)",
        "trigger": "fail-nth 85 of erofs init: kmalloc in create_unique_id(), inlined into "
                   "sysfs_slab_add(), while creating the erofs_pcluster-1 cache",
        "mechanism": [
            "sysfs_slab_add() returns before kobject_init_and_add() when create_unique_id() "
            "fails, so the cache's kobject is never initialised",
            "do_kmem_cache_create() treats sysfs failure as non-fatal and keeps the cache",
            "kmem_cache_destroy() unlinks the cache and calls kobject_put() on the "
            "uninitialised kobject: WARN, refcount underflow, kmem_cache_release() never runs",
            "the struct kmem_cache, its per-node structures and its name stay allocated and "
            "unreferenced",
        ],
        "stock": {"batches": len(stock), "leaking_batches": sum(1 for b in stock if b["unreferenced"]),
                  "unreferenced": sum(b["unreferenced"] for b in stock)},
        "patched": {"batches": len(fixed), "leaking_batches": sum(1 for b in fixed if b["unreferenced"]),
                    "unreferenced": sum(b["unreferenced"] for b in fixed),
                    "sysfs_failures_exercised": grep_count("erofs_slubfix", r"Unable to add cache erofs_pcluster"),
                    "kobject_warnings": grep_count("erofs_slubfix", r"is not initialized, yet kobject_put")},
        "warn_trace": trace,
        "upstream": "unchanged in mainline 7.3 and linux-next (next-20261020) as of 2026-10-20",
        "patch": "patches/0001-mm-slub-release-cache-whose-sysfs-kobject-was-never-initialised.patch",
    }
    crashed = sorted(int(p.stem.split("_")[-1]) for p in (REAL / "nullblk_probe" / "out").glob("crashes_run_*"))
    probed = sorted({int(p.stem.split("_")[1]) for p in (REAL / "nullblk_probe" / "out").glob("dmesg_*.txt")}
                    | set(crashed))
    con = (REAL / "nullblk_739" / "console_crash1.log").read_text(errors="replace")
    inj = con[con.rindex("FAULT_INJECTION"):]
    fault_stack = re.findall(r"\]  (\w+\+0x[0-9a-f]+/0x[0-9a-f]+(?: \[\w+\])?)", inj.split("BUG:")[0])[3:8]
    crash_stack = re.findall(r"\]  (\w+\+0x[0-9a-f]+/0x[0-9a-f]+)",
                             inj.split("BUG:")[1].split("Call Trace:")[1])[:4]
    nullblk = {
        "module": "null_blk",
        "component": "block/genhd.c disk_scan_partitions() deferred fput + module init failure",
        "trigger": "fail-nth 739 of null_blk init: kmalloc in configfs_register_subsystem(), "
                   "after null_init() has added its disk",
        "probed": probed, "crashed": crashed,
        "fault_stack": fault_stack, "crash_stack": crash_stack,
        "mechanism": [
            "add_disk() -> disk_scan_partitions() opens the whole disk (taking a module "
            "reference through disk->fops->owner) and drops it with fput(); called from a user "
            "task (finit_module), the final __fput() is deferred to task_work",
            "configfs_register_subsystem() then fails; null_init() destroys its device and "
            "returns the error, and the module loader frees the module",
            "on return to user space the deferred __fput() runs bdev_release(), whose "
            "module_put(disk->fops->owner) reads the freed module's block_device_operations",
        ],
        "upstream": "unchanged in mainline 7.3 (disk_scan_partitions() still uses fput(); "
                    "null_init() still registers configfs after creating devices)",
        "fix": "releasing the scan file synchronously (__fput_sync()) is "
               "documented as reserved for kernel threads; the fix belongs to the block / "
               "module-loader maintainers",
    }
    val = json.loads((REAL / "ntfs3_fix" / "validation.json").read_text())
    ntfs3 = {
        "module": "ntfs3",
        "component": "fs/ntfs3/fslog.c do_action() (log replay)",
        "found_by": "static analysis (high-confidence warning), confirmed by reading the source",
        "mechanism": [
            "for an InitializeFileRecordSegment log record whose MFT record cannot be read "
            "(mi_get() fails), do_action() allocates a struct mft_inode with kzalloc()",
            "mi_format_new() can fail (mi_init()'s buffer allocation, or ntfs_get_bh() after "
            "mi->mrec was allocated) and does not free mi",
            "do_action() then returns the error without mi_put(): the mft_inode (and mi->mrec) "
            "leak; on success the object is released by mi_put() at the out label",
        ],
        "upstream": "unchanged in mainline 7.3 and linux-next (next-20261020); a web search "
                    "found no existing report or fix",
        "patch": "patches/0002-fs-ntfs3-free-mft_inode-when-mi_format_new-fails-in-do_action.patch",
        "validation": val,
        "runtime": "not confirmed at runtime, which needs an NTFS image with a dirty log that "
                   "replays InitializeFileRecordSegment for an unreadable record",
    }
    # The same SLUB leak seen by the all-module sweep in other modules' initialisation.
    summ = json.loads((REAL / "summary.json").read_text())
    slub["also_in"] = sorted({l["module"] for l in summ.get("dynamic_leaks", [])
                              if "__kmem_cache_create_args+" in " ".join(l.get("backtrace", []))})

    def names(run: str) -> dict[str, int]:
        txt = (REAL / run / "out" / "kml_369_429.txt").read_text(errors="replace")
        found = {}
        for rec in txt.split("unreferenced object")[1:]:
            if "kobject_set_name_vargs" in rec:
                m = re.search(r"  ([a-z_]+)\.", rec)
                key = m.group(1) if m else "?"
                found[key] = found.get(key, 0) + 1
        return found
    f2fs = {
        "module": "f2fs",
        "component": "fs/f2fs/sysfs.c f2fs_init_sysfs()",
        "found_by": "runtime sweep of module initialisation (kmemleak)",
        "trigger": "fault points 369-429 of f2fs init: allocations inside kobject_init_and_add() "
                   "for the \"features\" and \"tuning\" kobjects",
        "mechanism": [
            "kobject_init_and_add() requires kobject_put() even when it fails (the kobject "
            "name is already allocated)",
            "f2fs_init_sysfs() jumps past kobject_put(&f2fs_feat) when adding \"features\" fails "
            "and past kobject_put(&f2fs_tune) when adding \"tuning\" fails",
            "initialisation fails, the module is freed, and the kstrdup'd kobject names are "
            "left unreferenced",
        ],
        "stock_leaked_names": names("f2fs_stock"),
        "patched_leaked_names": names("f2fs_patched"),
        "upstream": "unchanged in mainline 7.3 as of 2026-10-20",
        "introduced_by": {"commit": "b635f2ecdb5a",
                          "subject": "f2fs: fix uninitialized kobject put in f2fs_init_sysfs()",
                          "date": "2026-04-10",
                          "note": "the rewrite stopped putting an uninitialised f2fs_tune but "
                                  "also stopped putting the kobject whose own "
                                  "kobject_init_and_add() failed; backported to stable (present "
                                  "in 6.18.55)"},
        "patch": "patches/0003-f2fs-put-kobjects-when-kobject_init_and_add-fails-in-f2fs_init_sysfs.patch",
    }
    ufs = {
        "module": "ufs",
        "component": "fs/ufs/util.c ubh_bforget(), called by fs/ufs/inode.c free_full_branch()",
        "found_by": "static analysis (warning), confirmed by reading the source",
        "mechanism": [
            "free_full_branch() reads an indirect block with ubh_bread(), which kmallocs a "
            "struct ufs_buffer_head",
            "it ends with ubh_bforget(ubh), which bforget()s the buffers but, unlike "
            "ubh_brelse(), does not kfree() the ufs_buffer_head",
            "one ufs_buffer_head leaks for every indirect block freed when a file is "
            "truncated or deleted",
        ],
        "upstream": "unchanged in mainline 7.3; the leak was reported with a fix in 2018 (\"ufs: "
                    "Fix memory leak in the unlink path\", Luis Henriques) that is not in mainline",
        "patch": "patches/0004-ufs-free-the-ufs_buffer_head-in-ubh_bforget.patch",
        "validation": json.loads((REAL / "ufs_fix" / "validation.json").read_text()),
        "runtime": "not confirmed at runtime, which needs a mounted UFS image and a truncate",
    }
    out = {"slub_sysfs_leak": slub, "null_blk_crash": nullblk, "ntfs3_do_action_leak": ntfs3,
           "f2fs_sysfs_leak": f2fs, "ufs_bforget_leak": ufs}
    (REAL / "root_causes.json").write_text(json.dumps(out, indent=2))
    print(f"slub: stock {slub['stock']}, patched {slub['patched']}")
    print(f"null_blk: crashed at {crashed} of {probed}")


if __name__ == "__main__":
    main()
