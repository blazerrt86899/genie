"""Clerk webhook tests — placeholders (CLAUDE.md §16).

- invalid Svix signature -> 400, payload never processed
- user.created / user.updated / user.deleted each handled
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="webhook handler not implemented yet (Phase 1)")


def test_invalid_signature_rejected() -> None: ...
