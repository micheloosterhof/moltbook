# ABOUTME: Tests for the Moltbook Session module.
# ABOUTME: Verifies session briefing, compact post reading, and comment-and-watch.

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from moltbook.cursor import FeedCursor
from moltbook.rules import FeedRules
from moltbook.session import Session


class TestSessionStart(unittest.TestCase):
    def _make_session(self, tracker=None):
        client = MagicMock()
        client.feed.return_value = {
            "posts": [
                {
                    "id": "1",
                    "title": "Hot Post",
                    "author": {"name": "Eos"},
                    "submolt": {"name": "general"},
                    "upvotes": 5,
                    "comment_count": 2,
                    "created_at": "2026-01-31T00:00:00Z",
                    "content": "body",
                },
            ]
        }
        return Session(client, tracker), client

    def test_start_returns_feeds(self):
        session, client = self._make_session()
        brief = session.start()
        self.assertIn("feed_hot", brief)
        self.assertIn("feed_new", brief)
        self.assertEqual(len(brief["feed_hot"]), 1)
        self.assertEqual(brief["feed_hot"][0]["id"], "1")
        # Content should be stripped (summarized)
        self.assertNotIn("content", brief["feed_hot"][0])

    def test_start_without_tracker(self):
        session, _ = self._make_session()
        brief = session.start()
        self.assertEqual(brief["replies"], [])

    def test_start_with_tracker(self):
        tracker = MagicMock()
        tracker.check_replies.return_value = [{"post_id": "p1", "new_comments": []}]
        session, _ = self._make_session(tracker=tracker)
        brief = session.start()
        self.assertEqual(len(brief["replies"]), 1)
        tracker.check_replies.assert_called_once()

    def test_start_custom_limit(self):
        session, client = self._make_session()
        session.start(feed_limit=10)
        for call in client.feed.call_args_list:
            self.assertEqual(call.kwargs["limit"], 10)


class TestSessionRulesIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp_rules = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp_rules.close()
        self.rules_path = Path(self.tmp_rules.name)
        self.rules_path.write_text("{}")
        self.tmp_cursor = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp_cursor.close()
        self.cursor_path = Path(self.tmp_cursor.name)
        self.cursor_path.write_text("{}")

    def tearDown(self):
        self.rules_path.unlink(missing_ok=True)
        self.cursor_path.unlink(missing_ok=True)

    def _make_client(self):
        client = MagicMock()
        client.feed.return_value = {
            "posts": [
                {
                    "id": "1",
                    "title": "Good Post",
                    "author": {"name": "alice"},
                    "submolt": {"name": "general"},
                    "upvotes": 5,
                    "comment_count": 2,
                    "created_at": "2026-01-31T00:00:00Z",
                    "content": "body",
                },
                {
                    "id": "2",
                    "title": "test post please ignore",
                    "author": {"name": "bob"},
                    "submolt": {"name": "general"},
                    "upvotes": 0,
                    "comment_count": 0,
                    "created_at": "2026-01-31T00:00:00Z",
                    "content": "nothing",
                },
            ]
        }
        return client

    def test_rules_kill_posts_in_brief(self):
        rules = FeedRules(self.rules_path)
        rules.add("kill", "title", "test post")
        client = self._make_client()
        session = Session(client, feed_rules=rules)
        brief = session.start()
        # Killed post should be excluded from feed_hot
        self.assertEqual(len(brief["feed_hot"]), 1)
        self.assertEqual(brief["feed_hot"][0]["id"], "1")
        self.assertEqual(brief["killed_count"], 2)  # 1 per feed (hot + new)

    def test_cursor_tracks_unseen_in_brief(self):
        cursor = FeedCursor(self.cursor_path)
        client = self._make_client()
        # First session: everything is unseen
        session = Session(client, feed_cursor=cursor)
        brief1 = session.start()
        self.assertEqual(brief1["unseen_hot_count"], 2)
        # Second session: same posts are now seen
        session2 = Session(client, feed_cursor=cursor)
        brief2 = session2.start()
        self.assertEqual(brief2["unseen_hot_count"], 0)

    def test_select_rule_populates_selected(self):
        rules = FeedRules(self.rules_path)
        rules.add("select", "author", "alice")
        client = self._make_client()
        session = Session(client, feed_rules=rules)
        brief = session.start()
        self.assertTrue(len(brief["selected"]) > 0)
        self.assertTrue(all(s["id"] == "1" for s in brief["selected"]))


class TestSessionReadPost(unittest.TestCase):
    def test_read_post_returns_flat_comments(self):
        client = MagicMock()
        client.post.return_value = {
            "post": {
                "id": "p1",
                "title": "Test",
                "content": "Body",
                "author": {"name": "Eos"},
                "upvotes": 3,
            },
            "comments": [
                {
                    "id": "c1",
                    "author": {"name": "Bot"},
                    "content": "Hi",
                    "upvotes": 1,
                    "parent_id": None,
                    "created_at": "",
                    "replies": [
                        {
                            "id": "c2",
                            "author": "Sub",
                            "content": "Reply",
                            "upvotes": 0,
                            "parent_id": "c1",
                            "created_at": "",
                            "replies": [],
                        }
                    ],
                },
            ],
        }
        session = Session(client)
        result = session.read_post("p1")
        self.assertEqual(result["id"], "p1")
        self.assertEqual(result["author"], "Eos")
        # Comments should be flat
        self.assertEqual(len(result["comments"]), 2)
        self.assertEqual(result["comments"][0]["id"], "c1")
        self.assertEqual(result["comments"][1]["id"], "c2")


class TestSessionMyRecentPosts(unittest.TestCase):
    def test_returns_summarized_posts(self):
        client = MagicMock()
        client.me.return_value = {"agent": {"name": "Eos"}}
        client.profile.return_value = {
            "posts": [
                {
                    "id": "p1",
                    "title": "First",
                    "author": {"name": "Eos"},
                    "submolt": {"name": "general"},
                    "upvotes": 5,
                    "comment_count": 2,
                    "created_at": "2026-01-31",
                    "content": "long body here",
                },
                {
                    "id": "p2",
                    "title": "Second",
                    "author": {"name": "Eos"},
                    "submolt": {"name": "dev"},
                    "upvotes": 1,
                    "comment_count": 0,
                    "created_at": "2026-01-30",
                    "content": "another body",
                },
            ]
        }
        session = Session(client)
        result = session.my_recent_posts()
        self.assertEqual(len(result), 2)
        self.assertNotIn("content", result[0])
        self.assertEqual(result[0]["id"], "p1")
        client.profile.assert_called_once_with("Eos")

    def test_respects_limit(self):
        client = MagicMock()
        client.me.return_value = {"agent": {"name": "Eos"}}
        client.profile.return_value = {
            "posts": [{"id": str(i), "title": f"Post {i}"} for i in range(20)]
        }
        session = Session(client)
        result = session.my_recent_posts(limit=5)
        self.assertEqual(len(result), 5)

    def test_empty_when_no_name(self):
        client = MagicMock()
        client.me.return_value = {}
        session = Session(client)
        result = session.my_recent_posts()
        self.assertEqual(result, [])


class TestSessionCommentAndWatch(unittest.TestCase):
    def test_comments_and_watches(self):
        client = MagicMock()
        client.comment.return_value = {"comment": {"id": "new-c", "content": "Hello"}}
        tracker = MagicMock()
        session = Session(client, tracker)

        result = session.comment_and_watch("p1", "Hello")

        client.comment.assert_called_once_with("p1", "Hello", parent_id=None)
        tracker.watch.assert_called_once_with("p1", my_comment_id="new-c")
        self.assertEqual(result["comment"]["id"], "new-c")

    def test_comments_without_tracker(self):
        client = MagicMock()
        client.comment.return_value = {"comment": {"id": "c1"}}
        session = Session(client)
        result = session.comment_and_watch("p1", "Hi")
        client.comment.assert_called_once()
        self.assertEqual(result["comment"]["id"], "c1")

    def test_reply_passes_parent_id(self):
        client = MagicMock()
        client.comment.return_value = {"comment": {"id": "c2"}}
        tracker = MagicMock()
        session = Session(client, tracker)

        session.comment_and_watch("p1", "Reply", parent_id="c1")
        client.comment.assert_called_once_with("p1", "Reply", parent_id="c1")


if __name__ == "__main__":
    unittest.main()
