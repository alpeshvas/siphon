"""
Typed interface for Siphon using Pydantic models.

Install with: pip install siphon-dsl[typed]

Usage:
    from siphon.typed import process_spec, ExtractSpec, FieldSpec

    spec = ExtractSpec(
        extract={
            "id": "$.data.id",
            "active_items": FieldSpec(
                path="$.data.items[*]",
                where={"status": "active"},
                select={"item_id": "id", "name": "name"},
                collect=True,
            ),
        }
    )
    result = process_spec(spec, data)
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class FieldSpec(BaseModel):
    """Specification for extracting a single field."""

    model_config = ConfigDict(extra="forbid")

    path: str
    """JSONPath expression (e.g., '$.data.items[*]')"""

    where: dict[str, Any] | None = None
    """Filter conditions - item must match all key-value pairs"""

    select: dict[str, str] | None = None
    """Field projection/renaming: {new_name: old_path}"""

    collect: bool = False
    """If True, return all matches. If False, return first match only."""


class RequestSpec(BaseModel):
    """Specification for API request (used with fetch_and_process)."""

    model_config = ConfigDict(extra="forbid")

    path: str
    """API endpoint path to append to base_url"""


class ExtractSpec(BaseModel):
    """Root specification for data extraction."""

    model_config = ConfigDict(extra="forbid")

    extract: dict[str, str | FieldSpec]
    """
    Mapping of output field names to extraction specs.
    Values can be:
    - str: Simple JSONPath (e.g., "$.data.id")
    - FieldSpec: Complex extraction with filtering/projection
    """

    request: RequestSpec | None = None
    """Optional request config for fetch_and_process"""


def process_spec(spec: ExtractSpec, data: dict) -> dict:
    """Process a typed extraction spec against data."""
    from siphon import process

    return process(spec.model_dump(exclude_none=True), data)


def fetch_and_process_spec(spec: ExtractSpec, base_url: str) -> dict:
    """Fetch from API and process a typed extraction spec."""
    from siphon import fetch_and_process

    return fetch_and_process(spec.model_dump(exclude_none=True), base_url)
