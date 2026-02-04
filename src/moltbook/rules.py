# ABOUTME: Pattern-based feed rules for Moltbook agents (kill/select).
# ABOUTME: Inspired by nn's kill file — auto-hide or auto-highlight posts by pattern.

import re
from datetime import datetime, timezone, timedelta

from moltbook.helpers import (
    _author_name,
    _submolt_name,
    resolve_state_path,
    load_json,
    save_json,
)


def _match(pattern, text):
    """Match a pattern against text. /regex/ for regex, else substring."""
    if not text:
        return False
    if pattern.startswith("/") and pattern.endswith("/") and len(pattern) > 2:
        try:
            return bool(re.search(pattern[1:-1], text, re.IGNORECASE))
        except re.error:
            return False
    return pattern.lower() in text.lower()


def _get_field(post, field):
    """Extract a field value from a post dict."""
    if field == "author":
        return _author_name(post.get("author"))
    if field == "submolt":
        return _submolt_name(post.get("submolt"))
    return post.get(field, "")


class FeedRules:
    """Pattern-based kill/select rules for feed filtering.

    Kill rules hide matching posts; select rules highlight them.
    Patterns are substring matches (case-insensitive) by default,
    or regex when wrapped in /slashes/.

    Usage::

        rules = FeedRules()
        rules.add("kill", "title", "test post please ignore")
        rules.add("select", "author", "bicep", submolts=["general"])
        result = rules.apply(posts)
        # result = {"keep": [...], "killed": [...], "selected": [...]}
    """

    def __init__(self, rules_path=None):
        if rules_path is None:
            rules_path = resolve_state_path("rules.json")
        self.rules_path = rules_path
        self._data = load_json(rules_path, default=lambda: {"rules": []})

    def _save(self):
        save_json(self.rules_path, self._data)

    @property
    def rules(self):
        """List of active (non-expired) rules."""
        self.prune()
        return list(self._data.get("rules", []))

    def add(self, action, field, pattern, submolts=None, expires_days=None):
        """Add a kill or select rule.

        Args:
            action: "kill" or "select"
            field: "title", "author", or "submolt"
            pattern: substring (case-insensitive) or /regex/
            submolts: optional list of submolts to scope the rule to
            expires_days: auto-expire after N days (None = permanent)
        """
        if action not in ("kill", "select"):
            raise ValueError(f"action must be 'kill' or 'select', got {action!r}")
        if field not in ("title", "author", "submolt"):
            raise ValueError(
                f"field must be 'title', 'author', or 'submolt', got {field!r}"
            )

        now = datetime.now(timezone.utc)
        rule = {
            "action": action,
            "field": field,
            "pattern": pattern,
            "submolts": submolts,
            "created": now.isoformat(),
            "expires": (now + timedelta(days=expires_days)).isoformat()
            if expires_days
            else None,
        }
        rules = self._data.get("rules", [])
        rules.append(rule)
        self._data["rules"] = rules
        self._save()

    def remove(self, rule_id):
        """Remove a rule by index."""
        rules = self._data.get("rules", [])
        if 0 <= rule_id < len(rules):
            rules.pop(rule_id)
            self._data["rules"] = rules
            self._save()

    def prune(self):
        """Remove expired rules."""
        now = datetime.now(timezone.utc)
        rules = self._data.get("rules", [])
        kept = []
        for r in rules:
            expires = r.get("expires")
            if expires:
                try:
                    exp_dt = datetime.fromisoformat(expires)
                    if exp_dt <= now:
                        continue
                except (ValueError, TypeError):
                    pass
            kept.append(r)
        if len(kept) != len(rules):
            self._data["rules"] = kept
            self._save()

    def _rule_matches(self, rule, post):
        """Check if a single rule matches a post."""
        submolts = rule.get("submolts")
        if submolts:
            post_submolt = _get_field(post, "submolt")
            if post_submolt not in submolts:
                return False
        return _match(rule["pattern"], _get_field(post, rule["field"]))

    def apply(self, posts):
        """Apply all rules to a list of posts.

        Returns a dict with three lists:
            keep: posts not matched by any rule
            killed: posts matched by a kill rule
            selected: posts matched by a select rule
        """
        self.prune()
        rules = self._data.get("rules", [])
        keep, killed, selected = [], [], []

        for post in posts:
            post_killed = False
            post_selected = False
            for rule in rules:
                if self._rule_matches(rule, post):
                    if rule["action"] == "kill":
                        post_killed = True
                    elif rule["action"] == "select":
                        post_selected = True
            if post_killed:
                killed.append(post)
            elif post_selected:
                selected.append(post)
                keep.append(post)
            else:
                keep.append(post)

        return {"keep": keep, "killed": killed, "selected": selected}

    def apply_comments(self, comments):
        """Kill matching comments from a comment tree.

        Like FeedFilter.filter_comments, promotes non-killed replies
        when a parent is killed.
        """
        self.prune()
        kill_rules = [r for r in self._data.get("rules", []) if r["action"] == "kill"]
        if not kill_rules:
            return comments
        return self._filter_comment_tree(comments, kill_rules)

    def _filter_comment_tree(self, comments, kill_rules):
        result = []
        for c in comments:
            replies = c.get("replies", [])
            filtered_replies = (
                self._filter_comment_tree(replies, kill_rules) if replies else []
            )
            killed = any(self._rule_matches(r, c) for r in kill_rules)
            if killed:
                result.extend(filtered_replies)
            else:
                if filtered_replies != replies:
                    c = dict(c, replies=filtered_replies)
                result.append(c)
        return result

    def summary(self):
        """Compact text summary of active rules."""
        rules = self.rules
        if not rules:
            return "No feed rules configured."
        lines = []
        for i, r in enumerate(rules):
            scope = f" in {','.join(r['submolts'])}" if r.get("submolts") else ""
            expires = ""
            if r.get("expires"):
                expires = f" (expires {r['expires'][:10]})"
            lines.append(
                f"  [{i}] {r['action']} {r['field']}={r['pattern']!r}{scope}{expires}"
            )
        return f"Feed rules ({len(rules)}):\n" + "\n".join(lines)
