# ABOUTME: Tests for the Moltbook helpers module.
# ABOUTME: Verifies summarize, filter, and extract functions.

import unittest

from moltbook.helpers import (
    summarize_post,
    summarize_posts,
    filter_posts,
    extract_comments,
)


SAMPLE_POST = {
    "id": "abc-123",
    "title": "Test Post",
    "content": "This is a long body that should be dropped in summary.",
    "url": "https://example.com",
    "author": {"id": "x", "name": "Eos", "karma": 33},
    "submolt": {"id": "y", "name": "general", "display_name": "General"},
    "upvotes": 5,
    "comment_count": 3,
    "created_at": "2026-01-31T00:00:00Z",
}

SAMPLE_POSTS = [
    {**SAMPLE_POST, "id": "1", "upvotes": 10, "author": {"name": "Eos"}},
    {**SAMPLE_POST, "id": "2", "upvotes": 2, "author": {"name": "Spotter"}},
    {**SAMPLE_POST, "id": "3", "upvotes": 0, "author": "Bot",
     "submolt": "dev"},
]


class TestSummarizePost(unittest.TestCase):

    def test_extracts_key_fields(self):
        s = summarize_post(SAMPLE_POST)
        self.assertEqual(s["id"], "abc-123")
        self.assertEqual(s["title"], "Test Post")
        self.assertEqual(s["author"], "Eos")
        self.assertEqual(s["submolt"], "general")
        self.assertEqual(s["upvotes"], 5)
        self.assertEqual(s["comment_count"], 3)

    def test_drops_content_and_url(self):
        s = summarize_post(SAMPLE_POST)
        self.assertNotIn("content", s)
        self.assertNotIn("url", s)

    def test_handles_string_author(self):
        post = {"id": "1", "author": "Bot", "title": "X"}
        s = summarize_post(post)
        self.assertEqual(s["author"], "Bot")

    def test_handles_missing_fields(self):
        s = summarize_post({"id": "1"})
        self.assertEqual(s["title"], "")
        self.assertEqual(s["author"], "unknown")
        self.assertEqual(s["upvotes"], 0)


class TestSummarizePosts(unittest.TestCase):

    def test_summarizes_list(self):
        result = summarize_posts(SAMPLE_POSTS)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["id"], "1")
        # Content should be stripped
        self.assertNotIn("content", result[0])


class TestFilterPosts(unittest.TestCase):

    def test_filter_by_min_upvotes(self):
        result = filter_posts(SAMPLE_POSTS, min_upvotes=3)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "1")

    def test_filter_by_authors(self):
        result = filter_posts(SAMPLE_POSTS, authors=["Eos"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "1")

    def test_filter_by_submolts(self):
        result = filter_posts(SAMPLE_POSTS, submolts=["dev"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "3")

    def test_filter_combined(self):
        result = filter_posts(SAMPLE_POSTS, min_upvotes=1, authors=["Eos", "Spotter"])
        self.assertEqual(len(result), 2)

    def test_no_filters_returns_all(self):
        result = filter_posts(SAMPLE_POSTS)
        self.assertEqual(len(result), 3)

    def test_does_not_mutate_input(self):
        original_len = len(SAMPLE_POSTS)
        filter_posts(SAMPLE_POSTS, min_upvotes=100)
        self.assertEqual(len(SAMPLE_POSTS), original_len)


class TestExtractComments(unittest.TestCase):

    COMMENTS = [
        {
            "id": "c1",
            "author": {"name": "Eos"},
            "content": "Top level",
            "upvotes": 2,
            "parent_id": None,
            "created_at": "2026-01-31T00:00:00Z",
            "replies": [
                {
                    "id": "c2",
                    "author": "Bot",
                    "content": "Reply",
                    "upvotes": 0,
                    "parent_id": "c1",
                    "created_at": "2026-01-31T00:01:00Z",
                    "replies": [],
                }
            ],
        },
        {
            "id": "c3",
            "author": {"name": "Spotter"},
            "content": "Another top",
            "upvotes": 1,
            "parent_id": None,
            "created_at": "2026-01-31T00:02:00Z",
            "replies": [],
        },
    ]

    def test_extract_preserves_tree(self):
        result = extract_comments(self.COMMENTS, flat=False)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["author"], "Eos")
        self.assertEqual(len(result[0]["replies"]), 1)
        self.assertEqual(result[0]["replies"][0]["author"], "Bot")

    def test_extract_flat(self):
        result = extract_comments(self.COMMENTS, flat=True)
        self.assertEqual(len(result), 3)
        ids = [c["id"] for c in result]
        self.assertEqual(ids, ["c1", "c2", "c3"])

    def test_normalizes_author_names(self):
        result = extract_comments(self.COMMENTS, flat=True)
        authors = [c["author"] for c in result]
        self.assertEqual(authors, ["Eos", "Bot", "Spotter"])


if __name__ == "__main__":
    unittest.main()
