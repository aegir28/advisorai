"""De-identification: the PII boundary in front of every model call (blueprint Part 5; ADR 0011).

Identity fields (name, email, phone, hospital IDs) live in their own columns and are never part of an AI
context (case.v1 says the same). But free text a person typed (`cases.concern`, `proposed_treatment`, a
document title) and text read from a document can still carry identity. Everything that is not fixed template
text passes through `deidentify` before it reaches a prompt, and the gateway re-checks the final prompt with
`find_residual` and refuses to send it if anything identifying is left.

This is rule-based, deterministic and best-effort. It is a safety net, not a guarantee: the prototype is
synthetic-only (ADR 0004), and real data stays locked out until a clinician-reviewed de-identification
standard replaces this module. Dates of visits, lab values and doses are clinical content and are kept; only
dates of birth are removed.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class DeidentificationResult:
    text: str
    # Category -> number of replacements. Counts only; never the removed text.
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def changed(self) -> bool:
        return bool(self.counts)


_NAME = r"[A-Z][a-z]+(?:[ '\-][A-Z][a-z]+){0,3}"

# (category, pattern, replacement). Order matters: specific before general.
_RULES: list[tuple[str, re.Pattern[str], str]] = [
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"), "[EMAIL]"),
    ("url", re.compile(r"\bhttps?://[^\s<>\"']+|\bwww\.[^\s<>\"']+", re.I), "[URL]"),
    # Indian Aadhaar-style 12 digits (optionally grouped 4-4-4) and PAN.
    ("government_id", re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}\b"), "[ID]"),
    ("government_id", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), "[ID]"),
    # Phone numbers: optional country code, 10 digits, optional separators.
    ("phone", re.compile(r"(?<![\w/.])(?:\+\d{1,3}[ -]?)?(?:\d[ -]?){9}\d(?![\w/])"), "[PHONE]"),
    # Hospital / record identifiers introduced by a label.
    (
        "record_id",
        re.compile(
            r"(?i)\b(?:MRN|UHID|patient\s*id|hospital\s*id|record\s*(?:no|number)|IP\s*no|OP\s*no)\b\s*[:#.-]?\s*[A-Za-z0-9/-]{3,}"
        ),
        "[ID]",
    ),
    # Date of birth, labelled.
    (
        "date_of_birth",
        re.compile(
            r"(?i)\b(?:DOB|date\s+of\s+birth|born\s+on)\b\s*[:.-]?\s*"
            r"(?:\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}\s+[a-z]{3,9}\.?\s+\d{4}|[a-z]{3,9}\.?\s+\d{1,2},?\s+\d{4})"
        ),
        "[DATE_OF_BIRTH]",
    ),
    # Labelled names and titled names.
    (
        "name",
        re.compile(
            rf"(?i:\b(?:patient(?:'s)?\s+name|name\s+of\s+patient|name|pt\.?\s*name)\b)\s*[:.-]\s*{_NAME}"
        ),
        "[NAME]",
    ),
    ("name", re.compile(rf"\b(?:Mr|Mrs|Ms|Miss|Shri|Smt|Dr)\.?\s+{_NAME}"), "[NAME]"),
    # Street-style addresses and 6-digit PIN codes after an address cue.
    (
        "address",
        re.compile(r"(?i)\b(?:address|resident\s+of|residing\s+at)\b\s*[:.-]?\s*[^\n.;]{6,80}"),
        "[ADDRESS]",
    ),
]

# What `find_residual` looks for after de-identification (high-signal categories only).
_RESIDUAL = {
    "email": _RULES[0][1],
    "url": _RULES[1][1],
    "government_id": _RULES[2][1],
    "phone": _RULES[4][1],
}


def deidentify(text: str, *, known_identifiers: Iterable[str] = ()) -> DeidentificationResult:
    """Replace identifying strings with fixed placeholders. `known_identifiers` are exact strings the system
    already knows are identity (the person's own name, email, phone from their profile): matched
    case-insensitively and replaced wherever they appear, which catches names the patterns cannot."""
    counts: dict[str, int] = {}
    out = text

    for ident in sorted(
        {i.strip() for i in known_identifiers if i and len(i.strip()) >= 3}, key=len, reverse=True
    ):
        pattern = re.compile(re.escape(ident), re.I)
        out, n = pattern.subn("[NAME]", out)
        if n:
            counts["known_identifier"] = counts.get("known_identifier", 0) + n

    for category, pattern, replacement in _RULES:
        out, n = pattern.subn(replacement, out)
        if n:
            counts[category] = counts.get(category, 0) + n
    return DeidentificationResult(out, counts)


def find_residual(text: str) -> list[str]:
    """Categories of identifying patterns still present. Empty means clean (as far as the rules can tell)."""
    return sorted(category for category, pattern in _RESIDUAL.items() if pattern.search(text))
