# ABOUTME: Helper functions for working with Moltbook API responses.
# ABOUTME: Reduces token cost by summarizing and filtering post data.

import json
from datetime import datetime, timezone
from pathlib import Path


def _author_name(author):
    """Extract author name from a string or dict."""
    if isinstance(author, dict):
        return author.get("name", "unknown")
    return author or "unknown"


def _submolt_name(submolt):
    """Extract submolt name from a string or dict."""
    if isinstance(submolt, dict):
        return submolt.get("name", "")
    return submolt or ""


def resolve_state_path(filename):
    """Find a state file, checking project then user config directory.

    Search order:
    1. ./eos/{filename} (project directory)
    2. ~/.config/moltbook/{filename} (user config)

    Returns the first path that exists. For new files, prefers project
    directory if ./eos/ exists and is writable, otherwise user config.
    """
    project_path = Path.cwd() / "eos" / filename
    user_path = Path.home() / ".config" / "moltbook" / filename

    # Return existing file if found
    if project_path.exists():
        return project_path
    if user_path.exists():
        return user_path

    # For new files, prefer project directory if ./eos/ exists
    project_dir = Path.cwd() / "eos"
    if project_dir.is_dir():
        return project_path

    return user_path


def load_json(path, default=None):
    """Load a JSON file, returning default on missing/corrupt file."""
    try:
        return json.loads(Path(path).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return (
            default() if callable(default) else (default if default is not None else {})
        )


def save_json(path, data):
    """Save data as indented JSON, creating parent directories."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def summarize_post(post):
    """Reduce a full post object to the fields an agent needs for triage.

    Returns a compact dict with id, title, author, submolt, upvotes,
    comment_count, and created_at. Drops content, URL, and nested objects.
    """
    return {
        "id": post.get("id"),
        "title": post.get("title", ""),
        "author": _author_name(post.get("author")),
        "submolt": _submolt_name(post.get("submolt")),
        "upvotes": post.get("upvotes", 0),
        "comment_count": post.get("comment_count", 0),
        "created_at": post.get("created_at", ""),
    }


def summarize_posts(posts):
    """Summarize a list of posts. Accepts raw API post list."""
    return [summarize_post(p) for p in posts]


def filter_posts(posts, min_upvotes=None, authors=None, submolts=None):
    """Filter a list of posts by criteria.

    Args:
        posts: List of post dicts (full or summarized).
        min_upvotes: Only include posts with at least this many upvotes.
        authors: Only include posts by these author names.
        submolts: Only include posts in these submolts.

    Returns filtered list (does not mutate input).
    """
    result = posts
    if min_upvotes is not None:
        result = [p for p in result if p.get("upvotes", 0) >= min_upvotes]
    if authors is not None:
        author_set = set(authors)
        result = [p for p in result if _author_name(p.get("author")) in author_set]
    if submolts is not None:
        submolt_set = set(submolts)
        result = [p for p in result if _submolt_name(p.get("submolt")) in submolt_set]
    return result


def oneline_post(post):
    """Ultra-compact single-line representation of a post.

    Format: "[+5|3c] Title (by Author in submolt) #id"
    Optimized for minimum token count during feed triage.
    """
    upvotes = post.get("upvotes", 0)
    comments = post.get("comment_count", 0)
    title = post.get("title", "")
    author = _author_name(post.get("author"))
    submolt = _submolt_name(post.get("submolt"))
    post_id = post.get("id", "?")
    age = relative_age(post.get("created_at", ""))
    sub = f" in {submolt}" if submolt else ""
    return f"[{upvotes:+d}|{comments}c|{age}] {title} (by {author}{sub}) #{post_id}"


def oneline_feed(posts):
    """Render a full feed as one line per post.

    Returns a single string. This is the most token-efficient way to
    scan a feed — an agent can read 25 posts in ~25 lines instead of
    a massive JSON blob.
    """
    return "\n".join(oneline_post(p) for p in posts)


def oneline_comment(comment):
    """Ultra-compact single-line representation of a comment.

    Format: "[+2] Author: content (truncated) #id"
    """
    upvotes = comment.get("upvotes", 0)
    author = _author_name(comment.get("author"))
    content = comment.get("content", "")
    if len(content) > 120:
        content = content[:117] + "..."
    comment_id = comment.get("id", "?")
    return f"[{upvotes:+d}] {author}: {content} #{comment_id}"


def diff_feed(old_posts, new_posts):
    """Return posts in new_posts that weren't in old_posts.

    Compares by post ID. Useful for agents that poll periodically and
    only want to process new content.

    Args:
        old_posts: List of post dicts from previous check.
        new_posts: List of post dicts from current check.

    Returns list of posts that are new (not in old_posts by ID).
    """
    old_ids = {p.get("id") for p in old_posts}
    return [p for p in new_posts if p.get("id") not in old_ids]


def oneline_comments(comments):
    """Render a flat comment list as one line per comment.

    Like oneline_feed but for comments. Accepts the output of
    extract_comments(flat=True) or any list of comment dicts.
    """
    return "\n".join(oneline_comment(c) for c in comments)


def relative_age(timestamp):
    """Convert an ISO 8601 timestamp to a compact relative age string.

    Returns strings like '2h', '3d', '1w', '2mo'. Falls back to the
    original string if parsing fails. Much cheaper than full timestamps.
    """
    if not timestamp:
        return "?"
    try:
        # Handle both Z suffix and +00:00
        ts = timestamp.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        now = datetime.now(timezone.utc)
        delta = now - dt
        seconds = int(delta.total_seconds())
        if seconds < 0:
            return "now"
        if seconds < 60:
            return f"{seconds}s"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}m"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h"
        days = hours // 24
        if days < 7:
            return f"{days}d"
        weeks = days // 7
        if weeks < 5:
            return f"{weeks}w"
        months = days // 30
        if months < 12:
            return f"{months}mo"
        years = days // 365
        return f"{years}y"
    except (ValueError, TypeError):
        return str(timestamp)


def summarize_submolts(submolts):
    """Reduce the submolt list to essential fields.

    The full submolts response includes IDs, timestamps, creator objects,
    and theme data. This keeps only what agents need for discovery:
    name, display_name, subscriber_count, and a truncated description.
    """
    result = []
    for s in submolts:
        desc = s.get("description", "")
        if len(desc) > 80:
            desc = desc[:77] + "..."
        result.append(
            {
                "name": s.get("name", ""),
                "display_name": s.get("display_name", ""),
                "subscribers": s.get("subscriber_count", 0),
                "description": desc,
            }
        )
    return result


def oneline_submolt(submolt):
    """Ultra-compact one-line submolt representation.

    Format: \"m/name (123 subs) Description\"
    """
    name = submolt.get("name", "")
    subs = submolt.get("subscriber_count", 0)
    desc = submolt.get("description", "")
    if len(desc) > 60:
        desc = desc[:57] + "..."
    return f"m/{name} ({subs} subs) {desc}"


def oneline_submolts(submolts):
    """Render a submolt list as one line per submolt."""
    return "\n".join(oneline_submolt(s) for s in submolts)


def summarize_profile(profile):
    """Reduce a full profile response to essential fields.

    Drops full post lists and comment histories. Returns agent name,
    bio, karma, post count, and follower/following counts.
    """
    agent = profile.get("agent", profile) if isinstance(profile, dict) else profile
    if not isinstance(agent, dict):
        return profile

    result = {
        "name": agent.get("name", ""),
        "bio": agent.get("bio", ""),
        "karma": agent.get("karma", 0),
    }

    # Post count from posts list if available
    posts = profile.get("posts", agent.get("posts", []))
    if isinstance(posts, list):
        result["post_count"] = len(posts)

    # Follower/following counts
    for key in ("followers", "following", "follower_count", "following_count"):
        val = agent.get(key, profile.get(key))
        if val is not None:
            if isinstance(val, list):
                result[key + "_count"] = len(val)
            else:
                result[key] = val

    return result


def extract_comments(comments, flat=False):
    """Extract comment data from a nested comment tree.

    If flat=True, flattens the tree into a single list (depth-first).
    Each comment gets an 'author' field normalized to a string name.
    """
    result = []
    for c in comments:
        entry = {
            "id": c.get("id"),
            "author": _author_name(c.get("author")),
            "content": c.get("content", ""),
            "upvotes": c.get("upvotes", 0),
            "parent_id": c.get("parent_id"),
            "created_at": c.get("created_at", ""),
        }
        if flat:
            result.append(entry)
            replies = c.get("replies", [])
            if replies:
                result.extend(extract_comments(replies, flat=True))
        else:
            replies = c.get("replies", [])
            if replies:
                entry["replies"] = extract_comments(replies, flat=False)
            result.append(entry)
    return result
