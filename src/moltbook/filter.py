# ABOUTME: Feed filter and spam blocklist for Moltbook agents.
# ABOUTME: Strips known spam actors from feeds and comment trees before display.

import json
from pathlib import Path

from moltbook.helpers import _author_name


def _resolve_blocklist():
    """Find the blocklist file, checking multiple locations.

    Search order:
    1. ./eos/blocklist.json (project directory)
    2. ~/.config/moltbook/blocklist.json (user config)

    Returns the first path that exists, or the user config path as default.
    """
    candidates = [
        Path.cwd() / "eos" / "blocklist.json",
        Path.home() / ".config" / "moltbook" / "blocklist.json",
    ]
    for path in candidates:
        if path.exists():
            return path
    # Default to user config (will be created on first block)
    return Path.home() / ".config" / "moltbook" / "blocklist.json"


class FeedFilter:
    """Filters spam and noise from Moltbook feeds and comment trees.

    Loads a blocklist from a JSON file and strips matching authors from
    post lists and comment trees. Saves tokens and attention every session.

    The blocklist file is a JSON object with a "blocked" list of author
    names and an optional "reasons" dict for documentation::

        {
            "blocked": ["clawph", "Rally", "samaltman"],
            "reasons": {
                "clawph": "engagement farming, lobster emoji spam",
                "samaltman": "prompt injection via fake impersonation"
            }
        }

    Usage::

        from moltbook import Moltbook
        from moltbook.filter import FeedFilter

        client = Moltbook()
        ff = FeedFilter()
        posts = client.feed()["posts"]
        clean = ff.filter_posts(posts)
    """

    def __init__(self, blocklist_path=None):
        if blocklist_path is None:
            blocklist_path = _resolve_blocklist()
        self.blocklist_path = Path(blocklist_path)
        self._data = self._load()

    def _load(self):
        try:
            return json.loads(self.blocklist_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {"blocked": [], "reasons": {}}

    def _save(self):
        self.blocklist_path.parent.mkdir(parents=True, exist_ok=True)
        self.blocklist_path.write_text(json.dumps(self._data, indent=2))

    @property
    def blocked(self):
        """Set of blocked author names (case-sensitive)."""
        return set(self._data.get("blocked", []))

    def block(self, name, reason=None):
        """Add an author to the blocklist."""
        blocked = self._data.get("blocked", [])
        if name not in blocked:
            blocked.append(name)
            self._data["blocked"] = blocked
        if reason:
            reasons = self._data.get("reasons", {})
            reasons[name] = reason
            self._data["reasons"] = reasons
        self._save()

    def unblock(self, name):
        """Remove an author from the blocklist."""
        blocked = self._data.get("blocked", [])
        self._data["blocked"] = [n for n in blocked if n != name]
        reasons = self._data.get("reasons", {})
        reasons.pop(name, None)
        self._data["reasons"] = reasons
        self._save()

    def is_blocked(self, author):
        """Check if an author name (string or dict) is blocked."""
        return _author_name(author) in self.blocked

    def filter_posts(self, posts):
        """Remove posts by blocked authors. Returns a new list."""
        return [p for p in posts if _author_name(p.get("author")) not in self.blocked]

    def filter_comments(self, comments):
        """Remove comments by blocked authors from a comment tree.

        Recursively filters the nested replies structure. If a blocked
        author's comment has non-blocked replies, the replies are
        promoted up (not lost with their parent).
        """
        result = []
        for c in comments:
            replies = c.get("replies", [])
            filtered_replies = self.filter_comments(replies) if replies else []

            if _author_name(c.get("author")) in self.blocked:
                # Blocked author: drop the comment, promote any clean replies
                result.extend(filtered_replies)
            else:
                if filtered_replies != replies:
                    c = dict(c, replies=filtered_replies)
                result.append(c)
        return result

    def filter_post_data(self, post_data):
        """Filter comments within a full post response.

        Accepts the raw API response from client.post(id) and returns
        it with blocked comments removed.
        """
        if not isinstance(post_data, dict):
            return post_data
        comments = post_data.get("comments", [])
        if comments:
            post_data = dict(post_data, comments=self.filter_comments(comments))
        return post_data

    def stats(self):
        """Return a summary dict of the blocklist."""
        blocked = self._data.get("blocked", [])
        reasons = self._data.get("reasons", {})
        return {
            "count": len(blocked),
            "blocked": blocked,
            "with_reasons": {n: reasons[n] for n in blocked if n in reasons},
        }

    def summary(self):
        """Compact text summary of the blocklist."""
        blocked = self._data.get("blocked", [])
        reasons = self._data.get("reasons", {})
        if not blocked:
            return "Blocklist is empty."
        lines = []
        for name in sorted(blocked):
            reason = reasons.get(name, "")
            suffix = f" — {reason}" if reason else ""
            lines.append(f"  {name}{suffix}")
        return f"Blocklist ({len(blocked)} blocked):\n" + "\n".join(lines)
