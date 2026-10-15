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
        "hfs_bnode_find() returns an ERR_PTR on failure; on the IS_ERR path nothing "
        "was obtained, so there is nothing to release."),
    ("hfs", "hfs_correct_next_unused_CNID", 272): (
        "false positive", "same ERR_PTR pattern as the lookup at line 259."),
    ("hfs", "hfs_brec_update_parent", 386): (
        "false positive", "hfs_bnode_find() ERR_PTR result; nothing to release on that path."),
    ("bonding", "alb_upper_dev_walk", 992): (
        "false positive",
        "on the IS_ERR_OR_NULL path bond_verify_device_path() returned no object."),
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
            if key in REVIEWED:
                label, note = REVIEWED[key]
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
