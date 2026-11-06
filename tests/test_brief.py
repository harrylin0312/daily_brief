import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("brief", ROOT / "scripts/brief.py")
brief = importlib.util.module_from_spec(spec)
spec.loader.exec_module(brief)


class BriefTests(unittest.TestCase):
    def setUp(self):
        self.issue = json.loads((ROOT / "content/issues/2026-11-07.json").read_text())

    def test_real_issue_and_all_generated_links(self):
        output = brief.render(ROOT)
        brief.validate_outputs(output, ROOT)
        self.assertIn("issues/2026-11-07.html", output)

    def test_duplicate_story_rejected(self):
        self.issue["stories"].append(copy.deepcopy(self.issue["stories"][0]))
        with self.assertRaises(ValueError):
            brief.validate_issue(self.issue)

    def test_missing_image_rejected(self):
        self.issue["hero"]["image"] = "assets/missing.jpg"
        with self.assertRaisesRegex(ValueError, "資產不存在"):
            brief.validate_issue(self.issue)

    def test_source_failure_cannot_be_no_news(self):
        for check in self.issue["source_checks"]:
            check["status"] = "failed"
        self.issue["stories"] = []
        self.issue["empty_reason"] = "沒有新聞"
        with self.assertRaisesRegex(ValueError, "來源成功查核"):
            brief.validate_issue(self.issue)

    def test_empty_issue_after_successful_research_is_supported(self):
        self.issue["stories"] = []
        self.issue["hero"] = None
        self.issue["empty_reason"] = "已查核來源，未找到值得新增的重大消息。"
        brief.validate_issue(self.issue)
        output = brief.issue_page(self.issue, [self.issue], brief.config())
        self.assertIn(self.issue["empty_reason"], output)

    def test_unsafe_sources_and_asset_traversal_rejected(self):
        with self.assertRaises(ValueError):
            brief.valid_url("javascript:alert(1)")
        with self.assertRaises(ValueError):
            brief.local_asset("../../README.md", ROOT)

    def test_stories_escape_markup(self):
        s = self.issue["stories"][0]
        s["title"] = '<script>alert("x")</script>'
        output = brief.story_card(s, 1)
        self.assertNotIn("<script>", output)
        self.assertIn("&lt;script&gt;", output)

    def test_invalid_data_does_not_replace_existing_homepage(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "content/issues").mkdir(parents=True)
            (root / "index.html").write_text("previous good edition")
            (root / "content/issues/2026-11-07.json").write_text('{"date":"broken"}')
            with self.assertRaises(ValueError):
                brief.build(root)
            self.assertEqual((root / "index.html").read_text(), "previous good edition")

    def test_build_is_deterministic(self):
        self.assertEqual(brief.render(ROOT), brief.render(ROOT))

    def test_second_run_does_not_change_files(self):
        paths = [ROOT / p for p in brief.render(ROOT)]
        before = {str(p): p.read_bytes() for p in paths}
        brief.build(ROOT)
        self.assertEqual(before, {str(p): p.read_bytes() for p in paths})

    def test_parallel_publish_lock_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with brief.lock(Path(folder)):
                with self.assertRaisesRegex(ValueError, "正在執行"):
                    with brief.lock(Path(folder)):
                        self.fail("should not acquire second lock")

    def test_publish_refuses_staged_user_changes_before_network(self):
        cfg = brief.config()
        calls = []
        def fake_run(*args, **kwargs):
            calls.append(args)
            if args[:3] == ("git", "rev-parse", "--show-toplevel"):
                return str(ROOT)
            if args[:3] == ("git", "remote", "get-url"):
                return cfg["repository"]
            if args[:3] == ("git", "branch", "--show-current"):
                return cfg["branch"]
            if args[:3] == ("git", "diff", "--cached"):
                return "user-work.txt"
            self.fail(f"Unexpected command: {args}")
        with patch.object(brief, "run", fake_run):
            with self.assertRaisesRegex(ValueError, "暫存變更"):
                brief.publish()
        self.assertFalse(any("push" in c or "fetch" in c for c in calls))

    def test_403_requires_recent_editor_verification(self):
        s = self.issue["stories"][0]["sources"][0]
        s.pop("verification_method")
        with patch.object(brief, "load_issues", return_value=[self.issue]), patch.object(brief, "run", return_value="403"):
            with self.assertRaisesRegex(ValueError, "替代查核證據"):
                brief.check_links()

    def test_future_source_rejected(self):
        self.issue["stories"][0]["sources"][0]["published"] = "2099-01-01"
        with self.assertRaisesRegex(ValueError, "超出刊期"):
            brief.validate_issue(self.issue)


if __name__ == "__main__":
    unittest.main()
