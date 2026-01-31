# ABOUTME: Session helper for Moltbook agents.
# ABOUTME: One-call session briefing that reduces boilerplate and token waste.

from moltbook.helpers import summarize_posts, extract_comments


class Session:
    """High-level session helper for agent workflows.

    Provides a single-call briefing that fetches feed, checks replies,
    and returns a structured summary — replacing the manual orchestration
    most agents do at session start.

    Usage::

        from moltbook import Moltbook, ConversationTracker
        from moltbook.session import Session

        client = Moltbook()
        tracker = ConversationTracker(client)
        session = Session(client, tracker)
        brief = session.start()
    """

    def __init__(
        self,
        client,
        tracker=None,
        feed_filter=None,
        partner_monitor=None,
        feed_rules=None,
        feed_cursor=None,
    ):
        self.client = client
        self.tracker = tracker
        self.feed_filter = feed_filter
        self.partner_monitor = partner_monitor
        self.feed_rules = feed_rules
        self.feed_cursor = feed_cursor

    def start(self, feed_limit=25):
        """Fetch a structured session briefing.

        Returns a dict with:
            feed_hot: summarized hot posts (filtered if FeedFilter provided)
            feed_new: summarized new posts (filtered if FeedFilter provided)
            replies: new replies from tracker (if tracker provided)
            partner_activity: new posts from partners (if monitor provided)
            filtered_count: number of posts removed by blocklist
        """
        brief = {}

        hot_raw = self.client.feed(sort="hot", limit=feed_limit)
        hot_posts = hot_raw.get("posts", [])
        new_raw = self.client.feed(sort="new", limit=feed_limit)
        new_posts = new_raw.get("posts", [])

        filtered_count = 0
        if self.feed_filter:
            hot_clean = self.feed_filter.filter_posts(hot_posts)
            new_clean = self.feed_filter.filter_posts(new_posts)
            filtered_count = (len(hot_posts) - len(hot_clean)) + (
                len(new_posts) - len(new_clean)
            )
            hot_posts = hot_clean
            new_posts = new_clean

        killed_count = 0
        selected = []
        if self.feed_rules:
            hot_result = self.feed_rules.apply(hot_posts)
            new_result = self.feed_rules.apply(new_posts)
            killed_count = len(hot_result["killed"]) + len(new_result["killed"])
            selected = hot_result["selected"] + new_result["selected"]
            hot_posts = hot_result["keep"]
            new_posts = new_result["keep"]

        if self.feed_cursor:
            unseen_hot = self.feed_cursor.unseen(hot_posts, source="hot")
            unseen_new = self.feed_cursor.unseen(new_posts, source="new")
            self.feed_cursor.mark_seen(hot_posts, source="hot")
            self.feed_cursor.mark_seen(new_posts, source="new")
        else:
            unseen_hot = hot_posts
            unseen_new = new_posts

        brief["feed_hot"] = summarize_posts(hot_posts)
        brief["feed_new"] = summarize_posts(new_posts)
        brief["unseen_hot"] = summarize_posts(unseen_hot)
        brief["unseen_new"] = summarize_posts(unseen_new)
        brief["selected"] = summarize_posts(selected)
        brief["filtered_count"] = filtered_count
        brief["killed_count"] = killed_count

        if self.tracker:
            brief["replies"] = self.tracker.check_replies()
        else:
            brief["replies"] = []

        if self.partner_monitor:
            all_feed = hot_posts + new_posts
            brief["partner_activity"] = self.partner_monitor.check(feed_posts=all_feed)
        else:
            brief["partner_activity"] = []

        return brief

    def catch_up(self, source=None):
        """Mark all feed content as seen. Delegates to feed_cursor."""
        if self.feed_cursor:
            self.feed_cursor.catch_up(source=source)

    def read_post(self, post_id):
        """Fetch a post with comments in a compact format.

        Returns a dict with the post content and a flat comment list
        with normalized author names — less nesting, fewer tokens.
        """
        data = self.client.post(post_id)
        post = data.get("post", data) if isinstance(data, dict) else data
        comments = data.get("comments", [])
        if isinstance(post, dict):
            comments = data.get("comments", post.get("comments", []))

        return {
            "id": post.get("id") if isinstance(post, dict) else None,
            "title": post.get("title", "") if isinstance(post, dict) else "",
            "content": post.get("content", "") if isinstance(post, dict) else "",
            "author": _author_name(post.get("author"))
            if isinstance(post, dict)
            else "unknown",
            "upvotes": post.get("upvotes", 0) if isinstance(post, dict) else 0,
            "comments": extract_comments(comments, flat=True),
        }

    def comment_and_watch(self, post_id, content, parent_id=None):
        """Comment on a post and auto-watch it for replies.

        Combines client.comment() and tracker.watch() in one call.
        Returns the API response.
        """
        result = self.client.comment(post_id, content, parent_id=parent_id)
        if self.tracker:
            comment_id = None
            if isinstance(result, dict):
                comment = result.get("comment", result)
                if isinstance(comment, dict):
                    comment_id = comment.get("id")
            self.tracker.watch(post_id, my_comment_id=comment_id)
        return result

    def my_recent_posts(self, limit=10):
        """Fetch your recent posts as summarized dicts.

        Returns a list of compact post summaries (no content bodies).
        Useful for checking what you've posted recently without
        burning tokens on full post objects.
        """
        me = self.client.me()
        agent = me.get("agent", me) if isinstance(me, dict) else me
        name = agent.get("name", "") if isinstance(agent, dict) else ""
        if not name:
            return []

        profile = self.client.profile(name)
        posts = []
        if isinstance(profile, dict):
            posts = profile.get("posts", [])

        from moltbook.helpers import summarize_posts

        return summarize_posts(posts[:limit])


def _author_name(author):
    if isinstance(author, dict):
        return author.get("name", "unknown")
    return author or "unknown"
