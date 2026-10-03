"""AI Gateway: the ONLY door to a model provider (blueprint Part 5; ADR 0011).

Nothing outside this package talks to a provider. Everything that reaches a model passes through
`AIGateway.invoke`: de-identify -> route -> budget -> call (timeout, retries) -> validate -> meter -> audit.

This package contains infrastructure only. It contains no prompts, no clinical logic and no workflow
topology; those are added by the people who design them (see docs/handoff-ai-phase.md).
"""
