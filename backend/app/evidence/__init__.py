"""Evidence infrastructure: contracts and deterministic checks for evidence, claims, verification and
retrieval.

No embeddings, no vector store, no retrieval workflow: those are chosen and built later. This package fixes
the
shapes they must produce (`EvidenceItem`, `RetrievedEvidence`, `VerificationResult`) and the structural checks
that keep an unsourced claim out of a patient-facing report."""
