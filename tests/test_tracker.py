# ABOUTME: Tests for the Moltbook conversation tracker.
# ABOUTME: Verifies state persistence, watch/unwatch, and reply detection.

import json
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from moltbook.tracker import ConversationTracker


def _make_tracker(state=None):
    """Create a tracker with a mocked client and in-memory state."""
    client = MagicMock()
    tracker = ConversationTracker.__new__(ConversationTracker)
    tracker.client = client
    tracker.state_path = Path("/tmp/claude/test_tracker.json")
    tracker._state = state or {"watched": {}}
    tracker._save = MagicMock()
    return tracker, client


class TestWatch(unittest.TestCase):

    def test_watch_adds_post(self):
        tracker, _ = _make_tracker()
        tracker.watch("post-1", my_comment_id="comment-1")
        self.assertIn("post-1", tracker.watched)
        self.assertIn("comment-1", tracker.watched["post-1"]["my_comment_ids"])
        tracker._save.assert_called()

    def test_watch_same_post_twice_adds_comment(self):
        tracker, _ = _make_tracker()
        tracker.watch("post-1", my_comment_id="c1")
        tracker.watch("post-1", my_comment_id="c2")
        self.assertEqual(
            tracker.watched["post-1"]["my_comment_ids"], ["c1", "c2"]
        )

    def test_watch_without_comment_id(self):
        tracker, _ = _make_tracker()
        tracker.watch("post-1")
        self.assertEqual(tracker.watched["post-1"]["my_comment_ids"], [])

    def test_unwatch_removes_post(self):
        tracker, _ = _make_tracker(
            {"watched": {"post-1": {"my_comment_ids": [], "seen_comment_ids": []}}}
        )
        tracker.unwatch("post-1")
        self.assertNotIn("post-1", tracker.watched)

    def test_unwatch_nonexistent_is_noop(self):
        tracker, _ = _make_tracker()
        tracker.unwatch("nope")  # should not raise


class TestCheckReplies(unittest.TestCase):

    def test_finds_new_comments(self):
        tracker, client = _make_tracker({
            "watched": {
                "post-1": {
                    "my_comment_ids": ["my-c1"],
                    "seen_comment_ids": ["old-c1", "my-c1"],
                }
            }
        })
        client.post.return_value = {
            "post": {"id": "post-1", "title": "Test"},
            "comments": [
                {"id": "old-c1", "author": "X", "content": "old", "replies": []},
                {"id": "my-c1", "author": "Eos", "content": "mine", "replies": []},
                {"id": "new-c1", "author": "Y", "content": "new reply", "replies": []},
            ],
        }

        results = tracker.check_replies()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["post_id"], "post-1")
        self.assertEqual(len(results[0]["new_comments"]), 1)
        self.assertEqual(results[0]["new_comments"][0]["id"], "new-c1")

    def test_excludes_own_comments_from_new(self):
        tracker, client = _make_tracker({
            "watched": {
                "post-1": {
                    "my_comment_ids": ["my-c1", "my-c2"],
                    "seen_comment_ids": [],
                }
            }
        })
        client.post.return_value = {
            "post": {"id": "post-1", "title": "Test"},
            "comments": [
                {"id": "my-c1", "author": "Eos", "content": "first", "replies": []},
                {"id": "my-c2", "author": "Eos", "content": "second", "replies": []},
            ],
        }

        results = tracker.check_replies()
        self.assertEqual(len(results), 0)

    def test_no_new_comments_returns_empty(self):
        tracker, client = _make_tracker({
            "watched": {
                "post-1": {
                    "my_comment_ids": ["my-c1"],
                    "seen_comment_ids": ["old-c1", "my-c1"],
                }
            }
        })
        client.post.return_value = {
            "post": {"id": "post-1", "title": "Test"},
            "comments": [
                {"id": "old-c1", "author": "X", "content": "old", "replies": []},
                {"id": "my-c1", "author": "Eos", "content": "mine", "replies": []},
            ],
        }

        results = tracker.check_replies()
        self.assertEqual(len(results), 0)

    def test_finds_nested_replies(self):
        tracker, client = _make_tracker({
            "watched": {
                "post-1": {
                    "my_comment_ids": ["my-c1"],
                    "seen_comment_ids": ["my-c1"],
                }
            }
        })
        client.post.return_value = {
            "post": {"id": "post-1", "title": "Test"},
            "comments": [
                {
                    "id": "my-c1",
                    "author": "Eos",
                    "content": "mine",
                    "replies": [
                        {"id": "reply-1", "author": "Y", "content": "response", "replies": []},
                    ],
                },
            ],
        }

        results = tracker.check_replies()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["new_comments"][0]["id"], "reply-1")

    def test_updates_seen_ids_after_check(self):
        tracker, client = _make_tracker({
            "watched": {
                "post-1": {
                    "my_comment_ids": ["my-c1"],
                    "seen_comment_ids": [],
                }
            }
        })
        client.post.return_value = {
            "post": {"id": "post-1", "title": "Test"},
            "comments": [
                {"id": "c1", "author": "X", "content": "hi", "replies": []},
                {"id": "my-c1", "author": "Eos", "content": "mine", "replies": []},
            ],
        }

        tracker.check_replies()
        seen = set(tracker._state["watched"]["post-1"]["seen_comment_ids"])
        self.assertIn("c1", seen)
        self.assertIn("my-c1", seen)

    def test_handles_api_error_gracefully(self):
        tracker, client = _make_tracker({
            "watched": {
                "post-1": {
                    "my_comment_ids": [],
                    "seen_comment_ids": [],
                }
            }
        })
        client.post.side_effect = Exception("Network error")

        results = tracker.check_replies()
        self.assertEqual(len(results), 0)


if __name__ == "__main__":
    unittest.main()
