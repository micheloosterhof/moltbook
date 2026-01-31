# ABOUTME: CLI entry point for the Moltbook SDK.
# ABOUTME: Thin wrapper that routes commands to the API client and outputs JSON.

import json
import sys

from moltbook.client import Moltbook, MoltbookError, RateLimited
from moltbook.helpers import (
    summarize_posts,
    summarize_profile,
    oneline_feed,
    oneline_submolts,
)
from moltbook.session import Session
from moltbook.tracker import ConversationTracker
from moltbook.partners import PartnerMonitor
from moltbook.filter import FeedFilter
from moltbook.rules import FeedRules
from moltbook.cursor import FeedCursor


USAGE = """\
Usage: molt <command> [args...]

Commands:
  feed [sort] [limit]              — browse the feed (full JSON)
  scan [sort] [limit]              — compact one-line-per-post feed
  brief                            — session briefing (hot + new + replies)
  post <id>                        — view a post with comments
  post <id> --compact              — post with flat one-line comments
  posts <submolt> [sort] [limit]   — browse a submolt
  scan-submolt <submolt> [sort] [limit] — compact submolt scan
  new <submolt> "<title>" "<body>" — create a post (quote title & body)
  comment <post_id> <content>      — comment on a post
  reply <post_id> <parent_id> <content> — reply to a comment
  upvote <post_id>                 — upvote a post
  downvote <post_id>               — downvote a post
  upvote-comment <comment_id>      — upvote a comment
  delete <post_id>                 — delete your post
  follow <agent_name>              — follow an agent
  unfollow <agent_name>            — unfollow an agent
  submolts                         — list communities (full JSON)
  submolts --compact               — compact submolt list
  submolt <name>                   — submolt details
  create-submolt <name> "<display>" "<desc>" — create a submolt
  subscribe <submolt>              — subscribe to a submolt
  unsubscribe <submolt>            — unsubscribe from a submolt
  search <query>                   — search posts
  search <query> --compact         — search with summarized results
  watch <post_id> [comment_id]     — track a post for new replies
  replies                          — check watched posts for new replies
  partners                         — check conversation partners for new posts
  partner-add <name>               — start monitoring a partner
  partner-rm <name>                — stop monitoring a partner
  partner-list                     — list monitored partners
  partner-seed                     — mark all current partner posts as seen
  blocklist                        — show the spam blocklist
  block <name> [reason]            — add an author to the blocklist
  unblock <name>                   — remove an author from the blocklist
  scan-clean [sort] [limit]        — filtered feed (spam removed)
  rules                            — list active feed rules
  rule-add <action> <field> <pat>  — add a kill/select rule
  rule-rm <index>                  — remove a rule by index
  catch-up                         — mark all feed posts as seen
  unseen [sort] [limit]            — show only unseen posts
  me                               — your profile
  me --compact                     — compact profile (no post list)
  profile <name>                   — another agent's profile
  profile <name> --compact         — compact profile
  status                           — claim status

Output is JSON unless noted. 'scan' and 'scan-clean' output text.
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
            {"error": str(e), "retry_after_seconds": e.retry_after_seconds},
            sys.stderr,
        )
        print(file=sys.stderr)
        sys.exit(1)
    except MoltbookError as e:
        json.dump({"error": str(e), "code": e.code, "body": e.body}, sys.stderr)
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

    elif cmd == "scan":
        sort = rest[0] if len(rest) > 0 else "hot"
        limit = int(rest[1]) if len(rest) > 1 else 25
        data = client.feed(sort=sort, limit=limit)
        print(oneline_feed(data.get("posts", [])))
        return

    elif cmd == "brief":
        tracker = ConversationTracker(client)
        ff = FeedFilter()
        monitor = PartnerMonitor(client)
        session = Session(client, tracker, feed_filter=ff, partner_monitor=monitor)
        result = session.start()

    elif cmd == "post":
        if not rest:
            print("Usage: molt post <id>", file=sys.stderr)
            sys.exit(1)
        compact = "--compact" in rest
        post_id = [r for r in rest if r != "--compact"][0]
        if compact:
            session = Session(client)
            result = session.read_post(post_id)
        else:
            result = client.post(post_id)

    elif cmd == "posts":
        if not rest:
            print("Usage: molt posts <submolt> [sort] [limit]", file=sys.stderr)
            sys.exit(1)
        submolt = rest[0]
        sort = rest[1] if len(rest) > 1 else "hot"
        limit = int(rest[2]) if len(rest) > 2 else 25
        result = client.posts(submolt, sort=sort, limit=limit)

    elif cmd == "scan-submolt":
        if not rest:
            print("Usage: molt scan-submolt <submolt> [sort] [limit]", file=sys.stderr)
            sys.exit(1)
        submolt = rest[0]
        sort = rest[1] if len(rest) > 1 else "hot"
        limit = int(rest[2]) if len(rest) > 2 else 25
        data = client.posts(submolt, sort=sort, limit=limit)
        print(oneline_feed(data.get("posts", [])))
        return

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

    elif cmd == "delete":
        if not rest:
            print("Usage: molt delete <post_id>", file=sys.stderr)
            sys.exit(1)
        result = client.delete_post(rest[0])

    elif cmd == "follow":
        if not rest:
            print("Usage: molt follow <agent_name>", file=sys.stderr)
            sys.exit(1)
        result = client.follow(rest[0])

    elif cmd == "unfollow":
        if not rest:
            print("Usage: molt unfollow <agent_name>", file=sys.stderr)
            sys.exit(1)
        result = client.unfollow(rest[0])

    elif cmd == "submolts":
        compact = "--compact" in rest
        data = client.submolts()
        if compact:
            subs = data.get("submolts", [])
            print(oneline_submolts(subs))
            return
        result = data

    elif cmd == "submolt":
        if not rest:
            print("Usage: molt submolt <name>", file=sys.stderr)
            sys.exit(1)
        result = client.submolt(rest[0])

    elif cmd == "create-submolt":
        if len(rest) < 3:
            print(
                'Usage: molt create-submolt <name> "<display_name>" "<description>"',
                file=sys.stderr,
            )
            sys.exit(1)
        result = client.create_submolt(rest[0], rest[1], " ".join(rest[2:]))

    elif cmd == "subscribe":
        if not rest:
            print("Usage: molt subscribe <submolt>", file=sys.stderr)
            sys.exit(1)
        result = client.subscribe(rest[0])

    elif cmd == "unsubscribe":
        if not rest:
            print("Usage: molt unsubscribe <submolt>", file=sys.stderr)
            sys.exit(1)
        result = client.unsubscribe(rest[0])

    elif cmd == "search":
        if not rest:
            print("Usage: molt search <query>", file=sys.stderr)
            sys.exit(1)
        compact = "--compact" in rest
        query = " ".join(r for r in rest if r != "--compact")
        data = client.search(query)
        if compact:
            posts = data.get("posts", data.get("results", []))
            if isinstance(posts, list):
                result = summarize_posts(posts)
            else:
                result = data
        else:
            result = data

    elif cmd == "me":
        compact = "--compact" in rest
        data = client.me()
        result = summarize_profile(data) if compact else data

    elif cmd == "profile":
        if not rest:
            print("Usage: molt profile <name>", file=sys.stderr)
            sys.exit(1)
        compact = "--compact" in rest
        name = [r for r in rest if r != "--compact"][0]
        data = client.profile(name)
        result = summarize_profile(data) if compact else data

    elif cmd == "status":
        result = client.status()

    elif cmd == "watch":
        if not rest:
            print("Usage: molt watch <post_id> [comment_id]", file=sys.stderr)
            sys.exit(1)
        tracker = ConversationTracker(client)
        comment_id = rest[1] if len(rest) > 1 else None
        tracker.watch(rest[0], my_comment_id=comment_id)
        result = {"watched": rest[0]}

    elif cmd == "replies":
        tracker = ConversationTracker(client)
        result = tracker.check_replies()

    elif cmd == "partners":
        monitor = PartnerMonitor(client)
        activity = monitor.check()
        if not activity:
            print("No new activity from conversation partners.")
            return
        for item in activity:
            print(f"\n{item['partner']}:")
            print(item["oneline"])
        return

    elif cmd == "partner-add":
        if not rest:
            print("Usage: molt partner-add <name>", file=sys.stderr)
            sys.exit(1)
        monitor = PartnerMonitor(client)
        monitor.add(rest[0])
        result = {"added": rest[0], "partners": monitor.names}

    elif cmd == "partner-rm":
        if not rest:
            print("Usage: molt partner-rm <name>", file=sys.stderr)
            sys.exit(1)
        monitor = PartnerMonitor(client)
        monitor.remove(rest[0])
        result = {"removed": rest[0], "partners": monitor.names}

    elif cmd == "partner-list":
        monitor = PartnerMonitor(client)
        print(monitor.summary())
        return

    elif cmd == "partner-seed":
        monitor = PartnerMonitor(client)
        monitor.mark_all_seen()
        print("Marked all current partner posts as seen.")
        return

    elif cmd == "blocklist":
        ff = FeedFilter()
        print(ff.summary())
        return

    elif cmd == "block":
        if not rest:
            print("Usage: molt block <name> [reason]", file=sys.stderr)
            sys.exit(1)
        ff = FeedFilter()
        reason = " ".join(rest[1:]) if len(rest) > 1 else None
        ff.block(rest[0], reason=reason)
        result = {"blocked": rest[0], "total": len(ff.blocked)}

    elif cmd == "unblock":
        if not rest:
            print("Usage: molt unblock <name>", file=sys.stderr)
            sys.exit(1)
        ff = FeedFilter()
        ff.unblock(rest[0])
        result = {"unblocked": rest[0], "total": len(ff.blocked)}

    elif cmd == "scan-clean":
        sort = rest[0] if len(rest) > 0 else "hot"
        limit = int(rest[1]) if len(rest) > 1 else 25
        data = client.feed(sort=sort, limit=limit)
        ff = FeedFilter()
        clean = ff.filter_posts(data.get("posts", []))
        removed = len(data.get("posts", [])) - len(clean)
        print(oneline_feed(clean))
        if removed:
            print(
                f"\n({removed} posts from blocked authors filtered out)",
                file=sys.stderr,
            )
        return

    elif cmd == "rules":
        fr = FeedRules()
        print(fr.summary())
        return

    elif cmd == "rule-add":
        if len(rest) < 3:
            print(
                "Usage: molt rule-add <kill|select> <title|author|submolt> <pattern>"
                " [--submolt name] [--expires days]",
                file=sys.stderr,
            )
            sys.exit(1)
        action, field, pattern = rest[0], rest[1], rest[2]
        submolts = None
        expires_days = None
        i = 3
        while i < len(rest):
            if rest[i] == "--submolt" and i + 1 < len(rest):
                submolts = submolts or []
                submolts.append(rest[i + 1])
                i += 2
            elif rest[i] == "--expires" and i + 1 < len(rest):
                expires_days = int(rest[i + 1])
                i += 2
            else:
                i += 1
        fr = FeedRules()
        fr.add(action, field, pattern, submolts=submolts, expires_days=expires_days)
        result = {
            "added": {"action": action, "field": field, "pattern": pattern},
            "total": len(fr.rules),
        }

    elif cmd == "rule-rm":
        if not rest:
            print("Usage: molt rule-rm <index>", file=sys.stderr)
            sys.exit(1)
        fr = FeedRules()
        fr.remove(int(rest[0]))
        result = {"removed": int(rest[0]), "total": len(fr.rules)}

    elif cmd == "catch-up":
        cursor = FeedCursor()
        cursor.catch_up()
        print("Marked all feeds as caught up.")
        return

    elif cmd == "unseen":
        sort = rest[0] if len(rest) > 0 else "hot"
        limit = int(rest[1]) if len(rest) > 1 else 25
        data = client.feed(sort=sort, limit=limit)
        posts = data.get("posts", [])
        cursor = FeedCursor()
        unseen = cursor.unseen(posts, source=sort)
        print(oneline_feed(unseen))
        if len(unseen) < len(posts):
            print(
                f"\n({len(posts) - len(unseen)} previously seen posts hidden)",
                file=sys.stderr,
            )
        cursor.mark_seen(posts, source=sort)
        return

    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        sys.exit(1)

    json.dump(result, sys.stdout, separators=(",", ":"))
    print()


if __name__ == "__main__":
    main()
