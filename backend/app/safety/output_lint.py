"""Output safety lint: a deterministic gate between model output and a patient.

AdvisorAI prepares a person for a doctor visit. It never tells them to stop, start or change a medicine,
never says a doctor is wrong, never ranks doctors, never states a diagnosis as settled fact when the
record does not, and never invents a reference. This module is the floor under that promise: pattern
rules over text, applied to every model-written string before it is stored or shown. It is not a medical
judgement and not a substitute for the prompt's own instructions or for clinical review; it is the part
that does not depend on a model behaving.

A violation carries a rule code and the sentence number only, never the text, so a failing report cannot
leak its own content through a log or an error. Discussion framing is allowed ("Ask whether ... could be
reviewed"): a sentence that is a question, or that sends the person to their doctor, is not an
instruction.

Rules (codes):
  medication_directive   an instruction to stop / start / change / skip / double a medicine or its dose
  prescribing            "take 10 mg", "I prescribe": dosing instructions
  doctor_wrong           says a doctor is wrong, mistaken or negligent, or that a diagnosis was a mistake
  doctor_ranking         ranks, scores or picks a doctor/opinion, or says to switch doctors
  unsupported_certainty  "definitely", "proves", "100%", "guaranteed" and similar
  definitive_diagnosis   "you have / you are suffering from ..." for anything that is not a documented fact
  unsourced_citation     a free-text reference (PMID, DOI, "et al.", a URL): only registered sources may
  unknown_evidence_id    an evidence id that is not in the case's evidence index
"""

import re
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from typing import Any, Literal

TextKind = Literal["patient_fact", "interpretation", "external_evidence", "template", "question"]

_VERBS = (
    r"stop|discontinue|cease|quit|skip|start|begin|restart|resume|increase|decrease|reduce|lower|raise|double|"
    r"cut\s+(?:down|back)|come\s+off|go\s+off|wean\s+off|"
    r"halve|switch|change|adjust|cut"
)
_OBJECT = (
    r"(?:taking|using|your|the|this|that|these|those|his|her|any|all)\b(?:\s+[\w'-]+){0,4}?\s+"
    r"(?:dose|doses|dosage|medicine|medicines|medication|medications|tablet|tablets|pill|pills|drug|drugs|"
    r"treatment|therapy|injection|inhaler|insulin|statin|mg|[a-z]+(?:pril|sartan|olol|statin|mab|cillin|zole|"
    r"formin|dipine|oxetine|pram))\b"
)
_STOP_TAKING = re.compile(
    rf"\b(?:{_VERBS})\s+(?:taking|using)\b|\b(?:do\s+not|don'?t|never|avoid|refrain\s+from)\s+(?:take|taking|use|using)\b",
    re.I,
)
_VERB_OBJECT = re.compile(rf"\b(?:{_VERBS})\s+{_OBJECT}", re.I)
_MODAL = re.compile(
    r"\b(?:you\s+(?:should|must|need\s+to|ought\s+to|have\s+to)|i\s+(?:recommend|advise|suggest|urge)|"
    r"we\s+(?:recommend|advise|suggest|urge)|it\s+is\s+(?:best|safest|advisable|wise)\s+to|make\s+sure\s+(?:you|to)|"
    r"be\s+sure\s+to|do\s+not|don'?t|never|always)\b",
    re.I,
)
_DOSE_INSTRUCTION = re.compile(
    r"\b(?:take|use|inject|swallow)\s+\d+(?:\.\d+)?\s*(?:mg|mcg|µg|g|ml|units?|tablets?|pills?|capsules?)\b|"
    r"\bi\s+(?:prescribe|am\s+prescribing)\b|\bprescription\s+for\s+you\b",
    re.I,
)
_DOCTOR = (
    r"(?:doctor|doctors|dr\.?|physician|cardiologist|surgeon|specialist|consultant|clinician|gp|radiologist)"
)
_DOCTOR_WRONG = re.compile(
    rf"\b(?:your|the|current|treating)\s+(?:\w+\s+)?{_DOCTOR}\s+(?:is|was|has\s+been|may\s+be|might\s+be|seems|"
    r"appears\s+to\s+be|got\s+it|made\s+a)\s*(?:wrong|incorrect|mistaken|negligent|incompetent|a\s+mistake|"
    r"an\s+error|misdiagnos\w+)|\bmisdiagnos\w*|\bwrong\s+diagnosis\b|\b(?:should\s+not|shouldn'?t)\s+have\s+"
    r"(?:been\s+)?(?:prescribed|operated|treated|diagnosed)\b|\bnegligen\w+\b|\bmalpractice\b",
    re.I,
)
_RANKING = re.compile(
    rf"\b(?:{_DOCTOR}|opinion)\s+[ab12]\s+(?:is|was|seems|appears)\s+(?:better|more\s+(?:accurate|reliable|correct|"
    r"trustworthy|qualified)|correct|right|the\s+(?:better|winner|best))\b|\b(?:better|best|worse|worst)\s+"
    rf"{_DOCTOR}\b|\bwinner\b|\b(?:switch|change)\s+(?:your\s+)?(?:{_DOCTOR}|to\s+(?:another|a\s+different)\s+"
    rf"{_DOCTOR})\b|\bgo\s+with\s+(?:the\s+)?(?:first|second)\s+(?:{_DOCTOR}|opinion)\b|\b(?:rank(?:ed|ing)?|"
    rf"score[sd]?)\s+(?:the\s+)?(?:{_DOCTOR}s?|opinions?)\b|\bmore\s+(?:qualified|experienced|trustworthy)\s+than\b",
    re.I,
)
_CERTAINTY = re.compile(
    r"\b(?:definitely|certainly|undoubtedly|unquestionably|without\s+(?:a\s+)?doubt|guaranteed?|"
    r"proves?\s+that|is\s+certain|are\s+certain|beyond\s+doubt|no\s+doubt)\b|\b100\s*%",
    re.I,
)
_DEFINITIVE_DIAGNOSIS = re.compile(
    r"\byou\s+(?:definitely\s+|clearly\s+)?(?:have|are\s+suffering\s+from|suffer\s+from|are\s+diagnosed\s+with)\s+"
    r"(?!been\b|had\b|taken\b|used\b|received\b|got\b|told\b|noted\b|reported\b|mentioned\b|asked\b|shown\b|"
    r"seen\b|made\b|given\b|(?:two|three|one|several|some|many|more|no|any|a\s+(?:question|list|copy|few))\b)"
    r"(?:an?\s+|the\s+)?[a-z][\w'-]*(?:\s+[\w'-]+){0,3}\b|\bthis\s+(?:confirms|proves|means)\s+(?:that\s+)?you\b|"
    r"\bit\s+is\s+(?:a\s+)?(?:clear|certain)\s+(?:case\s+of|sign\s+of)\b",
    re.I,
)
_CITATION = re.compile(
    r"\bPMID\s*:?\s*\d+|\bdoi\s*:|\bdoi\.org/|\bet\s+al\b|\bhttps?://|\bwww\.|\[\d{1,3}(?:\s*[,-]\s*\d{1,3})*\]|"
    r"\(\s*[A-Z][a-z]+(?:\s+et\s+al\.?)?,?\s+(?:19|20)\d{2}\s*\)",
)
_DISCUSSION_CUE = re.compile(
    r"\b(?:ask|asks|asking|discuss|discussing|talk\s+(?:to|with)|raise\s+(?:it\s+)?with|bring\s+(?:it\s+)?up|"
    r"whether|if\s+it\s+(?:would|could|might)|worth\s+asking|question|to\s+your\s+doctor|with\s+your\s+doctor)\b",
    re.I,
)
_PROTECTIVE = re.compile(
    r"\b(?:do\s+not|don'?t|never|avoid)\b[^.?!]*\b(?:on\s+your\s+own|without\s+(?:first\s+)?(?:asking|talking|"
    r"speaking|checking|consulting|discussing)|before\s+(?:talking|speaking|checking|asking|discussing))\b",
    re.I,
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass(frozen=True, slots=True)
class LintViolation:
    rule: str
    sentence: int

    def __str__(self) -> str:
        return f"{self.rule}@{self.sentence}"


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]


def _is_question_or_discussion(sentence: str) -> bool:
    return sentence.rstrip().endswith("?") or bool(_DISCUSSION_CUE.search(sentence))


def lint_text(text: str, kind: TextKind = "interpretation") -> list[LintViolation]:
    """Violations in one piece of model-written text. Codes and sentence numbers only; never the text."""
    out: list[LintViolation] = []
    for number, sentence in enumerate(_sentences(text), start=1):
        framed = _is_question_or_discussion(sentence)
        modal = bool(_MODAL.search(sentence))
        directive = bool(_STOP_TAKING.search(sentence) or _VERB_OBJECT.search(sentence))
        # "Stop taking X" is an instruction unless the sentence only RAISES it for a doctor
        # ("Ask whether to stop X"). A modal ("you should stop ...") is always an instruction,
        # even next to a discussion cue.
        protective = bool(_PROTECTIVE.search(sentence))  # "do not change any medicine on your own"
        if directive and not protective and (not framed or (modal and not sentence.rstrip().endswith("?"))):
            out.append(LintViolation("medication_directive", number))
        if _DOSE_INSTRUCTION.search(sentence) and not sentence.rstrip().endswith("?"):
            out.append(LintViolation("prescribing", number))
        if _DOCTOR_WRONG.search(sentence):
            out.append(LintViolation("doctor_wrong", number))
        if _RANKING.search(sentence):
            out.append(LintViolation("doctor_ranking", number))
        if _CERTAINTY.search(sentence):
            out.append(LintViolation("unsupported_certainty", number))
        if kind != "patient_fact" and _DEFINITIVE_DIAGNOSIS.search(sentence):
            out.append(LintViolation("definitive_diagnosis", number))
        if _CITATION.search(sentence):
            out.append(LintViolation("unsourced_citation", number))
    return out


def lint_evidence_ids(cited: Iterable[str], known: Collection[str]) -> list[LintViolation]:
    """Every cited evidence id must exist in the case's evidence index (no fabricated evidence)."""
    return [LintViolation("unknown_evidence_id", i) for i, c in enumerate(cited, start=1) if c not in known]


# Keys whose string values are identifiers or enums, never prose.
_NON_PROSE_KEYS = frozenset(
    {
        "id",
        "ids",
        "schema_version",
        "case_id",
        "run_id",
        "doc_id",
        "specialist",
        "specialist_id",
        "agent",
        "kind",
        "status",
        "priority",
        "tier",
        "type",
        "group",
        "flag",
        "confidence",
        "impact",
        "importance",
        "relationship",
        "audience",
        "category",
        "version",
        "name",
        "title",
        "publisher",
        "licence",
        "section",
        "factor",
        "weight",
        "label",
        "snippet",
        "generated_at",
        "opinion_a_label",
        "opinion_b_label",
        "reviewer",
    }
)


_KINDS = frozenset({"patient_fact", "interpretation", "external_evidence", "template", "question"})


def prose_strings(
    value: Any, key: str = "", kind: TextKind = "interpretation"
) -> Iterable[tuple[str, str, TextKind]]:
    """(key, text, kind) for every prose string in a dumped model. Skips ids, enums and quoted source
    snippets (a snippet is the patient's own document text shown as a quote, not model-written prose).
    A string inherits the `kind` of the nearest enclosing object that has one."""
    if isinstance(value, str):
        if key not in _NON_PROSE_KEYS and not key.endswith(("_id", "_ids", "_refs")) and len(value) >= 12:
            yield key, value, kind
    elif isinstance(value, dict):
        own = value.get("kind")
        here: TextKind = own if isinstance(own, str) and own in _KINDS else kind  # type: ignore[assignment]
        for k, v in value.items():
            yield from prose_strings(v, str(k), here)
    elif isinstance(value, list):
        for v in value:
            yield from prose_strings(v, key, kind)


def lint_document(dumped: Any) -> list[tuple[str, LintViolation]]:
    """Lint every prose string of a dumped contract object. Returns (field key, violation); never text."""
    return [(key, v) for key, text, kind in prose_strings(dumped) for v in lint_text(text, kind)]
