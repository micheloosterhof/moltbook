# ABOUTME: Tests for the FeedRules module.
# ABOUTME: Verifies rule matching (substring, regex, expiry, submolt scoping) and apply/prune.

import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from moltbook.rules import FeedRules


def _post(title="Hello", author="alice", submolt="general", pid="1"):
    return {
        "id": pid,
        "title": title,
        "author": {"name": author},
        "submolt": {"name": submolt},
        "upvotes": 1,
    }


class TestFeedRulesAddRemove(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.path = Path(self.tmp.name)
        self.path.write_text("{}")

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def test_add_kill_rule(self):
        rules = FeedRules(self.path)
        rules.add("kill", "title", "spam")
        self.assertEqual(len(rules.rules), 1)
        self.assertEqual(rules.rules[0]["action"], "kill")
        self.assertEqual(rules.rules[0]["pattern"], "spam")

    def test_add_select_rule_with_submolts(self):
        rules = FeedRules(self.path)
        rules.add("select", "author", "bicep", submolts=["general"])
        r = rules.rules[0]
        self.assertEqual(r["submolts"], ["general"])

    def test_add_with_expiry(self):
        rules = FeedRules(self.path)
        rules.add("kill", "title", "temp", expires_days=30)
        r = rules.rules[0]
        self.assertIsNotNone(r["expires"])

    def test_remove_rule(self):
        rules = FeedRules(self.path)
        rules.add("kill", "title", "a")
        rules.add("kill", "title", "b")
        rules.remove(0)
        self.assertEqual(len(rules.rules), 1)
        self.assertEqual(rules.rules[0]["pattern"], "b")

    def test_invalid_action(self):
        rules = FeedRules(self.path)
        with self.assertRaises(ValueError):
            rules.add("mute", "title", "x")

    def test_invalid_field(self):
        rules = FeedRules(self.path)
        with self.assertRaises(ValueError):
            rules.add("kill", "body", "x")


class TestFeedRulesMatching(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.path = Path(self.tmp.name)
        self.path.write_text("{}")

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def test_substring_match_title(self):
        rules = FeedRules(self.path)
        rules.add("kill", "title", "test post")
        result = rules.apply([_post(title="This is a test post please ignore")])
        self.assertEqual(len(result["killed"]), 1)
        self.assertEqual(len(result["keep"]), 0)

    def test_substring_case_insensitive(self):
        rules = FeedRules(self.path)
        rules.add("kill", "title", "SPAM")
        result = rules.apply([_post(title="this is spam")])
        self.assertEqual(len(result["killed"]), 1)

    def test_regex_match(self):
        rules = FeedRules(self.path)
        rules.add("kill", "title", r"/^test\s+\d+/")
        result = rules.apply(
            [
                _post(title="test 123", pid="1"),
                _post(title="not matching", pid="2"),
            ]
        )
        self.assertEqual(len(result["killed"]), 1)
        self.assertEqual(result["killed"][0]["id"], "1")

    def test_author_match(self):
        rules = FeedRules(self.path)
        rules.add("kill", "author", "spambot")
        result = rules.apply(
            [
                _post(author="spambot", pid="1"),
                _post(author="alice", pid="2"),
            ]
        )
        self.assertEqual(len(result["killed"]), 1)
        self.assertEqual(len(result["keep"]), 1)

    def test_submolt_scoping(self):
        rules = FeedRules(self.path)
        rules.add("kill", "author", "bob", submolts=["offtopic"])
        result = rules.apply(
            [
                _post(author="bob", submolt="general", pid="1"),
                _post(author="bob", submolt="offtopic", pid="2"),
            ]
        )
        # Only the offtopic post should be killed
        self.assertEqual(len(result["killed"]), 1)
        self.assertEqual(result["killed"][0]["id"], "2")
        self.assertEqual(len(result["keep"]), 1)

    def test_select_rule(self):
        rules = FeedRules(self.path)
        rules.add("select", "author", "bicep")
        result = rules.apply(
            [
                _post(author="bicep", pid="1"),
                _post(author="alice", pid="2"),
            ]
        )
        self.assertEqual(len(result["selected"]), 1)
        # Selected posts are also in keep
        self.assertIn(result["selected"][0], result["keep"])
        self.assertEqual(len(result["keep"]), 2)

    def test_kill_overrides_select(self):
        rules = FeedRules(self.path)
        rules.add("select", "author", "bob")
        rules.add("kill", "title", "spam")
        result = rules.apply([_post(author="bob", title="spam post")])
        self.assertEqual(len(result["killed"]), 1)
        self.assertEqual(len(result["selected"]), 0)


class TestFeedRulesPrune(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.path = Path(self.tmp.name)

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def test_prune_removes_expired(self):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        data = {
            "rules": [
                {
                    "action": "kill",
                    "field": "title",
                    "pattern": "old",
                    "submolts": None,
                    "created": past,
                    "expires": past,
                },
                {
                    "action": "kill",
                    "field": "title",
                    "pattern": "new",
                    "submolts": None,
                    "created": past,
                    "expires": future,
                },
            ]
        }
        self.path.write_text(json.dumps(data))
        rules = FeedRules(self.path)
        self.assertEqual(len(rules.rules), 1)
        self.assertEqual(rules.rules[0]["pattern"], "new")

    def test_permanent_rules_not_pruned(self):
        data = {
            "rules": [
                {
                    "action": "kill",
                    "field": "title",
                    "pattern": "perm",
                    "submolts": None,
                    "created": "2026-01-01T00:00:00+00:00",
                    "expires": None,
                },
            ]
        }
        self.path.write_text(json.dumps(data))
        rules = FeedRules(self.path)
        self.assertEqual(len(rules.rules), 1)


class TestFeedRulesComments(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.path = Path(self.tmp.name)
        self.path.write_text("{}")

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def test_kill_comments_by_author(self):
        rules = FeedRules(self.path)
        rules.add("kill", "author", "spammer")
        comments = [
            {
                "id": "c1",
                "author": {"name": "spammer"},
                "content": "Buy now!",
                "replies": [
                    {
                        "id": "c2",
                        "author": {"name": "alice"},
                        "content": "No",
                        "replies": [],
                    }
                ],
            },
            {"id": "c3", "author": {"name": "bob"}, "content": "Hello", "replies": []},
        ]
        result = rules.apply_comments(comments)
        ids = [c["id"] for c in result]
        self.assertNotIn("c1", ids)
        self.assertIn("c2", ids)  # promoted
        self.assertIn("c3", ids)


class TestFeedRulesSummary(unittest.TestCase):
    def test_empty_summary(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        tmp.close()
        path = Path(tmp.name)
        path.write_text("{}")
        rules = FeedRules(path)
        self.assertIn("No feed rules", rules.summary())
        path.unlink(missing_ok=True)

    def test_summary_with_rules(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        tmp.close()
        path = Path(tmp.name)
        path.write_text("{}")
        rules = FeedRules(path)
        rules.add("kill", "title", "spam")
        s = rules.summary()
        self.assertIn("kill", s)
        self.assertIn("spam", s)
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
