"""Splits text into the tokens the schedule grammar reads."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True, slots=True)
class Tok:
    """One lexical token.

    ``kind`` is one of:

    - ``word``: a run of letters
    - ``num``: a run of digits
    - ``ord``: an ordinal such as "15th"
    - ``iso``: "2026-12-03"
    - ``slash``: "12/3" or "12/3/2026"
    - ``clock``: "17:30"
    - ``sym``: any other single character
    - ``stop``: a span the caller masked out, such as "#home"; no phrase
      crosses it

    ``text`` is lowercased. ``glued`` is true when no whitespace separates the
    token from the one before it.
    """

    kind: str
    text: str
    start: int
    end: int
    glued: bool


_TOKEN = re.compile(
    r"""
      (?P<iso>\d{4}-\d{1,2}-\d{1,2})(?![\d-])
    | (?P<slash>\d{1,2}/\d{1,2}(?:/(?:\d{4}|\d{2}))?)(?![\d/])
    | (?P<clock>\d{1,2}:\d{2})(?![\d:])
    | (?P<ord>\d{1,2}(?:st|nd|rd|th))(?![^\W_])
    | (?P<num>\d+)
    | (?P<word>[^\W\d_]+)
    | (?P<sym>.)
    """,
    re.VERBOSE | re.IGNORECASE | re.DOTALL,
)


def lex(text: str, masked: Sequence[tuple[int, int]] = ()) -> list[Tok]:
    """Tokenize ``text``; each ``masked`` (start, end) span becomes a stop token."""
    toks: list[Tok] = []
    masks = sorted(masked)
    mask = 0
    pos = 0
    prev_end = -1
    while pos < len(text):
        while mask < len(masks) and masks[mask][1] <= pos:
            mask += 1
        if mask < len(masks) and masks[mask][0] <= pos:
            end = masks[mask][1]
            toks.append(Tok("stop", text[pos:end], pos, end, pos == prev_end))
            pos = prev_end = end
            continue
        if text[pos].isspace():
            pos += 1
            continue
        limit = masks[mask][0] if mask < len(masks) else len(text)
        m = _TOKEN.match(text, pos, limit)
        assert m is not None and m.lastgroup is not None  # "sym" matches anything
        toks.append(Tok(m.lastgroup, m.group().lower(), pos, m.end(), pos == prev_end))
        pos = prev_end = m.end()
    return toks
