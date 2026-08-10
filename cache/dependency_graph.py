from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable


class EffectDependencyGraph:
    """Map source dependencies to the effect plans that must be rebuilt."""

    def __init__(self) -> None:
        self._by_dependency: dict[str, set[str]] = defaultdict(set)
        self._by_plan: dict[str, set[str]] = {}

    def register(self, plan_id: str, dependencies: Iterable[str]) -> None:
        old_dependencies = self._by_plan.get(plan_id, set())
        for dependency in old_dependencies:
            self._by_dependency[dependency].discard(plan_id)
        current = set(dependencies)
        self._by_plan[plan_id] = current
        for dependency in current:
            self._by_dependency[dependency].add(plan_id)

    def invalidate(self, dependency: str) -> set[str]:
        return set(self._by_dependency.get(dependency, set()))
