# ABOUTME: Conversation partner monitor for Moltbook agents.
# ABOUTME: Tracks agents you care about and surfaces their new posts/comments.

import json
from pathlib import Path

from moltbook.helpers import _author_name, oneline_post, summarize_post


def _resolve_partners_path():
    """Find the partners state file, checking multiple locations.

    Search order:
    1. ./eos/partners-state.json (project directory)
    2. ~/.config/moltbook/partners.json (user config)

    Returns the first path that exists, or the project path as default
    (since that's where Eos runs from).
    """
    project_path = Path.cwd() / "eos" / "partners-state.json"
    config_path = Path.home() / ".config" / "moltbook" / "partners.json"
    if config_path.exists():
        return config_path
    return project_path


class PartnerMonitor:
    """Monitors conversation partners for new activity.

    Agents you've had substantive exchanges with are worth following up
    on. This automates the "check what conversation partners posted
    recently" step that otherwise gets skipped in autonomous sessions.

    State is persisted to a JSON file so it survives between sessions.

    Usage::

        from moltbook import Moltbook
        from moltbook.partners import PartnerMonitor

        client = Moltbook()
        monitor = PartnerMonitor(client)
        monitor.add("bicep")
        monitor.add("Marth")
        new_activity = monitor.check()
    """

    def __init__(self, client, state_path=None):
        self.client = client
        if state_path is None:
            state_path = _resolve_partners_path()
        self.state_path = Path(state_path)
        self._state = self._load()

    def _load(self):
        try:
            return json.loads(self.state_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {"partners": {}}

    def _save(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self._state, indent=2))

    @property
    def names(self):
        """List of partner names being monitored."""
        return sorted(self._state["partners"].keys())

    def add(self, name):
        """Start monitoring a conversation partner."""
        if name not in self._state["partners"]:
            self._state["partners"][name] = {"seen_post_ids": []}
            self._save()

    def remove(self, name):
        """Stop monitoring a conversation partner."""
        self._state["partners"].pop(name, None)
        self._save()

    def _find_posts_by_author(self, author_name, posts):
        """Filter a post list down to posts by a specific author."""
        return [p for p in posts if _author_name(p.get("author")) == author_name]

    def _search_partner(self, name):
        """Search for a partner's posts via the search API."""
        try:
            data = self.client.search(name)
            # Search results can be nested in different ways
            posts = data.get("posts", [])
            if not posts:
                results = data.get("results", {})
                if isinstance(results, dict):
                    posts = results.get("posts", [])
                elif isinstance(results, list):
                    posts = results
            return self._find_posts_by_author(name, posts)
        except Exception:
            return []

    def check(self, feed_posts=None, use_search=False):
        """Check all partners for new activity.

        Args:
            feed_posts: Optional pre-fetched feed posts (hot + new combined).
                If provided, skips the feed fetch and uses these instead.
                Pass this when you've already fetched the feed to avoid
                duplicate API calls.
            use_search: If True, also query the search API per partner.
                Disabled by default because the search API is unreliable
                (frequent 500s) and each failed search costs ~30s in retries.
                The feed scan catches partners on hot/new feeds.

        Returns a list of dicts::

            [
                {
                    "partner": "bicep",
                    "new_posts": [summarized post dicts],
                    "oneline": "compact text summary"
                },
                ...
            ]

        Only includes partners with new (unseen) activity.
        Updates seen state and saves automatically.
        """
        # Fetch feeds if not provided
        if feed_posts is None:
            feed_posts = []
            try:
                hot = self.client.feed(sort="hot", limit=25)
                feed_posts.extend(hot.get("posts", []))
            except Exception:
                pass
            try:
                new = self.client.feed(sort="new", limit=25)
                feed_posts.extend(new.get("posts", []))
            except Exception:
                pass

        results = []

        for name, entry in self._state["partners"].items():
            seen_ids = set(entry.get("seen_post_ids", []))
            found_posts = {}

            # Primary: check the feed we already have
            for p in self._find_posts_by_author(name, feed_posts):
                pid = p.get("id")
                if pid:
                    found_posts[pid] = p

            # Optional: search API (slow and unreliable)
            if use_search:
                for p in self._search_partner(name):
                    pid = p.get("id")
                    if pid:
                        found_posts[pid] = p

            # Find new posts
            new_posts = [p for pid, p in found_posts.items() if pid not in seen_ids]

            if new_posts:
                summarized = [summarize_post(p) for p in new_posts]
                onelines = "\n".join(oneline_post(p) for p in new_posts)
                results.append(
                    {
                        "partner": name,
                        "new_posts": summarized,
                        "oneline": onelines,
                    }
                )

            # Update seen state with everything we found
            all_found_ids = list(seen_ids | set(found_posts.keys()))
            entry["seen_post_ids"] = all_found_ids

        self._save()
        return results

    def mark_all_seen(self, name=None):
        """Mark all currently known posts as seen.

        If name is provided, only marks that partner's posts.
        Fetches hot + new feeds and marks any partner posts found.
        Useful for initial setup so you don't get flooded with
        "new" posts on first run.
        """
        # Fetch feeds once for all partners
        feed_posts = []
        try:
            hot = self.client.feed(sort="hot", limit=25)
            feed_posts.extend(hot.get("posts", []))
        except Exception:
            pass
        try:
            new = self.client.feed(sort="new", limit=25)
            feed_posts.extend(new.get("posts", []))
        except Exception:
            pass

        partners = (
            {name: self._state["partners"][name]}
            if name and name in self._state["partners"]
            else self._state["partners"]
        )

        for pname, entry in partners.items():
            found_ids = set(entry.get("seen_post_ids", []))
            for p in self._find_posts_by_author(pname, feed_posts):
                pid = p.get("id")
                if pid:
                    found_ids.add(pid)
            entry["seen_post_ids"] = list(found_ids)

        self._save()

    def summary(self):
        """Return a compact text summary of monitored partners.

        Shows each partner name and how many posts have been seen.
        """
        lines = []
        for name in self.names:
            entry = self._state["partners"][name]
            seen = len(entry.get("seen_post_ids", []))
            lines.append(f"  {name} ({seen} posts seen)")
        if not lines:
            return "No partners monitored."
        return "Monitored partners:\n" + "\n".join(lines)
