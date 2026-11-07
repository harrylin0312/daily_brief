import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree

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

    def test_new_categories_and_legacy_editions_are_compatible(self):
        for category in brief.CATEGORIES:
            issue = copy.deepcopy(self.issue)
            issue["stories"][0]["category"] = category
            brief.validate_issue(issue)
        self.assertEqual(brief.category_id(self.issue["stories"][0]), "tech")

    def test_list_is_compact_and_links_to_independent_detail(self):
        s = self.issue["stories"][0]
        output = brief.story_card(s, 1, self.issue["date"])
        self.assertIn("stories/2026-11-07/gpt-6-cyber.html", output)
        self.assertIn("了解更多", output)
        self.assertNotIn("<figure", output)
        self.assertNotIn('<p class="why">', output)
        self.assertNotIn("<details", output)

    def test_detail_has_original_facts_charts_sources_and_return_link(self):
        s = self.issue["stories"][0]
        output = brief.story_page(self.issue, s, brief.config())
        for value in (s["summary"], s["why"], s["limit"]):
            self.assertIn(brief.esc(value), output)
        self.assertIn("32.1%", output)
        self.assertIn("../../issues/2026-11-07.html#gpt-6-cyber", output)
        self.assertIn(s["sources"][0]["url"], output)
        self.assertIn("AI 生成概念圖", output)

    def test_custom_detail_is_searchable_and_escaped(self):
        s = self.issue["stories"][0]
        s["teaser"] = "一眼看懂重點。"
        s["details"] = [{"heading": "修補資訊", "points": ['測試用唯一關鍵字 <script>alert(1)</script>']}]
        brief.validate_issue(self.issue)
        card = brief.story_card(s, 1, self.issue["date"])
        self.assertIn("測試用唯一關鍵字", card)
        self.assertNotIn("<script>", card)
        detail = brief.story_page(self.issue, s, brief.config())
        self.assertIn("修補資訊", detail)
        self.assertNotIn("<script>alert", detail)

    def test_invalid_or_long_details_rejected(self):
        for details in ([], [{"heading": "", "points": ["test"]}], [{"heading": "test", "points": ["x" * 801]}]):
            with self.subTest(details=details):
                s = copy.deepcopy(self.issue)
                s["stories"][0]["details"] = details
                with self.assertRaises(ValueError):
                    brief.validate_issue(s)

    def test_images_are_optional_for_nonempty_editions(self):
        self.issue["hero"] = None
        brief.validate_issue(self.issue)
        output = brief.issue_page(self.issue, [self.issue], brief.config())
        self.assertNotIn("<img", output)

    def test_only_categories_with_stories_get_filter_buttons(self):
        self.issue["stories"][0]["category"] = "f1"
        output = brief.issue_page(self.issue, [self.issue], brief.config())
        self.assertIn('data-category="f1" aria-pressed', output)
        self.assertIn('data-category="tech" aria-pressed', output)
        self.assertNotIn('data-category="markets" aria-pressed', output)
        self.assertNotIn('data-category="security" aria-pressed', output)

    def test_cross_page_anchors_are_validated(self):
        output = brief.render(ROOT)
        path = "stories/2026-11-07/gpt-6-cyber.html"
        output[path] = output[path].replace("#gpt-6-cyber", "#nonexistent-story")
        with self.assertRaisesRegex(ValueError, "錨點不存在"):
            brief.validate_outputs(output, ROOT)

    def test_feed_links_to_each_detail_page(self):
        output = brief.render(ROOT)
        feed = ElementTree.fromstring(output["feed.xml"])
        links = feed.findall("{http://www.w3.org/2005/Atom}entry/{http://www.w3.org/2005/Atom}link")
        self.assertEqual(len(links), len(self.issue["stories"]))
        for link in links:
            relative = link.attrib["href"].removeprefix(brief.config()["url"])
            self.assertIn(relative, output)
            self.assertTrue(relative.startswith("stories/"))


if __name__ == "__main__":
    unittest.main()
