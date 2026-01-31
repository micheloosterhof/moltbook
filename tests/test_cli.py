# ABOUTME: Tests for the Moltbook CLI.
# ABOUTME: Verifies JSON output and command routing.

import json
import unittest
from io import StringIO
from unittest.mock import patch

from moltbook.cli import main


class TestCLIOutput(unittest.TestCase):
    """Test that CLI commands produce valid JSON output."""

    @patch("moltbook.cli.Moltbook")
    def test_feed_outputs_json(self, mock_cls):
        mock_client = mock_cls.return_value
        mock_client.feed.return_value = {"posts": [{"id": 1, "title": "Test"}]}

        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            main(["feed"])

        result = json.loads(mock_out.getvalue())
        self.assertEqual(result["posts"][0]["title"], "Test")

    @patch("moltbook.cli.Moltbook")
    def test_post_outputs_json(self, mock_cls):
        mock_client = mock_cls.return_value
        mock_client.post.return_value = {"post": {"id": 42, "title": "Hello"}}

        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            main(["post", "42"])

        result = json.loads(mock_out.getvalue())
        self.assertEqual(result["post"]["id"], 42)

    @patch("moltbook.cli.Moltbook")
    def test_me_outputs_json(self, mock_cls):
        mock_client = mock_cls.return_value
        mock_client.me.return_value = {"agent": {"name": "Eos"}}

        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            main(["me"])

        result = json.loads(mock_out.getvalue())
        self.assertEqual(result["agent"]["name"], "Eos")

    def test_no_args_prints_usage(self):
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            main([])

        output = mock_out.getvalue()
        self.assertIn("Usage:", output)
        self.assertIn("molt", output)

    @patch("moltbook.cli.Moltbook")
    def test_unknown_command_exits_nonzero(self, mock_cls):
        with self.assertRaises(SystemExit) as ctx:
            with patch("sys.stderr", new_callable=StringIO):
                main(["bogus"])
        self.assertNotEqual(ctx.exception.code, 0)


    @patch("moltbook.cli.Moltbook")
    def test_scan_outputs_text(self, mock_cls):
        mock_client = mock_cls.return_value
        mock_client.feed.return_value = {
            "posts": [
                {"id": "1", "title": "Hello", "author": "Eos",
                 "upvotes": 3, "comment_count": 1, "submolt": "general"},
            ]
        }

        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            main(["scan"])

        output = mock_out.getvalue().strip()
        self.assertIn("#1", output)
        self.assertIn("Hello", output)
        # Should NOT be JSON
        with self.assertRaises(json.JSONDecodeError):
            json.loads(output)

    @patch("moltbook.cli.Session")
    @patch("moltbook.cli.ConversationTracker")
    @patch("moltbook.cli.Moltbook")
    def test_brief_outputs_json(self, mock_cls, mock_tracker_cls, mock_session_cls):
        mock_session = mock_session_cls.return_value
        mock_session.start.return_value = {
            "feed_hot": [], "feed_new": [], "replies": []
        }

        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            main(["brief"])

        result = json.loads(mock_out.getvalue())
        self.assertIn("feed_hot", result)

    @patch("moltbook.cli.ConversationTracker")
    @patch("moltbook.cli.Moltbook")
    def test_watch_outputs_json(self, mock_cls, mock_tracker_cls):
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            main(["watch", "post-123"])

        result = json.loads(mock_out.getvalue())
        self.assertEqual(result["watched"], "post-123")
        mock_tracker_cls.return_value.watch.assert_called_once_with(
            "post-123", my_comment_id=None
        )


if __name__ == "__main__":
    unittest.main()
