"""Supervisor routing tests — placeholders (CLAUDE.md §16).

Key assertions to implement in Phase 1:
- RouteDecision output is valid for a range of queries
- Supervisor NEVER routes to the same agent twice in one run
- Token budget enforced: routing stops at MAX_TOKENS_PER_RUN
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="supervisor not implemented yet (Phase 1)")


def test_route_decision_no_duplicate_agents() -> None: ...
