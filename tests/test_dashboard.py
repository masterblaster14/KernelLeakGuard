"""Dashboard tests: every page renders without exceptions, and the Run button
really starts the pipeline in the background and reports its result.

    .venv/bin/python -m unittest tests.test_dashboard -v
"""
import json
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from streamlit.testing.v1 import AppTest
except ImportError:  # system python without the venv
    AppTest = None

from klg import config  # noqa: E402

APP = str(ROOT / "dashboard" / "app.py")
PAGES = ["Overview", "Findings", "Fix patches", "Real kernel code", "Live kernel", "Evaluation",
         "Run pipeline"]


@unittest.skipIf(AppTest is None, "streamlit not installed (use .venv/bin/python)")
class TestDashboard(unittest.TestCase):
    def app(self, page):
        at = AppTest.from_file(APP, default_timeout=60).run()
        at.sidebar.radio(key="page").set_value(page).run()
        return at

    def test_pages_render(self):
        for page in PAGES:
            at = self.app(page)
            self.assertEqual([e.value for e in at.exception], [], page)

    def test_findings_filters(self):
        at = self.app("Findings")
        if at.multiselect:
            at.multiselect[0].set_value(["✔ confirmed"]).run()
            self.assertEqual([e.value for e in at.exception], [])

    def test_run_button_starts_and_finishes(self):
        at = self.app("Run pipeline")
        at.selectbox[0].set_value("evaluate").run()
        run_btn = next(b for b in at.button if "Run" in b.label)
        run_btn.click().run()
        state = json.loads((config.RESULTS / "dashboard_run.json").read_text())
        self.assertEqual(state["step"], "evaluate")
        log = config.RESULTS / "dashboard_run.log"
        for _ in range(120):                                  # wait for the background run
            if "@@EXIT" in log.read_text():
                break
            time.sleep(0.5)
        text = log.read_text()
        self.assertIn("@@EXIT 0", text)
        self.assertIn("| hybrid", text)                       # evaluate printed its table
        at.run()
        self.assertTrue(any("exit code 0" in s.value for s in at.success))


if __name__ == "__main__":
    unittest.main()
