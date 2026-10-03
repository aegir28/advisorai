# registry

Configuration, not code.

- `models.yaml`: model tiers per provider, enablement, and prices. Loaded by `backend/app/ai/registry.py`.
  Edit this file to point a tier at a real model (docs/handoff-ai-phase.md, "Enabling real calls").
- Specialist-agent registry: the five specialty contracts are registered in code
  (`backend/app/agents/registry.py`); their prompts live in `backend/app/agents/prompts/` (see that folder's README).
