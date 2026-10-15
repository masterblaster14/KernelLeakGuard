"""KernelLeakGuard test suite.

    python3 -m unittest discover -s tests -v

Unit tests run anywhere; the analyser tests need analyzer/build/klg-analyze
and the IR in results/ir (python3 -m klg build) and are skipped otherwise.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from klg import config, evidence, ground_truth, verify  # noqa: E402

AGENT_LOG = """\
K KLG: attempt n=3 target=/sys/kernel/debug/klg_klg_l03_reg_fail
@@ATTEMPT n=3 ret=-1 errno=22 injected=1
K FAULT_INJECTION: forcing a failure.\\x0aname fail_function, interval 1, probability 0
K Call Trace:
K  <TASK>
K  dump_stack_lvl+0x84/0xc0
K  ? hw_register_channel+0x5/0x20 [klg_l03_reg_fail]
K  hw_register_channel+0x9/0x20 [klg_l03_reg_fail]
K  channel_open+0x32/0x70 [klg_l03_reg_fail]
K  klg_trigger_write+0x12/0x30 [klg_l03_reg_fail]
K  </TASK>
@@END
@@ATTEMPT n=4 ret=1 errno=0 injected=0
@@END
"""

KMEMLEAK = """\
unreferenced object 0xffff8880058f2d48 (size 8):
  comm "klg-agent", pid 81, jiffies 4294671270
  hex dump (first 8 bytes):
    03 00 00 00 00 00 00 00                          ........
  backtrace (crc 9c47bb37):
    __kmalloc_cache_noprof+0x1b5/0x420
    channel_open+0x1c/0x70 [klg_l03_reg_fail]
    klg_trigger_write+0x12/0x30 [klg_l03_reg_fail]
unreferenced object 0xffff888005af4380 (size 128):
  comm "klg-agent", pid 90, jiffies 4294671999
  backtrace (crc 0):
    __kmalloc_cache_noprof+0x1b0/0x420
    0xffffffffa0012345
    do_one_initcall+0x10f/0x300
"""


class TestEvidenceParsing(unittest.TestCase):
    def test_agent_log(self):
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as f:
            f.write(AGENT_LOG)
        attempts = evidence.parse_agent_log(Path(f.name))
        self.assertEqual(len(attempts), 2)
        a = attempts[0]
        self.assertEqual((a.n, a.ret, a.errno, a.injected), (3, -1, 22, True))
        self.assertTrue(a.traced())
        frames = [fr.text for fr in a.fault_frames() if fr.module]
        self.assertIn("channel_open+0x32/0x70", frames)
        self.assertFalse(attempts[1].injected)

    def test_kmemleak(self):
        leaks = evidence.parse_kmemleak(KMEMLEAK)
        self.assertEqual(len(leaks), 2)
        self.assertEqual(leaks[0].size, 8)
        self.assertEqual(leaks[0].modules(), {"klg_l03_reg_fail"})
        self.assertEqual(leaks[0].comm, "klg-agent")
        # Second object: module already unloaded, frame left as a raw address.
        self.assertEqual(leaks[1].modules(), set())
        self.assertEqual(leaks[1].unresolved_module_frames, 1)

    def test_symbol_map_resolves_unloaded_module(self):
        log = ("K KLG-MOD mymod text=ffffffffa0010000+2000 init=ffffffffa0020000+1000\n"
               "K KLG-SYM mymod ffffffffa0010000 helper\n"
               "K KLG-SYM mymod ffffffffa0020040 mymod_init\n")
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as f:
            f.write(log)
        sm = evidence.SymbolMap.from_logs([f.name])
        fr = sm.resolve(0xFFFFFFFFA0020052)
        self.assertEqual((fr.func, fr.offset, fr.module), ("mymod_init", 0x12, "mymod"))
        self.assertIsNone(sm.resolve(0xFFFFFFFFA0050000))          # outside every module
        self.assertIsNone(sm.resolve(0xFFFFFFFFA0020052, {"other"}))  # not a candidate
        lk = evidence.parse_kmemleak(KMEMLEAK)[1]
        lk.raw_addresses = [0xFFFFFFFFA0020052]
        self.assertTrue(lk.resolve(sm))
        self.assertEqual(lk.modules(), {"mymod"})

    def test_crash_site_from_begin_marker(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "sweep_x.log").write_text("@@BEGIN n=1\n@@ATTEMPT n=1 ret=0 errno=0 "
                                                 "injected=1\n@@END\n@@BEGIN n=2\n")
            (Path(d) / "sweep_y.log").write_text("@@BEGIN n=1\n@@ATTEMPT n=1 ret=0 errno=0 "
                                                 "injected=0\n@@END\n")
            self.assertEqual(verify._crash_site(Path(d)), {"log": "sweep_x", "fail_nth": 2})

    def test_size_compatible(self):
        self.assertTrue(verify.size_compatible(100, 128))   # kmalloc-128 bucket
        self.assertTrue(verify.size_compatible(20, 32))
        self.assertTrue(verify.size_compatible(256, 256))
        self.assertFalse(verify.size_compatible(100, 256))
        self.assertFalse(verify.size_compatible(-1, 128))   # unknown size never matches


class TestPlanning(unittest.TestCase):
    def cand(self, trig_line, kind="alloc"):
        return {"id": "m:f:10:20", "module": "m", "function": "f",
                "alloc": {"file": "m.c", "line": 10},
                "triggers": [{"callee": "kmalloc", "file": "m.c", "line": trig_line, "kind": kind}]}

    def test_exact_line_match(self):
        pts = [verify.FaultPoint(1, [("m.c", 10)], ["f+0x10/0x40"], -1, 12),
               verify.FaultPoint(3, [("m.c", 14)], ["f+0x22/0x40"], -1, 12),
               verify.FaultPoint(5, [("other.c", 14)], ["g+0x8/0x40"], -1, 12)]
        hits, how = verify._match_points(self.cand(14), pts, {})
        self.assertEqual(how, "line")
        # Same line number in another file of the module must not match.
        self.assertEqual([(p.n, fr) for p, fr in hits], [(3, "f+0x22/0x40")])

    def test_function_fallback_needs_single_site(self):
        pts = [verify.FaultPoint(3, [], [], -1, 12, True, {"f": "f+0x48/0x2d0"})]
        one = {"f": [{"file": "m.c", "line": 10}]}
        two = {"f": [{"file": "m.c", "line": 10}, {"file": "m.c", "line": 12}]}
        hits, how = verify._match_points(self.cand(10), pts, one)
        self.assertEqual(how, "function")
        hits, how = verify._match_points(self.cand(10), pts, two)
        self.assertEqual(hits, [])

    def test_silent_fault_fallback(self):
        pts = [verify.FaultPoint(2, [], [], -1, 12, traced=False)]
        hits, how = verify._match_points(self.cand(99, "call"), pts, {})
        self.assertEqual(how, "silent")
        self.assertIsNone(hits[0][1])

    def test_schedule_isolates_init_tests(self):
        tests = [verify.Test("a__n1", "a", "trigger", "", 1, None),
                 verify.Test("b__n1", "b", "trigger", "", 1, None),
                 verify.Test("a__n3", "a", "trigger", "", 3, None),
                 verify.Test("c__n5", "c", "init", "", 5, None)]
        rounds = verify.schedule(tests)
        for r in rounds:
            mods = [t.module for t in r]
            self.assertEqual(len(mods), len(set(mods)))       # ≤ 1 test per module
            if any(t.mode == "init" for t in r):
                self.assertEqual(len(r), 1)                   # init tests alone


class TestRealModules(unittest.TestCase):
    def test_modname(self):
        from klg import real
        self.assertEqual(real.modname("snd-dummy"), "snd_dummy")
        self.assertEqual(real.modname("dm-flakey"), "dm_flakey")

    def test_fragment_mapping_complete(self):
        from klg import real
        files = real.wanted_files()                      # raises if a symbol is unmapped
        self.assertEqual(len(files), len(set(files)))
        self.assertIn("null_blk", files)

    def test_load_order_dependencies_first(self):
        from klg import real
        graph = {"vxlan": ["udp_tunnel", "ip6_udp_tunnel"], "ip6_udp_tunnel": ["udp_tunnel"],
                 "udp_tunnel": [], "dummy": []}
        orig = real.deps_of
        real.deps_of = lambda ko: graph[ko.name]
        try:
            order = real.load_order(["vxlan", "dummy"], {n: Path(n) for n in graph})
        finally:
            real.deps_of = orig
        self.assertEqual(order, ["udp_tunnel", "ip6_udp_tunnel"])


class TestGroundTruth(unittest.TestCase):
    def test_corpus_annotations(self):
        gt = ground_truth.load()
        leaks = [s for s in gt.values() if s.label == "LEAK"]
        self.assertGreaterEqual(len(leaks), 17)
        self.assertTrue(all("alloc" in s.code or "kstrdup" in s.code or "kmemdup" in s.code
                            or "session_create" in s.code or "make_label" in s.code
                            or "kasprintf" in s.code for s in gt.values()))

    def test_init_mode_detection(self):
        self.assertTrue(ground_truth.init_mode(config.CORPUS / "klg_l01_two_alloc.c"))
        self.assertFalse(ground_truth.init_mode(config.CORPUS / "klg_l03_reg_fail.c"))


@unittest.skipUnless(config.ANALYZER.exists() and (config.IR_DIR / "klg_l02_goto_ladder.bc").exists(),
                     "analyser or IR not built")
class TestAnalyzer(unittest.TestCase):
    def run_on(self, module, *flags):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.json"
            subprocess.run([str(config.ANALYZER), str(config.IR_DIR / f"{module}.bc"), "-o", str(out),
                            "--module-name", module, *flags], check=True)
            return json.loads(out.read_text())

    def sites(self, rep):
        return {c["alloc"]["line"] for c in rep["candidates"]}

    def test_detects_wrong_goto_label(self):
        rep = self.run_on("klg_l02_goto_ladder")
        c = next(c for c in rep["candidates"] if c["alloc"]["line"] == 32)
        self.assertEqual(c["return_value"], "-ENOMEM")
        self.assertEqual(c["confidence"], "high")
        self.assertEqual([t["callee"] for t in c["triggers"]], ["kasprintf"])

    def test_error_propagation_exit(self):
        rep = self.run_on("klg_l03_reg_fail")
        c = rep["candidates"][0]
        self.assertEqual(c["exit_kind"], "error")
        self.assertIn("hw_register_channel", c["return_value"])

    def test_fixed_version_is_clean(self):
        for m in ("klg_s01_two_alloc_ok", "klg_s02_goto_ok", "klg_s07_free_wrapper_ok"):
            self.assertEqual(self.run_on(m)["candidates"], [], m)

    def test_ownership_transfer(self):
        for m in ("klg_s03_list_owner", "klg_s04_param_owner", "klg_s11_register_owner",
                  "klg_s13_rcu_free", "klg_s14_kref"):
            self.assertEqual(self.run_on(m)["candidates"], [], m)
            self.assertNotEqual(self.run_on(m, "--no-escape")["candidates"], [], m)

    def test_interprocedural_wrapper(self):
        self.assertIn(37, self.sites(self.run_on("klg_l06_wrapper_alloc")))
        self.assertNotIn(37, self.sites(self.run_on("klg_l06_wrapper_alloc", "--no-interproc")))

    def test_branch_correlation(self):
        self.assertEqual(self.run_on("klg_s10_correlated")["candidates"], [])
        self.assertNotEqual(self.run_on("klg_s10_correlated", "--no-corr")["candidates"], [])

    def test_local_struct_container(self):
        self.assertIn(21, self.sites(self.run_on("klg_l17_local_struct")))
        self.assertEqual(self.run_on("klg_s08_local_struct_ok")["candidates"], [])

    def test_loop_leak(self):
        rep = self.run_on("klg_l04_loop_partial")
        self.assertIn("-ENOMEM", {c["return_value"] for c in rep["candidates"]})

    def test_managed_memory_ignored(self):
        self.assertEqual(self.run_on("klg_s06_devm")["stats"]["alloc_sites"], 0)

    def test_alloc_size_reported(self):
        rep = self.run_on("klg_l01_two_alloc")
        self.assertEqual(rep["candidates"][0]["alloc_size"], 100)


if __name__ == "__main__":
    unittest.main()
