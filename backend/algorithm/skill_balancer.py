"""Skill balancer — soft preference optimiser (v0.3).

TODO: Implement in v0.3. This module will post-process a RotationPlan to
swap outfield players between slots to minimise variance in per-slot
outfield skill totals.
"""

from backend.models.rotation import RotationPlan


def balance_skills(plan: RotationPlan) -> RotationPlan:
    """Optimise skill balance across slots (soft preference). Placeholder for v0.3."""
    # TODO: implement skill balancing optimisation
    return plan
