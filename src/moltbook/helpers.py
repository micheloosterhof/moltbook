# ABOUTME: Helper functions for working with Moltbook API responses.
# ABOUTME: Reduces token cost by summarizing and filtering post data.


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
