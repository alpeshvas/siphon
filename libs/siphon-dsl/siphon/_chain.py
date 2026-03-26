"""
Siphon chaining query engine - implements hierarchical data extraction with
MongoDB-style filters, field projection, sorting, and carry-forward semantics.

Private module (leading underscore). Users import query() from siphon package.
"""

import re
from typing import Any

from siphon import get_by_path, project


def eval_condition(value: Any, condition: Any) -> bool:
    """
    Evaluate a single-field condition.

    If condition is a bare value (not a dict), it's shorthand for $eq.
    If condition is a dict, check all operators (each operator must pass).

    Returns False for all comparisons when value is None (no TypeError).
    """
    if not isinstance(condition, dict):
        # Shorthand: {"field": "value"} == {"field": {"$eq": "value"}}
        return value == condition

    for op, operand in condition.items():
        result = False

        if op == "$eq":
            result = value == operand

        elif op == "$ne":
            result = value != operand

        elif op == "$gt":
            result = value is not None and value > operand

        elif op == "$gte":
            result = value is not None and value >= operand

        elif op == "$lt":
            result = value is not None and value < operand

        elif op == "$lte":
            result = value is not None and value <= operand

        elif op == "$in":
            result = value in operand

        elif op == "$nin":
            result = value not in operand

        elif op == "$exists":
            result = (value is not None) == operand

        elif op == "$regex":
            result = bool(re.search(operand, str(value))) if value is not None else False

        else:
            raise ValueError(f"Unknown operator: {op}")

        if not result:
            return False

    return True


def eval_filter(where: dict[str, Any] | None, item: dict) -> bool:
    """
    Evaluate a full filter dict against an item.

    Handles logical operators ($and, $or, $not, $nor) and field conditions.
    Each key in where is either a field path (e.g. "price.amount") or a logical operator.
    """
    if where is None:
        return True

    if not where:  # empty dict
        return True

    for key, condition in where.items():
        if key == "$and":
            # All conditions must pass
            if not all(eval_filter(sub, item) for sub in condition):
                return False

        elif key == "$or":
            # At least one condition must pass
            if not any(eval_filter(sub, item) for sub in condition):
                return False

        elif key == "$not":
            # Negate the condition
            if eval_filter(condition, item):
                return False

        elif key == "$nor":
            # None of the conditions must pass
            if any(eval_filter(sub, item) for sub in condition):
                return False

        else:
            # Regular field condition
            value = get_by_path(item, key)
            if not eval_condition(value, condition):
                return False

    return True


def sort_items(
    items: list[dict],
    sort_specs: list[dict[str, Any]] | None
) -> list[dict]:
    """
    Sort items by multiple sort specs (stable sort).

    Each sort_spec has: {"field": "...", "order": "asc" or "desc"}
    None values always sort last (both asc and desc).
    """
    if not sort_specs:
        return items

    result = items
    # Apply sorts in reverse order (rightmost has lowest priority, then the rest)
    for sort_spec in reversed(sort_specs):
        field = sort_spec.get("field", "")
        order = sort_spec.get("order", "asc")
        is_desc = order == "desc"

        # Sort with None values always going last
        # First, separate None and non-None items
        nones = [x for x in result if get_by_path(x, field) is None]
        non_nones = [x for x in result if get_by_path(x, field) is not None]

        # Sort non-None items
        non_nones = sorted(
            non_nones,
            key=lambda x: get_by_path(x, field),
            reverse=is_desc
        )

        # Combine: sorted non-Nones + Nones at the end
        result = non_nones + nones

    return result


def resolve_from(from_path: str | None, data: Any) -> list:
    """
    Resolve the "from" path to an array.

    If from_path starts with "$.", it's an absolute path from root.
    Otherwise, it's a relative path on data.

    Returns a list (empty if path doesn't resolve to a list).
    """
    if not from_path:
        return data if isinstance(data, list) else []

    # Strip leading "$." if present (absolute path)
    if from_path.startswith("$."):
        from_path = from_path[2:]

    # Split on first [*] to extract the array path
    before, _, _ = from_path.partition("[*]")
    before = before.rstrip(".")

    # Resolve the path
    array = get_by_path(data, before) if before else data

    return array if isinstance(array, list) else []


def execute_chain(
    spec: dict[str, Any],
    data: Any,
    carry_context: dict[str, Any] | None = None
) -> list | dict | None:
    """
    Execute a chain spec recursively against data.

    Returns:
    - At terminal level: list if collect=true, first item if collect=false, None if no match
    - At intermediate level: always a list (caller flattens)
    """
    if carry_context is None:
        carry_context = {}

    # Step 1: Get array to iterate
    items = resolve_from(spec.get("from"), data)

    # Step 2: Filter items
    where = spec.get("where")
    matched = [item for item in items if eval_filter(where, item)]

    # Step 3: Sort items
    sort_specs = spec.get("sort")
    if sort_specs:
        matched = sort_items(matched, sort_specs)

    # Step 4: Apply offset
    offset = spec.get("offset")
    if offset:
        matched = matched[offset:]

    # Step 5: Apply limit
    limit = spec.get("limit")
    if limit:
        matched = matched[:limit]

    # Step 6: Terminal or intermediate?
    if "then" not in spec:
        # TERMINAL LEVEL
        select = spec.get("select")
        collect = spec.get("collect", False)

        results = []
        for item in matched:
            # Project this level's fields
            projected = project(item, select) if select else item
            # Merge with carry-forward context (child wins on collision)
            merged = {**carry_context, **projected}
            results.append(merged)

        # Return based on collect flag
        if collect:
            return results
        else:
            return results[0] if results else None

    else:
        # INTERMEDIATE LEVEL
        select = spec.get("select")
        results = []

        for item in matched:
            # Project this level's fields for carry-forward
            contribution = project(item, select) if select else {}
            # Build carry context
            child_carry = {**carry_context, **contribution}
            # Recurse (then always operates on original item)
            child_results = execute_chain(spec["then"], item, child_carry)

            # Flatten results
            if isinstance(child_results, list):
                results.extend(child_results)
            elif child_results is not None:
                results.append(child_results)

        return results


def decompose_multi_star(spec: dict[str, Any]) -> dict[str, Any]:
    """
    Decompose a spec with multiple [*] in from path into nested chain specs.

    Example: {"from": "$.a[*].b[*].c", "where": {...}, "select": {...}}
    becomes:
    {
        "from": "$.a[*]",
        "then": {
            "from": "b[*].c",
            "where": {...},
            "select": {...}
        }
    }

    The where/select/sort/limit/offset/collect from the original spec attach to the innermost level.
    If an explicit "then" is present, it's appended to the decomposed innermost level.
    """
    from_path = spec.get("from", "")

    # Base case: no [*] or only one [*]
    if from_path.count("[*]") <= 1:
        return spec

    # Find the first [*]
    idx = from_path.index("[*]")
    before = from_path[:idx]
    after = from_path[idx + 3:]  # Skip "[*]"

    # The outer "from" is everything up to and including the first [*]
    outer_from = before + "[*]"

    # The inner spec gets the rest of the path
    # If after starts with ".", make it relative (remove the dot)
    inner_from = after.lstrip(".") if after else ""

    inner_spec = {
        "from": inner_from,
        **{k: v for k, v in spec.items() if k not in ("from", "then")}
    }

    # If the inner spec's from still has [*], recurse
    if "[*]" in inner_spec.get("from", ""):
        inner_spec = decompose_multi_star(inner_spec)

    # If there's an explicit "then" in the original spec, append it to the innermost level
    if "then" in spec:
        # Find the innermost "then" and attach the explicit then to it
        current = inner_spec
        while "then" in current:
            current = current["then"]
        current["then"] = spec["then"]

    return {
        "from": outer_from,
        "then": inner_spec
    }


def query(chain_spec: dict[str, Any], data: Any) -> list | dict | None:
    """
    Execute a chain query spec against data.

    Args:
        chain_spec: dict with keys: from, where, select, sort, limit, offset, collect, then
                   (from can have multiple [*] which will be auto-decomposed)
        data: the JSON/dict data to query

    Returns:
        Extracted data matching the spec (list, dict, or None)
    """
    # Decompose multi-star paths into nested specs
    chain_spec = decompose_multi_star(chain_spec)
    return execute_chain(chain_spec, data)
