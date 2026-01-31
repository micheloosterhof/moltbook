# ABOUTME: Tests for the Moltbook Session module.
# ABOUTME: Verifies session briefing, compact post reading, and comment-and-watch.

import unittest
from unittest.mock import MagicMock

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
