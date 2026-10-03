"""Reading level of patient-facing text: Flesch-Kincaid grade, deterministic and dependency-free.

The target for the patient report is roughly a 5th/6th class reading level (US grade about 5 to 7) without
losing medical meaning. This is a measurement and a gate for WARNINGS, not a rewriting tool: a medical word
such as "angiography" legitimately raises the score, so the report builder reports the grade per section and
flags sections above `MAX_GRADE` for review instead of silently dumbing the text down.
"""

import re

MAX_GRADE = 8.0  # a little above the 6th-class target, because necessary medical terms add syllables
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
_SENTENCE = re.compile(r"[.!?]+(?:\s|$)")
_VOWEL_GROUP = re.compile(r"[aeiouy]+")


def syllables(word: str) -> int:
    w = word.lower().strip("'-")
    if not w:
        return 0
    count = len(_VOWEL_GROUP.findall(w))
    if w.endswith("e") and not w.endswith(("le", "ee", "ie")) and count > 1:
        count -= 1  # silent final e
    if w.endswith("es") and count > 1 and not w.endswith(("ses", "zes", "ces", "ges", "xes")):
        count -= 1
    if w.endswith("ed") and count > 1 and not w.endswith(("ted", "ded")):
        count -= 1
    return max(count, 1)


def grade_level(text: str) -> float:
    """Flesch-Kincaid grade of `text`; 0.0 for text with no words."""
    words = _WORD.findall(text)
    if not words:
        return 0.0
    sentences = max(len(_SENTENCE.findall(text)), 1)
    syl = sum(syllables(w) for w in words)
    grade = 0.39 * (len(words) / sentences) + 11.8 * (syl / len(words)) - 15.59
    return round(max(grade, 0.0), 1)


def reading_ok(text: str, max_grade: float = MAX_GRADE) -> bool:
    return grade_level(text) <= max_grade
