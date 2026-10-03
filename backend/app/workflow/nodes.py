"""Where workflow node types are registered.

This is deliberately empty. The clinical workflow is designed by people, not generated here. To add a step:

1. write a node (an `AINode` subclass for a model call, or a plain `Node`) in `app/workflow/`;
2. register it below under a node type name, e.g. `registry.register("docintel.classify", MyNode(gateway))`;
3. reference that type from a versioned definition in `workflows/<name>.v<N>.yaml`.

The engine refuses to start a run whose definition names an unregistered type (`node_type_unavailable`), so a
half-wired workflow fails loudly instead of silently skipping steps.
"""

from app.ai.gateway import AIGateway
from app.workflow.engine import NodeRegistry


def register_nodes(registry: NodeRegistry, gateway: AIGateway) -> None:
    """Register node types. Intentionally registers none yet."""
    del registry, gateway  # used once the first node exists
