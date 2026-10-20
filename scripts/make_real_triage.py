"""Write results/real/triage.json: the manual review of the static warnings on
real kernel modules that were run in the VM.

Warnings read in the kernel source by the reviewers carry a specific verdict.
The others are classified by a documented pattern and marked as such
("pattern"), never as individually verified.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from klg import config  # noqa: E402

REAL = config.RESULTS / "real"

# (module, function, alloc line) -> (label, note): read in the source.
REVIEWED = {
    ("snd_aloop", "loopback_open", 1263): (
        "false positive",
        "dpcm is freed at the unlock label whenever err < 0; the analyser does not "
        "track that err holds -ENOMEM on this path (value correlation)."),
    ("mac80211_hwsim", "hwsim_new_radio_nl", 6489): (
        "false positive", "hwname is freed at out_free on every exit."),
    ("mac80211_hwsim", "hwsim_new_radio_nl", 6500): (
        "false positive", "param.pmsr_capa is freed at out_free on every exit."),
    ("vxlan", "vxlan_mdb_remote_src_add", 853): (
        "false positive",
        "the entry is linked into the remote's source list by the add helper and "
        "removed on the error path when it was newly created."),
    ("hfs", "hfs_correct_next_unused_CNID", 259): (
        "false positive",
        "hfs_bnode_find() returns a reference-counted node released by hfs_bnode_put; on the "
        "deeper -ENOENT exits the first node has already been put. The analyser does not model "
        "the refcounted lookup."),
    ("hfs", "hfs_correct_next_unused_CNID", 272): (
        "false positive", "same refcounted-lookup pattern as the node obtained at line 259."),
    ("hfs", "hfs_brec_update_parent", 386): (
        "false positive", "hfs_bnode_find() node is put on the error path via hfs_bnode_put."),
    ("scsi_debug", "sdebug_add_host_helper", 8851): (
        "false positive",
        "the sdebug_dev_info objects are freed in the clean: loop by list iteration; the "
        "analyser does not track release through list_for_each_entry_safe."),
    ("erofs", "z_erofs_submit_queue", 1663): (
        "false positive",
        "the queue from jobqueue_init() is freed with kvfree() when no bio was submitted, "
        "otherwise handed to z_erofs_decompress_kickoff() and the bios (bi_private); the "
        "decompression work frees it."),
    ("ntfs3", "indx_read", 1089): (
        "false positive",
        "in and ib are freed at out unless they were stored (in->index, *node); on the error "
        "paths those fields still hold their initial values, which the analyser does not track."),
    ("ntfs3", "indx_read", 1098): (
        "false positive", "same pattern as the allocation at line 1089 (ib != in->index)."),
    ("ntfs3", "do_action", 3166, 3173): (
        "real bug",
        "the kzalloc'd mft_inode (and mi->mrec) leak when mi_format_new() fails; still in "
        "mainline; patches/0002 adds mi_put()."),
    ("ntfs3", "do_action", 3166, 3837): (
        "false positive",
        "mi is released at out by mi_put() unless it is mi2_child; the analyser does not "
        "correlate that comparison."),
    ("ntfs3", "ntfs_inode_printk", 122): (
        "false positive",
        "name is either the static s_name_buf or the kmalloc'd buffer and is freed when "
        "name != s_name_buf."),
    ("ufs", "free_full_branch", 966): (
        "real bug",
        "ubh_bforget() releases the buffers but not the struct ufs_buffer_head that ubh_bread() "
        "allocated (ubh_brelse() does kfree it); proposed upstream in 2018 but not merged; "
        "patches/0004 adds the kfree()."),
    ("ufs", "ufs_truncate_blocks", 1139): (
        "false positive",
        "every buffer read into ubh[] is released by free_branch_tail() (ubh_brelse) in the "
        "while (i--) loop; the analyser does not relate the two loop counters."),
    ("f2fs", "read_raw_super_block", 4448): (
        "false positive",
        "super is stored in *raw_super when a valid block is found, otherwise freed by "
        "if (!*raw_super); the decision depends on the caller's memory."),
    ("f2fs", "__add_ino_entry", 517): (
        "false positive", "new is freed at the end unless it was inserted (e != new)."),
    ("f2fs", "cache_nat_entry", 452): (
        "false positive", "new is freed unless it was inserted (e != new)."),
}

# Allocators that return an ERR_PTR (or a reference-counted object) on failure:
# exits after an IS_ERR() check hold nothing to free.
ERR_PTR_ALLOCATORS = {
    "hfs_bnode_find", "hfs_bnode_split", "hfs_bmap_alloc", "bond_verify_device_path",
    "erofs_read_metadata", "z_erofs_alloc_pcluster", "find_build_dev_info",
    "sdebug_device_create", "vxlan_socket_create", "vxlan_mdb_entry_get",
    "vxlan_mdb_remote_src_entry_add", "zcomp_create", "brd_find_or_alloc_device",
    "squashfs_read_table", "memdup_user", "memdup_user_nul", "strndup_user",
    "jobqueue_init",
}


def main():
    runtime = json.loads((REAL / "summary.json").read_text()).get("runtime_modules", [])
    out = []
    for p in sorted((REAL / "static" / "full").glob("*.json")):
        if p.stem not in runtime:
            continue
        for c in json.loads(p.read_text())["candidates"]:
            key = (p.stem, c["function"], c["alloc"]["line"])
            exact = key + (c["exit"]["line"],)
            if exact in REVIEWED or key in REVIEWED:
                label, note = REVIEWED[exact if exact in REVIEWED else key]
                how = "reviewed in source"
            elif c["allocator"] in ERR_PTR_ALLOCATORS:
                label = "likely false positive"
                note = (f"{c['allocator']}() returns an ERR_PTR or a reference-counted "
                        "object; exits after an error check hold nothing to free")
                how = "pattern"
            else:
                label, note, how = "not reviewed", "low-confidence warning, not reviewed", "-"
            out.append({"id": c["id"], "module": p.stem, "label": label, "note": note,
                        "basis": how})
    (REAL / "triage.json").write_text(json.dumps(out, indent=2))
    counts = {}
    for t in out:
        counts[t["label"]] = counts.get(t["label"], 0) + 1
    print(f"triage: {len(out)} warnings: {counts}")


if __name__ == "__main__":
    main()
