"""A deterministic in-memory retriever for tests and demos: ranks by shared words. It is a test double that
satisfies the `EvidenceRetriever` contract. It is not embeddings and not a recommendation for how to
retrieve."""

import re

from app.evidence.contracts import EvidenceItem, RetrievalQuery, RetrievedEvidence

_WORD = re.compile(r"[a-z0-9]+")


def _words(text: str) -> set[str]:
    return set(_WORD.findall(text.casefold()))


class KeywordRetriever:
    def __init__(self, items: list[EvidenceItem]) -> None:
        self._items = items

    async def retrieve(self, query: RetrievalQuery) -> list[RetrievedEvidence]:
        wanted = _words(query.text)
        scored = []
        for item in self._items:
            if query.origin is not None and item.origin != query.origin:
                continue
            overlap = len(wanted & _words(item.snippet))
            if overlap:
                scored.append((overlap, item))
        # Best first; ties broken by id so the order is stable.
        scored.sort(key=lambda pair: (-pair[0], pair[1].id))
        return [
            RetrievedEvidence(item=item, score=float(score), rank=rank)
            for rank, (score, item) in enumerate(scored[: query.k], start=1)
        ]
