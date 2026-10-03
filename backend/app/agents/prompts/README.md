# Specialist-agent prompts

This is where the specialist prompts go. One folder per specialty, one file per version:

    prompts/<specialty_id>/v<N>.md

A file whose first line starts with `<!-- PLACEHOLDER` is treated as "not written": `PromptStore.get` refuses it
(`PromptNotWritten`), so an agent with no real prompt cannot run by accident. Replace the file's whole content with
the real prompt, then bump `prompt_version` in `registry/agents.yaml` if you add a new version rather than edit v1.

Rules the repository enforces around prompts (not in the prompt text):

- The model sees only de-identified, structured input (see `app/safety/deidentify.py`). Do not put names or
  identifiers in a prompt.
- The model must return the `specialist_report.v1` shape (`app/schemas/specialist_report.py`); the gateway
  validates it and rejects anything else.
- Each prompt's SHA-256 is recorded with the call context so a result can be tied to the exact prompt text.
- Prompts are version-controlled files, never database rows or environment variables.
