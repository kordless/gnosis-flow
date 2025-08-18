from __future__ import annotations

import re
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from rapidfuzz import fuzz
    HAVE_RAPIDFUZZ = True
except Exception:
    HAVE_RAPIDFUZZ = False


@dataclass
class MatchRule:
    name: str
    include: List[str] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)
    regex: Optional[str] = None
    fuzzy: List[str] = field(default_factory=list)
    threshold: float = 0.8
    scope: str = "auto"  # "log" | "file" | "auto"
    lines_before: int = 1
    lines_after: int = 3
    action: Dict[str, Any] = field(default_factory=dict)

    def compile(self):
        self._regex = re.compile(self.regex, re.IGNORECASE | re.MULTILINE | re.DOTALL) if self.regex else None
        return self


def load_rules(path: Path) -> List[MatchRule]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rules = []
    for item in data.get("rules", []):
        r = MatchRule(
            name=item.get("name", "rule"),
            include=item.get("include", []),
            exclude=item.get("exclude", []),
            regex=item.get("regex"),
            fuzzy=item.get("fuzzy", []),
            threshold=float(item.get("threshold", 0.8)),
            scope=item.get("scope", "auto"),
            lines_before=int(item.get("lines_before", 1)),
            lines_after=int(item.get("lines_after", 3)),
            action=item.get("action", {}),
        ).compile()
        rules.append(r)
    return rules


def default_rules_yaml() -> str:
    return """
rules:
  - name: Errors in logs
    include: ["**/*.log"]
    regex: "(ERROR|CRITICAL)"
    lines_before: 2
    lines_after: 5
    action:
      type: notify

  - name: DB failures
    include: ["**/*.log"]
    fuzzy: ["failed to connect", "timeout contacting db", "connection refused"]
    threshold: 0.85
    lines_before: 1
    lines_after: 4
    action:
      type: ai_tool
      provider: anthropic
      model: opus
      prompt: |
        Summarize the error and propose a fix with steps.
"""


def ratio(a: str, b: str) -> float:
    if HAVE_RAPIDFUZZ:
        try:
            return fuzz.ratio(a, b) / 100.0
        except Exception:
            pass
    # fallback
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio()


def fuzzy_hit(line: str, terms: List[str], threshold: float) -> Optional[Dict[str, Any]]:
    if not terms:
        return None
    best = (0.0, None)
    for t in terms:
        s = ratio(t.lower(), line.lower())
        if s > best[0]:
            best = (s, t)
    if best[0] >= max(0.6, threshold - 0.2):
        return {"term": best[1], "similarity": round(best[0], 3)}
    return None


def path_matches(path: Path, include: List[str], exclude: List[str]) -> bool:
    from fnmatch import fnmatch
    s = str(path)
    if include and not any(fnmatch(s, pat) for pat in include):
        return False
    if exclude and any(fnmatch(s, pat) for pat in exclude):
        return False
    return True


def evaluate_log_line(path: Path, line: str, rules: List[MatchRule]) -> List[Dict[str, Any]]:
    hits = []
    for r in rules:
        if not path_matches(path, r.include, r.exclude):
            continue
        # regex first
        if r._regex and r._regex.search(line):
            hits.append({"rule": r.name, "type": "regex", "action": r.action})
            continue
        # fuzzy terms
        h = fuzzy_hit(line, r.fuzzy, r.threshold)
        if h:
            hits.append({"rule": r.name, "type": "fuzzy", "action": r.action, **h})
    return hits


def evaluate_file_text(path: Path, text: str, rules: List[MatchRule], window: int = 65536) -> List[Dict[str, Any]]:
    """Scan text with regex/fuzzy using windows for large content."""
    n = len(text)
    windows = []
    if n <= 10_000_000:  # ~10MB
        windows = [(0, n)]
    else:
        # first, last, and 3 evenly spaced windows
        windows = [(0, min(window, n))]
        windows.append((max(0, n - window), n))
        for k in range(1, 4):
            start = int(n * k / 4)
            windows.append((max(0, start - window // 2), min(n, start + window // 2)))

    hits: List[Dict[str, Any]] = []
    for (a, b) in windows:
        chunk = text[a:b]
        lines = chunk.splitlines()
        for r in rules:
            if not path_matches(path, r.include, r.exclude):
                continue
            if r._regex and r._regex.search(chunk):
                hits.append({"rule": r.name, "type": "regex", "action": r.action, "span": [a, b]})
                continue
            if r.fuzzy:
                # scan line-by-line quickly
                for ln in lines:
                    h = fuzzy_hit(ln, r.fuzzy, r.threshold)
                    if h:
                        hits.append({"rule": r.name, "type": "fuzzy", "action": r.action, **h})
                        break
    return hits

