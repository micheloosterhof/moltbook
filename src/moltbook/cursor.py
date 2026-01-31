# ABOUTME: Persistent high-water mark for Moltbook feeds.
# ABOUTME: Tracks last-seen posts per source so sessions surface only new content.

import json
from datetime import datetime, timezone
from pathlib import Path

_MAX_SEEN_PER_SOURCE = 500


def _resolve_cursor():
    """Find the cursor file, checking multiple locations."""
    candidates = [
        Path.cwd() / "eos" / "cursor.json",
        Path.home() / ".config" / "moltbook" / "cursor.json",
    ]
    for path in candidates:
        if path.exists():
            return path
    return Path.home() / ".config" / "moltbook" / "cursor.json"


class FeedCursor:
    """Tracks last-seen posts per feed source.

    Inspired by nn's .newsrc — records which posts have been seen so
    subsequent sessions only surface truly new content.

    Sources are independent: "hot", "new", and submolt names each
    maintain their own seen set.

    Usage::

        cursor = FeedCursor()
        new_posts = cursor.unseen(posts, source="hot")
        cursor.mark_seen(posts, source="hot")
    """

    def __init__(self, cursor_path=None):
        if cursor_path is None:
            cursor_path = _resolve_cursor()
        self.cursor_path = Path(cursor_path)
        self._data = self._load()

    def _load(self):
        try:
            return json.loads(self.cursor_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {"sources": {}}

    def _save(self):
        self.cursor_path.parent.mkdir(parents=True, exist_ok=True)
        self.cursor_path.write_text(json.dumps(self._data, indent=2))

    def _source(self, name):
        """Get or create a source entry."""
        sources = self._data.setdefault("sources", {})
        if name not in sources:
            sources[name] = {"seen_ids": [], "last_checked": None}
        return sources[name]

    def mark_seen(self, posts, source=None):
        """Record post IDs as seen.

        Args:
            posts: list of post dicts (must have "id" key)
            source: feed source name ("hot", "new", submolt name)
        """
        source = source or "default"
        src = self._source(source)
        seen = set(src["seen_ids"])
        for p in posts:
            pid = p.get("id") if isinstance(p, dict) else p
            if pid:
                seen.add(pid)
        # Cap to prevent unbounded growth
        seen_list = list(seen)
        if len(seen_list) > _MAX_SEEN_PER_SOURCE:
            seen_list = seen_list[-_MAX_SEEN_PER_SOURCE:]
        src["seen_ids"] = seen_list
        src["last_checked"] = datetime.now(timezone.utc).isoformat()
        self._save()

    def unseen(self, posts, source=None):
        """Filter to only posts not yet seen.

        Args:
            posts: list of post dicts
            source: feed source name

        Returns:
            list of posts whose IDs are not in the seen set
        """
        source = source or "default"
        src = self._source(source)
        seen = set(src["seen_ids"])
        return [p for p in posts if p.get("id") not in seen]

    def catch_up(self, source=None):
        """Mark everything as seen (nn's -a0 equivalent).

        If source is given, only that source is caught up.
        If source is None, all sources are marked with current timestamp.
        """
        now = datetime.now(timezone.utc).isoformat()
        if source:
            src = self._source(source)
            src["last_checked"] = now
        else:
            for src in self._data.get("sources", {}).values():
                src["last_checked"] = now
        self._save()

    def reset(self, source=None):
        """Clear seen state (start fresh).

        If source is given, only that source is reset.
        If source is None, all sources are cleared.
        """
        if source:
            sources = self._data.get("sources", {})
            if source in sources:
                sources[source] = {"seen_ids": [], "last_checked": None}
        else:
            self._data["sources"] = {}
        self._save()

    def stats(self):
        """Counts per source."""
        result = {}
        for name, src in self._data.get("sources", {}).items():
            result[name] = {
                "seen_count": len(src.get("seen_ids", [])),
                "last_checked": src.get("last_checked"),
            }
        return result

    def summary(self):
        """Compact text summary."""
        sources = self._data.get("sources", {})
        if not sources:
            return "No feed history tracked."
        lines = []
        for name, src in sorted(sources.items()):
            count = len(src.get("seen_ids", []))
            last = src.get("last_checked", "never")
            if last and last != "never":
                last = last[:19].replace("T", " ")
            lines.append(f"  {name}: {count} seen (last: {last})")
        return f"Feed cursor ({len(sources)} sources):\n" + "\n".join(lines)
