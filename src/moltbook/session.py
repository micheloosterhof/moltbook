# ABOUTME: Session helper for Moltbook agents.
# ABOUTME: One-call session briefing that reduces boilerplate and token waste.

from moltbook.helpers import summarize_posts, filter_posts, extract_comments


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

    def __init__(self, client, tracker=None):
        self.client = client
        self.tracker = tracker

    def start(self, feed_limit=25):
        """Fetch a structured session briefing.

        Returns a dict with:
            feed_hot: summarized hot posts
            feed_new: summarized new posts
            replies: new replies from tracker (if tracker provided)
        """
        brief = {}

        hot = self.client.feed(sort="hot", limit=feed_limit)
        brief["feed_hot"] = summarize_posts(hot.get("posts", []))

        new = self.client.feed(sort="new", limit=feed_limit)
        brief["feed_new"] = summarize_posts(new.get("posts", []))

        if self.tracker:
            brief["replies"] = self.tracker.check_replies()
        else:
            brief["replies"] = []

        return brief

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
            "author": _author_name(post.get("author")) if isinstance(post, dict) else "unknown",
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
