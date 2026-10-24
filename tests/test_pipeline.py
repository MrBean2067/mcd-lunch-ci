import json
import tempfile
import unittest
from pathlib import Path

from mcd_lunch_ci.cli import load_team
from mcd_lunch_ci.pipeline import RunOptions, run
from mcd_lunch_ci.provider import SnapshotProvider

ROOT = Path(__file__).resolve().parent.parent


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self.team = load_team(ROOT / "examples" / "team.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_offline_run_produces_all_artifacts(self):
        ctx = run(self.team, SnapshotProvider(), RunOptions(mode="offline", out_dir=self.out))
        for name in ("lunch-report.md", "lunch-card.html", "plan.json"):
            self.assertTrue((self.out / name).exists(), name)
        self.assertEqual(len(ctx.stages), 7)
        self.assertTrue(ctx.order.dry_run)

    def test_report_marks_unverified_price(self):
        ctx = run(self.team, SnapshotProvider(), RunOptions(mode="offline", out_dir=self.out))
        report = (self.out / "lunch-report.md").read_text(encoding="utf-8")
        self.assertIn("推荐方案", report)
        self.assertIn("离线快照价", report)
        self.assertIn("calculate-price 核价", report)
        self.assertEqual(ctx.quote.verified, False)

    def test_plan_json_is_serialisable_and_consistent(self):
        run(self.team, SnapshotProvider(), RunOptions(mode="offline", out_dir=self.out))
        payload = json.loads((self.out / "plan.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["headcount"], 8)
        self.assertEqual(len(payload["members"]), 8)
        self.assertEqual(len(payload["frontier"]), 3)
        self.assertTrue(payload["order"]["dryRun"])

    def test_break_fast_items_excluded_at_lunch(self):
        ctx = run(self.team, SnapshotProvider(), RunOptions(mode="offline", out_dir=self.out))
        for assignment in ctx.result.best.assignments:
            self.assertNotIn("麦满分", assignment.combo.main.name)
            self.assertNotIn("热香饼", assignment.combo.main.name)

    def test_write_files_can_be_disabled(self):
        run(self.team, SnapshotProvider(), RunOptions(mode="offline", out_dir=self.out, write_files=False))
        self.assertEqual(list(self.out.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
