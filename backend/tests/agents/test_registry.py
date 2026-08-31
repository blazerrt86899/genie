"""Agent registry integrity (CLAUDE.md §12)."""

from __future__ import annotations

import inspect

from app.agents.registry import AGENT_REGISTRY, KNOWN_AGENTS, AgentSpec, agent_menu


def test_registry_entries_are_well_formed() -> None:
    assert AGENT_REGISTRY, "registry must not be empty"
    for key, spec in AGENT_REGISTRY.items():
        assert isinstance(spec, AgentSpec)
        assert spec.name == key
        assert spec.description.strip()
        assert inspect.iscoroutinefunction(spec.runner)


def test_known_agents_matches_registry() -> None:
    assert KNOWN_AGENTS == frozenset(AGENT_REGISTRY)


def test_agent_menu_lists_every_agent() -> None:
    menu = agent_menu()
    for name in AGENT_REGISTRY:
        assert name in menu
