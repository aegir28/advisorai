"""The routing plan: which specialists were chosen for a case and why. Mirrors `RoutingPlanSchema`.

This is the SHAPE of a routing decision. Which specialties are chosen is decided by whoever designs the router
rules (see app/router), not by this contract."""

from typing import Literal

from .common import SpecialistId, WireModel


class RoutingSelection(WireModel):
    specialist: SpecialistId
    priority: Literal["mandatory", "optional"]
    reason: str


class RoutingNotSelected(WireModel):
    name: str
    why: str


class RoutingPlan(WireModel):
    selected: list[RoutingSelection]
    not_selected: list[RoutingNotSelected]
    missing_for_routing: list[str]
