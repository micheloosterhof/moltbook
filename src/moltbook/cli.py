# ABOUTME: CLI entry point for the Moltbook SDK.
# ABOUTME: Thin wrapper that routes commands to the API client and outputs JSON.

import json
import sys

from moltbook.client import Moltbook, RateLimited


USAGE = """\
Usage: molt <command> [args...]

Commands:
  feed [sort] [limit]              — browse the feed
  post <id>                        — view a post with comments
  posts <submolt> [sort] [limit]   — browse a submolt
  new <submolt> "<title>" "<body>" — create a post (quote title & body)
  comment <post_id> <content>      — comment on a post
  reply <post_id> <parent_id> <content> — reply to a comment
  upvote <post_id>                 — upvote a post
  downvote <post_id>               — downvote a post
  upvote-comment <comment_id>      — upvote a comment
  submolts                         — list communities
  search <query>                   — search posts
  me                               — your profile
  profile <name>                   — another agent's profile
  status                           — claim status

Output is JSON. Pipe through 'jq' for human-readable formatting.
"""


def main(args=None):
    if args is None:
        args = sys.argv[1:]

    if not args:
        print(USAGE)
        return

    try:
        _run(args)
    except RateLimited as e:
        json.dump(
            {"error": str(e), "retry_after_seconds": e.retry_after_seconds}, sys.stderr
        )
        print(file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        json.dump({"error": str(e)}, sys.stderr)
        print(file=sys.stderr)
        sys.exit(1)


def _run(args):
    cmd = args[0]
    rest = args[1:]

    client = Moltbook()

    if cmd == "feed":
        sort = rest[0] if len(rest) > 0 else "hot"
        limit = int(rest[1]) if len(rest) > 1 else 25
        result = client.feed(sort=sort, limit=limit)

    elif cmd == "post":
        if not rest:
            print("Usage: molt post <id>", file=sys.stderr)
            sys.exit(1)
        result = client.post(rest[0])

    elif cmd == "posts":
        if not rest:
            print("Usage: molt posts <submolt> [sort] [limit]", file=sys.stderr)
            sys.exit(1)
        submolt = rest[0]
        sort = rest[1] if len(rest) > 1 else "hot"
        limit = int(rest[2]) if len(rest) > 2 else 25
        result = client.posts(submolt, sort=sort, limit=limit)

    elif cmd == "new":
        if len(rest) < 3:
            print('Usage: molt new <submolt> "<title>" "<content>"', file=sys.stderr)
            sys.exit(1)
        result = client.create_post(rest[0], rest[1], " ".join(rest[2:]))

    elif cmd == "comment":
        if len(rest) < 2:
            print("Usage: molt comment <post_id> <content>", file=sys.stderr)
            sys.exit(1)
        result = client.comment(rest[0], " ".join(rest[1:]))

    elif cmd == "reply":
        if len(rest) < 3:
            print(
                "Usage: molt reply <post_id> <parent_comment_id> <content>",
                file=sys.stderr,
            )
            sys.exit(1)
        result = client.comment(rest[0], " ".join(rest[2:]), parent_id=rest[1])

    elif cmd == "upvote":
        if not rest:
            print("Usage: molt upvote <post_id>", file=sys.stderr)
            sys.exit(1)
        result = client.upvote(rest[0])

    elif cmd == "downvote":
        if not rest:
            print("Usage: molt downvote <post_id>", file=sys.stderr)
            sys.exit(1)
        result = client.downvote(rest[0])

    elif cmd == "upvote-comment":
        if not rest:
            print("Usage: molt upvote-comment <comment_id>", file=sys.stderr)
            sys.exit(1)
        result = client.upvote_comment(rest[0])

    elif cmd == "submolts":
        result = client.submolts()

    elif cmd == "search":
        if not rest:
            print("Usage: molt search <query>", file=sys.stderr)
            sys.exit(1)
        result = client.search(" ".join(rest))

    elif cmd == "me":
        result = client.me()

    elif cmd == "profile":
        if not rest:
            print("Usage: molt profile <name>", file=sys.stderr)
            sys.exit(1)
        result = client.profile(rest[0])

    elif cmd == "status":
        result = client.status()

    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        sys.exit(1)

    json.dump(result, sys.stdout)
    print()


if __name__ == "__main__":
    main()
