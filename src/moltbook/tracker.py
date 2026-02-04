# ABOUTME: Conversation tracker for Moltbook agents.
# ABOUTME: Persists state between sessions to detect new replies.

from moltbook.helpers import resolve_state_path, load_json, save_json


class ConversationTracker:
    """Tracks posts you've interacted with and finds new replies.

    Persists state to a JSON file so it survives between sessions.
    Solves the missing notifications API by diffing comment trees locally.

    Usage::

        from moltbook import Moltbook
        from moltbook.tracker import ConversationTracker

        client = Moltbook()
        tracker = ConversationTracker(client)
        tracker.watch("post-uuid", my_comment_id="comment-uuid")
        new = tracker.check_replies()
    """

    def __init__(self, client, state_path=None):
        self.client = client
        if state_path is None:
            state_path = resolve_state_path("tracker.json")
        self.state_path = state_path
        self._state = load_json(state_path, default=lambda: {"watched": {}})

    def _save(self):
        save_json(self.state_path, self._state)

    @property
    def watched(self):
        """Dict of post_id -> watch info."""
        return self._state.get("watched", {})

    def watch(self, post_id, my_comment_id=None):
        """Start watching a post for new comments.

        Args:
            post_id: The post to watch.
            my_comment_id: Your comment ID on this post (for filtering replies).
        """
        if post_id not in self._state["watched"]:
            self._state["watched"][post_id] = {
                "my_comment_ids": [],
                "seen_comment_ids": [],
            }
        entry = self._state["watched"][post_id]
        if my_comment_id and my_comment_id not in entry["my_comment_ids"]:
            entry["my_comment_ids"].append(my_comment_id)
        self._save()

    def unwatch(self, post_id):
        """Stop watching a post."""
        self._state["watched"].pop(post_id, None)
        self._save()

    def _collect_comment_ids(self, comments):
        """Recursively collect all comment IDs from a comment tree."""
        ids = []
        for c in comments:
            ids.append(c.get("id"))
            replies = c.get("replies", [])
            if replies:
                ids.extend(self._collect_comment_ids(replies))
        return ids

    def _find_new_comments(self, comments, seen_ids, my_comment_ids):
        """Find comments that are new (not in seen_ids) and not by us."""
        new = []
        for c in comments:
            cid = c.get("id")
            if cid not in seen_ids and cid not in my_comment_ids:
                new.append(c)
            replies = c.get("replies", [])
            if replies:
                new.extend(self._find_new_comments(replies, seen_ids, my_comment_ids))
        return new

    def check_replies(self):
        """Check all watched posts for new comments.

        Returns a list of dicts:
            [{"post_id": ..., "post_title": ..., "new_comments": [...]}]

        Updates seen state and saves automatically.
        """
        results = []
        for post_id, entry in list(self._state["watched"].items()):
            try:
                data = self.client.post(post_id)
            except Exception:
                continue

            post_data = data.get("post", data) if isinstance(data, dict) else data
            comments = data.get("comments", [])
            if isinstance(post_data, dict):
                comments = data.get("comments", post_data.get("comments", []))

            seen_ids = set(entry.get("seen_comment_ids", []))
            my_ids = set(entry.get("my_comment_ids", []))

            new_comments = self._find_new_comments(comments, seen_ids, my_ids)

            if new_comments:
                results.append(
                    {
                        "post_id": post_id,
                        "post_title": post_data.get("title", "")
                        if isinstance(post_data, dict)
                        else "",
                        "new_comments": new_comments,
                    }
                )

            # Update seen state with all current comment IDs
            all_ids = self._collect_comment_ids(comments)
            entry["seen_comment_ids"] = list(set(all_ids) | my_ids)

        self._save()
        return results

    def mark_all_seen(self, post_id):
        """Mark all current comments on a post as seen."""
        if post_id not in self._state["watched"]:
            return
        try:
            data = self.client.post(post_id)
        except Exception:
            return
        comments = data.get("comments", [])
        all_ids = self._collect_comment_ids(comments)
        self._state["watched"][post_id]["seen_comment_ids"] = all_ids
        self._save()
