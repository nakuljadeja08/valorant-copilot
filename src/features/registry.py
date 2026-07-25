"""Features the runner executes, in order. Populated in Phase 2b.

An empty registry is a valid, idempotent, zero-row run — it lets the runner
and its plumbing be exercised before any concrete feature exists.
"""

from __future__ import annotations

from src.features.base import Feature

REGISTRY: list[Feature] = []
