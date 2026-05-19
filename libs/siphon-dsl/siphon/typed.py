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

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class FieldSpec(BaseModel):
    """Specification for extracting a single field."""

    model_config = ConfigDict(extra="forbid")

    path: str
    """JSONPath expression (e.g., '$.data.items[*]')"""

    where: dict[str, Any] | None = None
    """Filter conditions - item must match all key-value pairs"""

    select: dict[str, str] | None = None
    """Field projection/renaming: {new_name: old_path}

    A path string may contain `||` to coalesce — paths are tried
    left-to-right and the first one resolving to a non-None value wins.
    Example: `{"price": "sale_price || list_price"}`.
    """

    collect: bool = False
    """If True, return all matches. If False, return first match only."""

    reduce: str | dict[str, Any] | None = None
    """
    Aggregate all matched values to a single result.
    Accepts a plain operator name or a dict with 'op' and options.

    String operators: min_time, max_time, min_date, max_date, min_datetime,
    max_datetime, min_int, max_int, sum, count, first, last, concat, distinct

    min_time/max_time accept ISO 8601 datetime strings or plain HH:MM /
    HH:MM:SS strings; date and timezone are ignored.

    Dict form (for operators with options):
        {"op": "concat", "sep": " | "}

    Mutually exclusive with collect. Returns None for empty arrays,
    except count which returns 0.
    """


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


# Chaining query interface (v0.6.0+)


class SortSpec(BaseModel):
    """Sort specification for a chain level."""

    model_config = ConfigDict(extra="forbid")

    field: str
    """Field name to sort by (dot-notation for nested fields)"""

    order: Literal["asc", "desc"] = "asc"
    """Sort order: ascending or descending"""


class ChainSpec(BaseModel):
    """Specification for hierarchical data extraction with chaining."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    id: str | None = None
    """Optional stage identifier for pipeline $stages references (ignored by query)"""

    from_: str = Field(alias="from")
    """JSONPath or relative path to the array to iterate: e.g., '$.items[*]' or 'rates[*]'"""

    where: dict[str, Any] | None = None
    """MongoDB-style filter conditions for matching items at this level"""

    select: dict[str, str] | None = None
    """Field projection/renaming: {output_name: source_path}

    A path string may contain `||` to coalesce — first non-None segment wins.
    """

    sort: list[SortSpec] | None = None
    """Sort specifications for items at this level (before then recursion)"""

    limit: int | None = None
    """Maximum number of items to return from this level"""

    offset: int | None = None
    """Number of items to skip at this level"""

    collect: bool = False
    """If True, return all matched items as a list. If False, return first item only."""

    then: ChainSpec | None = None
    """Nested chain specification to recurse into for each matched item"""


# Rebuild self-referential model
ChainSpec.model_rebuild()


def query_typed(chain_spec: ChainSpec, data: dict) -> list | dict | None:
    """
    Execute a typed chain query spec against data.

    Args:
        chain_spec: ChainSpec model instance
        data: the JSON/dict data to query

    Returns:
        Extracted data matching the spec (list, dict, or None)

    Example:
        >>> spec = ChainSpec(
        ...     from_="$.items[*]",
        ...     where={"status": "active"},
        ...     select={"id": "item_id"},
        ...     collect=True
        ... )
        >>> result = query_typed(spec, data)
    """
    from siphon._chain import query

    return query(chain_spec.model_dump(by_alias=True, exclude_none=True), data)


class PipelineSpec(BaseModel):
    """Specification for a multi-stage pipeline."""

    model_config = ConfigDict(extra="forbid")

    stages: list[ChainSpec]
    """Ordered list of stages. Each stage's `from` resolves against root data."""


def pipeline_typed(spec: PipelineSpec, data: Any) -> list | dict | None:
    """
    Execute a typed pipeline spec against data.

    Args:
        spec: PipelineSpec model instance
        data: the root JSON/dict data all stages resolve against

    Returns:
        The last stage's output (list, dict, or None)
    """
    from siphon._chain import pipeline

    return pipeline(
        [s.model_dump(by_alias=True, exclude_none=True) for s in spec.stages],
        data,
    )
