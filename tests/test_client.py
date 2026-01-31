# ABOUTME: Tests for the Moltbook API client.
# ABOUTME: Verifies URL construction, headers, credential loading, and request building.

import json
import os
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch, MagicMock
from io import BytesIO

from moltbook.client import Moltbook, RateLimited, _resolve_api_key


def _make_client():
    """Create a Moltbook client with a fake API key, bypassing credential resolution."""
    with patch("moltbook.client._resolve_api_key", return_value="test_key"):
        return Moltbook()


class TestCredentialResolution(unittest.TestCase):
    """Test the credential resolution chain."""

    def test_env_var_takes_priority(self):
        with patch.dict(os.environ, {"MOLTBOOK_API_KEY": "env_key_123"}):
            client = Moltbook()
        self.assertEqual(client.api_key, "env_key_123")

    def test_config_dir_credentials(self):
        config_path = Path.home() / ".config" / "moltbook" / "credentials.json"
        creds = json.dumps({"api_key": "config_key_456"})

        def fake_read_text(self_path):
            if self_path == config_path:
                return creds
            raise FileNotFoundError

        with patch.dict(os.environ, {}, clear=True):
            env = os.environ.copy()
            env.pop("MOLTBOOK_API_KEY", None)
            with patch.dict(os.environ, env, clear=True):
                with patch.object(Path, "read_text", fake_read_text):
                    key = _resolve_api_key()
        self.assertEqual(key, "config_key_456")

    def test_cwd_credentials(self):
        config_path = Path.home() / ".config" / "moltbook" / "credentials.json"
        cwd_path = Path.cwd() / "credentials.json"
        creds = json.dumps({"api_key": "cwd_key_789"})

        def fake_read_text(self_path):
            if self_path == cwd_path:
                return creds
            raise FileNotFoundError

        with patch.dict(os.environ, {}, clear=True):
            env = os.environ.copy()
            env.pop("MOLTBOOK_API_KEY", None)
            with patch.dict(os.environ, env, clear=True):
                with patch.object(Path, "read_text", fake_read_text):
                    key = _resolve_api_key()
        self.assertEqual(key, "cwd_key_789")

    def test_explicit_path(self):
        creds = json.dumps({"api_key": "explicit_key"})

        def fake_read_text(self_path):
            if self_path == Path("/custom/creds.json"):
                return creds
            raise FileNotFoundError

        with patch.dict(os.environ, {}, clear=True):
            env = os.environ.copy()
            env.pop("MOLTBOOK_API_KEY", None)
            with patch.dict(os.environ, env, clear=True):
                with patch.object(Path, "read_text", fake_read_text):
                    client = Moltbook(credentials_path="/custom/creds.json")
        self.assertEqual(client.api_key, "explicit_key")

    def test_raises_when_no_credentials_found(self):
        with patch.dict(os.environ, {}, clear=True):
            env = os.environ.copy()
            env.pop("MOLTBOOK_API_KEY", None)
            with patch.dict(os.environ, env, clear=True):
                with patch.object(Path, "read_text", side_effect=FileNotFoundError):
                    with self.assertRaises(FileNotFoundError) as ctx:
                        Moltbook()
        self.assertIn("No Moltbook credentials found", str(ctx.exception))


class TestMoltbookURLs(unittest.TestCase):
    """Test that API methods build correct URLs and parameters."""

    def setUp(self):
        self.client = _make_client()

    def test_base_url(self):
        self.assertEqual(self.client.base_url, "https://www.moltbook.com/api/v1")

    def test_headers_include_api_key(self):
        headers = self.client._headers()
        self.assertEqual(headers["Authorization"], "Bearer test_key")
        self.assertEqual(headers["Content-Type"], "application/json")

    @patch("moltbook.client.Moltbook._request")
    def test_feed_default_params(self, mock_req):
        mock_req.return_value = {"posts": []}
        self.client.feed()
        mock_req.assert_called_once_with(
            "GET", "/feed", params={"sort": "hot", "limit": 25}
        )

    @patch("moltbook.client.Moltbook._request")
    def test_feed_custom_params(self, mock_req):
        mock_req.return_value = {"posts": []}
        self.client.feed(sort="new", limit=10)
        mock_req.assert_called_once_with(
            "GET", "/feed", params={"sort": "new", "limit": 10}
        )

    @patch("moltbook.client.Moltbook._request")
    def test_posts_builds_correct_path(self, mock_req):
        mock_req.return_value = {"posts": []}
        self.client.posts("general")
        mock_req.assert_called_once_with(
            "GET",
            "/submolts/general/posts",
            params={"sort": "hot", "limit": 25, "offset": 0},
        )

    @patch("moltbook.client.Moltbook._request")
    def test_post_by_id(self, mock_req):
        mock_req.return_value = {"post": {}}
        self.client.post(42)
        mock_req.assert_called_once_with("GET", "/posts/42")

    @patch("moltbook.client.Moltbook._request")
    def test_create_post(self, mock_req):
        mock_req.return_value = {"post": {}}
        self.client.create_post("general", "Title", "Body text")
        mock_req.assert_called_once_with(
            "POST",
            "/posts",
            body={
                "title": "Title",
                "content": "Body text",
                "submolt": "general",
            },
        )

    @patch("moltbook.client.Moltbook._request")
    def test_create_post_with_url(self, mock_req):
        mock_req.return_value = {"post": {}}
        self.client.create_post("general", "Title", "Body", url="https://example.com")
        mock_req.assert_called_once_with(
            "POST",
            "/posts",
            body={
                "title": "Title",
                "content": "Body",
                "submolt": "general",
                "url": "https://example.com",
            },
        )

    @patch("moltbook.client.Moltbook._request")
    def test_comment(self, mock_req):
        mock_req.return_value = {}
        self.client.comment(42, "Nice post")
        mock_req.assert_called_once_with(
            "POST",
            "/posts/42/comments",
            body={
                "content": "Nice post",
            },
        )

    @patch("moltbook.client.Moltbook._request")
    def test_comment_with_parent(self, mock_req):
        mock_req.return_value = {}
        self.client.comment(42, "Reply", parent_id=7)
        mock_req.assert_called_once_with(
            "POST",
            "/posts/42/comments",
            body={
                "content": "Reply",
                "parent_id": 7,
            },
        )

    @patch("moltbook.client.Moltbook._request")
    def test_upvote(self, mock_req):
        mock_req.return_value = {}
        self.client.upvote(42)
        mock_req.assert_called_once_with("POST", "/posts/42/upvote")

    @patch("moltbook.client.Moltbook._request")
    def test_downvote(self, mock_req):
        mock_req.return_value = {}
        self.client.downvote(42)
        mock_req.assert_called_once_with("POST", "/posts/42/downvote")

    @patch("moltbook.client.Moltbook._request")
    def test_upvote_comment(self, mock_req):
        mock_req.return_value = {}
        self.client.upvote_comment(99)
        mock_req.assert_called_once_with("POST", "/comments/99/upvote")

    @patch("moltbook.client.Moltbook._request")
    def test_submolts(self, mock_req):
        mock_req.return_value = {"submolts": []}
        self.client.submolts()
        mock_req.assert_called_once_with("GET", "/submolts")

    @patch("moltbook.client.Moltbook._request")
    def test_search(self, mock_req):
        mock_req.return_value = {"results": []}
        self.client.search("honeypot")
        mock_req.assert_called_once_with("GET", "/search", params={"q": "honeypot"})

    @patch("moltbook.client.Moltbook._request")
    def test_me(self, mock_req):
        mock_req.return_value = {"agent": {}}
        self.client.me()
        mock_req.assert_called_once_with("GET", "/me")

    @patch("moltbook.client.Moltbook._request")
    def test_profile(self, mock_req):
        mock_req.return_value = {"agent": {}}
        self.client.profile("Eos")
        mock_req.assert_called_once_with("GET", "/agents/Eos")

    @patch("moltbook.client.Moltbook._request")
    def test_status(self, mock_req):
        mock_req.return_value = {}
        self.client.status()
        mock_req.assert_called_once_with("GET", "/claim/status")

    @patch("moltbook.client.Moltbook._request")
    def test_update_profile(self, mock_req):
        mock_req.return_value = {}
        self.client.update_profile("I watch honeypots")
        mock_req.assert_called_once_with(
            "PUT",
            "/me",
            body={
                "description": "I watch honeypots",
            },
        )


class TestMoltbookRetry(unittest.TestCase):
    """Test rate limit retry behavior."""

    def setUp(self):
        self.client = _make_client()

    def _make_429_error(self, retry_after=None):
        headers = {}
        if retry_after is not None:
            headers["Retry-After"] = str(retry_after)
        resp = MagicMock()
        resp.code = 429
        resp.headers = headers
        return urllib.error.HTTPError(
            "https://example.com",
            429,
            "Too Many Requests",
            resp.headers,
            BytesIO(b""),
        )

    @patch("moltbook.client.time.sleep")
    @patch("urllib.request.urlopen")
    def test_retries_on_429_then_succeeds(self, mock_urlopen, mock_sleep):
        success_resp = MagicMock()
        success_resp.read.return_value = json.dumps({"ok": True}).encode()
        success_resp.__enter__ = lambda s: s
        success_resp.__exit__ = MagicMock(return_value=False)

        mock_urlopen.side_effect = [self._make_429_error(retry_after=5), success_resp]
        result = self.client._request("GET", "/feed")
        self.assertEqual(result, {"ok": True})
        mock_sleep.assert_called_once_with(5)

    @patch("moltbook.client.time.sleep")
    @patch("urllib.request.urlopen")
    def test_raises_after_max_retries(self, mock_urlopen, mock_sleep):
        mock_urlopen.side_effect = [
            self._make_429_error(retry_after=1),
            self._make_429_error(retry_after=1),
            self._make_429_error(retry_after=1),
        ]
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.client._request("GET", "/feed")
        self.assertEqual(ctx.exception.code, 429)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("moltbook.client.time.sleep")
    @patch("urllib.request.urlopen")
    def test_uses_default_delay_when_no_retry_after_header(
        self, mock_urlopen, mock_sleep
    ):
        success_resp = MagicMock()
        success_resp.read.return_value = json.dumps({"ok": True}).encode()
        success_resp.__enter__ = lambda s: s
        success_resp.__exit__ = MagicMock(return_value=False)

        mock_urlopen.side_effect = [self._make_429_error(), success_resp]
        self.client._request("GET", "/feed")
        mock_sleep.assert_called_once_with(10)

    @patch("urllib.request.urlopen")
    def test_does_not_retry_on_other_errors(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://example.com",
            500,
            "Server Error",
            {},
            BytesIO(b""),
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.client._request("GET", "/feed")
        self.assertEqual(ctx.exception.code, 500)
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch("urllib.request.urlopen")
    def test_raises_rate_limited_on_post_cooldown(self, mock_urlopen):
        body = json.dumps(
            {
                "success": False,
                "error": "Rate limit exceeded",
                "retry_after_minutes": 25,
            }
        ).encode()
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://example.com",
            429,
            "Too Many Requests",
            {},
            BytesIO(body),
        )
        with self.assertRaises(RateLimited) as ctx:
            self.client._request("POST", "/posts")
        self.assertEqual(ctx.exception.retry_after_seconds, 25 * 60)
        self.assertIn("25 minute", str(ctx.exception))

    @patch("urllib.request.urlopen")
    def test_rate_limited_does_not_retry(self, mock_urlopen):
        body = json.dumps(
            {
                "success": False,
                "retry_after_minutes": 30,
            }
        ).encode()
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://example.com",
            429,
            "Too Many Requests",
            {},
            BytesIO(body),
        )
        with self.assertRaises(RateLimited):
            self.client._request("POST", "/posts")
        self.assertEqual(mock_urlopen.call_count, 1)


if __name__ == "__main__":
    unittest.main()
