# ABOUTME: API client for Moltbook, the agent social network.
# ABOUTME: Handles authentication, request building, and JSON parsing for all endpoints.

import json
import os
import time
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

MAX_RETRIES = 3
RETRY_DELAY = 10


class RateLimited(Exception):
    """Raised when a long cooldown (e.g. post rate limit) makes retry impractical."""

    def __init__(self, retry_after_seconds, body=None):
        self.retry_after_seconds = retry_after_seconds
        self.body = body or {}
        minutes = retry_after_seconds // 60
        super().__init__(f"Rate limited. Try again in {minutes} minute(s).")


def _parse_error_body(http_error):
    """Try to parse JSON from an HTTPError response body."""
    try:
        return json.loads(http_error.read())
    except (json.JSONDecodeError, OSError):
        return {}


def _resolve_api_key(credentials_path=None):
    """Resolve the API key from environment, config files, or explicit path.

    Search order:
    1. MOLTBOOK_API_KEY environment variable
    2. ~/.config/moltbook/credentials.json
    3. ./credentials.json (current working directory)
    4. Explicit credentials_path parameter
    """
    env_key = os.environ.get("MOLTBOOK_API_KEY")
    if env_key:
        return env_key

    candidates = [
        Path.home() / ".config" / "moltbook" / "credentials.json",
        Path.cwd() / "credentials.json",
    ]
    if credentials_path is not None:
        candidates.append(Path(credentials_path))

    for path in candidates:
        try:
            creds = json.loads(path.read_text())
            return creds["api_key"]
        except (FileNotFoundError, KeyError, json.JSONDecodeError):
            continue

    raise FileNotFoundError(
        "No Moltbook credentials found. Set MOLTBOOK_API_KEY or place "
        "credentials.json in ~/.config/moltbook/ or the current directory."
    )


class Moltbook:
    """Client for the Moltbook API.

    Usage::

        from moltbook import Moltbook

        client = Moltbook()
        posts = client.feed()
    """

    base_url = "https://www.moltbook.com/api/v1"

    def __init__(self, credentials_path=None):
        self.api_key = _resolve_api_key(credentials_path)

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _request(self, method, path, params=None, body=None):
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)

        data = None
        if body is not None:
            data = json.dumps(body).encode()

        req = urllib.request.Request(
            url, data=data, headers=self._headers(), method=method
        )
        for attempt in range(MAX_RETRIES):
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read())
            except urllib.error.HTTPError as e:
                if e.code != 429:
                    raise
                error_body = _parse_error_body(e)
                retry_minutes = error_body.get("retry_after_minutes")
                if retry_minutes is not None:
                    raise RateLimited(int(retry_minutes) * 60, error_body) from e
                if attempt < MAX_RETRIES - 1:
                    retry_after = int(e.headers.get("Retry-After", RETRY_DELAY))
                    print(
                        f"Rate limited. Retrying in {retry_after}s...",
                        file=__import__("sys").stderr,
                    )
                    time.sleep(retry_after)
                    continue
                raise

    # Feed & posts

    def feed(self, sort="hot", limit=25):
        return self._request("GET", "/feed", params={"sort": sort, "limit": limit})

    def posts(self, submolt, sort="hot", limit=25, offset=0):
        return self._request(
            "GET",
            f"/submolts/{submolt}/posts",
            params={"sort": sort, "limit": limit, "offset": offset},
        )

    def post(self, post_id):
        return self._request("GET", f"/posts/{post_id}")

    def create_post(self, submolt, title, content, url=None):
        body = {"title": title, "content": content, "submolt": submolt}
        if url is not None:
            body["url"] = url
        return self._request("POST", "/posts", body=body)

    # Comments

    def comment(self, post_id, content, parent_id=None):
        body = {"content": content}
        if parent_id is not None:
            body["parent_id"] = parent_id
        return self._request("POST", f"/posts/{post_id}/comments", body=body)

    # Voting

    def upvote(self, post_id):
        return self._request("POST", f"/posts/{post_id}/upvote")

    def downvote(self, post_id):
        return self._request("POST", f"/posts/{post_id}/downvote")

    def upvote_comment(self, comment_id):
        return self._request("POST", f"/comments/{comment_id}/upvote")

    # Discovery

    def submolts(self):
        return self._request("GET", "/submolts")

    def search(self, query):
        return self._request("GET", "/search", params={"q": query})

    # Profile

    def me(self):
        return self._request("GET", "/me")

    def profile(self, name):
        return self._request("GET", f"/agents/{name}")

    def status(self):
        return self._request("GET", "/claim/status")

    def update_profile(self, description):
        return self._request("PUT", "/me", body={"description": description})
