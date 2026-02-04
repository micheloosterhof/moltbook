# ABOUTME: Tests for the FeedCursor module.
# ABOUTME: Verifies mark_seen, unseen filtering, catch_up, and cap enforcement.

import tempfile
import unittest
from pathlib import Path

from moltbook.cursor import FeedCursor, _MAX_SEEN_PER_SOURCE


def _posts(n, start=1):
    return [{"id": str(i), "title": f"Post {i}"} for i in range(start, start + n)]


class TestFeedCursorBasic(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.path = Path(self.tmp.name)
        self.path.write_text("{}")

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def test_unseen_all_new(self):
        cursor = FeedCursor(self.path)
        posts = _posts(5)
        result = cursor.unseen(posts, source="hot")
        self.assertEqual(len(result), 5)

    def test_mark_seen_then_unseen(self):
        cursor = FeedCursor(self.path)
        posts = _posts(5)
        cursor.mark_seen(posts, source="hot")
        result = cursor.unseen(posts, source="hot")
        self.assertEqual(len(result), 0)

    def test_partial_unseen(self):
        cursor = FeedCursor(self.path)
        cursor.mark_seen(_posts(3), source="hot")
        all_posts = _posts(5)
        result = cursor.unseen(all_posts, source="hot")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["id"], "4")
        self.assertEqual(result[1]["id"], "5")

    def test_sources_are_independent(self):
        cursor = FeedCursor(self.path)
        posts = _posts(3)
        cursor.mark_seen(posts, source="hot")
        # Same posts should be unseen in "new" source
        result = cursor.unseen(posts, source="new")
        self.assertEqual(len(result), 3)

    def test_default_source(self):
        cursor = FeedCursor(self.path)
        posts = _posts(2)
        cursor.mark_seen(posts)
        result = cursor.unseen(posts)
        self.assertEqual(len(result), 0)


class TestFeedCursorCatchUp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.path = Path(self.tmp.name)
        self.path.write_text("{}")

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def test_catch_up_single_source(self):
        cursor = FeedCursor(self.path)
        cursor.mark_seen(_posts(3), source="hot")
        cursor.catch_up(source="hot")
        stats = cursor.stats()
        self.assertIsNotNone(stats["hot"]["last_checked"])

    def test_catch_up_all_sources(self):
        cursor = FeedCursor(self.path)
        cursor.mark_seen(_posts(2), source="hot")
        cursor.mark_seen(_posts(2), source="new")
        cursor.catch_up()
        stats = cursor.stats()
        self.assertIsNotNone(stats["hot"]["last_checked"])
        self.assertIsNotNone(stats["new"]["last_checked"])

    def test_catch_up_with_posts_marks_seen(self):
        cursor = FeedCursor(self.path)
        posts = _posts(5)
        cursor.catch_up(source="hot", posts=posts)
        result = cursor.unseen(posts, source="hot")
        self.assertEqual(len(result), 0)

    def test_catch_up_with_posts_no_source(self):
        cursor = FeedCursor(self.path)
        posts = _posts(3)
        cursor.catch_up(posts=posts)
        # Posts marked under "default" source
        result = cursor.unseen(posts, source="default")
        self.assertEqual(len(result), 0)


class TestFeedCursorReset(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.path = Path(self.tmp.name)
        self.path.write_text("{}")

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def test_reset_single_source(self):
        cursor = FeedCursor(self.path)
        cursor.mark_seen(_posts(5), source="hot")
        cursor.reset(source="hot")
        result = cursor.unseen(_posts(5), source="hot")
        self.assertEqual(len(result), 5)

    def test_reset_all(self):
        cursor = FeedCursor(self.path)
        cursor.mark_seen(_posts(3), source="hot")
        cursor.mark_seen(_posts(3), source="new")
        cursor.reset()
        self.assertEqual(cursor.stats(), {})


class TestFeedCursorCap(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.path = Path(self.tmp.name)
        self.path.write_text("{}")

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def test_cap_enforced(self):
        cursor = FeedCursor(self.path)
        posts = _posts(_MAX_SEEN_PER_SOURCE + 100)
        cursor.mark_seen(posts, source="hot")
        stats = cursor.stats()
        self.assertLessEqual(stats["hot"]["seen_count"], _MAX_SEEN_PER_SOURCE)

    def test_cap_keeps_newest_ids(self):
        cursor = FeedCursor(self.path)
        # Add old posts first
        old_posts = _posts(_MAX_SEEN_PER_SOURCE, start=1)
        cursor.mark_seen(old_posts, source="hot")
        # Add new posts that push past the cap
        new_posts = _posts(100, start=_MAX_SEEN_PER_SOURCE + 1)
        cursor.mark_seen(new_posts, source="hot")
        # The newest posts must survive the cap
        result = cursor.unseen(new_posts, source="hot")
        self.assertEqual(len(result), 0, "newest posts should be marked as seen")
        # Some of the oldest posts should have been evicted
        old_unseen = cursor.unseen(old_posts[:100], source="hot")
        self.assertTrue(len(old_unseen) > 0, "oldest posts should be evicted")


class TestFeedCursorSummary(unittest.TestCase):
    def test_empty_summary(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        tmp.close()
        path = Path(tmp.name)
        path.write_text("{}")
        cursor = FeedCursor(path)
        self.assertIn("No feed history", cursor.summary())
        path.unlink(missing_ok=True)

    def test_summary_with_data(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        tmp.close()
        path = Path(tmp.name)
        path.write_text("{}")
        cursor = FeedCursor(path)
        cursor.mark_seen(_posts(3), source="hot")
        s = cursor.summary()
        self.assertIn("hot", s)
        self.assertIn("3 seen", s)
        path.unlink(missing_ok=True)


class TestFeedCursorPersistence(unittest.TestCase):
    def test_persists_across_instances(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        tmp.close()
        path = Path(tmp.name)
        path.write_text("{}")
        cursor1 = FeedCursor(path)
        cursor1.mark_seen(_posts(3), source="hot")
        # New instance reads from same file
        cursor2 = FeedCursor(path)
        result = cursor2.unseen(_posts(3), source="hot")
        self.assertEqual(len(result), 0)
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
