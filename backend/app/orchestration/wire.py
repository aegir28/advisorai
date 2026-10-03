"""`make`: build a wire model from keyword arguments, omitting the ones that are None.

The wire contracts mean "optional" as ABSENT, never null (`WireModel`), so passing `flag=None` is rejected.
Orchestration code computes optional values (a flag, a reason, a note) that are often None; this helper drops
them so the contract's rule is kept without an if-ladder at every call site.
"""

from typing import Any

from pydantic import BaseModel


def make[T: BaseModel](cls: type[T], **fields: Any) -> T:
    return cls(**{k: v for k, v in fields.items() if v is not None})
