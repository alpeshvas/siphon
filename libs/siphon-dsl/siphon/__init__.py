"""
Siphon - Minimal DSL for API Data Extraction

Supports:
- Simple JSONPath extraction: "$.data.id"
- Array iteration with [*]
- Filtering with `where` (returns first match by default)
- Ancestor filtering: `where` can match properties from any parent level
- Field projection/renaming with `select`
- Collect all matches with `collect: true`
"""

from dataclasses import dataclass
from typing import Any

__version__ = "0.5.0"


@dataclass
class FieldSpec:
    path: str
    where: dict | None = None
    select: dict | None = None
    collect: bool = False


def parse_field(value) -> FieldSpec:
    if isinstance(value, str):
        return FieldSpec(path=value)
    return FieldSpec(
        path=value["path"],
        where=value.get("where"),
        select=value.get("select"),
        collect=value.get("collect", False),
    )


def get_by_path(obj, path: str):
    """Traverse dot notation path."""
    for part in path.split("."):
        if obj is None:
            return None
        obj = obj.get(part) if isinstance(obj, dict) else None
    return obj


def extract_all(data, path: str, context: dict | None = None) -> list:
    """Extract all values from path, handling multiple [*] recursively.

    Returns list of (context, value) tuples where context includes
    all ancestor array item properties for where filtering.
    """
    context = context or {}

    if path.startswith("$."):
        path = path[2:]

    if "[*]" not in path:
        value = get_by_path(data, path) if path else data
        # Merge final item into context if it's a dict
        final_context = {**context, **value} if isinstance(value, dict) else context
        return [(final_context, value)]

    before, after = path.split("[*]", 1)
    before = before.rstrip(".")
    after = after.lstrip(".")

    array = get_by_path(data, before) if before else data
    if not array or not isinstance(array, list):
        return []

    results = []
    for item in array:
        # Merge current array item into context for descendant filtering
        merged = {**context, **item} if isinstance(item, dict) else context
        for sub_context, value in extract_all(item, after, merged):
            results.append((sub_context, value))
    return results


def matches(item: dict, where: dict) -> bool:
    """Check if item matches all where conditions."""
    return all(get_by_path(item, k) == v for k, v in where.items())


def project(item: dict, select: dict) -> dict:
    """Project/rename fields from item."""
    return {new_name: get_by_path(item, old_path) for new_name, old_path in select.items()}


class Extractor:
    def extract(self, spec: FieldSpec, data: dict) -> Any:
        # Simple path, no array iteration
        if "[*]" not in spec.path:
            return get_by_path(data, spec.path.lstrip("$."))

        results = []
        for item, value in extract_all(data, spec.path):
            if spec.where and not matches(item, spec.where):
                continue

            if spec.select and isinstance(value, dict):
                value = project(value, spec.select)

            if not spec.collect:
                return value

            results.append(value)

        return results if spec.collect else None


def process(spec: dict, data: dict) -> dict:
    """Process extraction spec against data."""
    extractor = Extractor()
    return {
        name: extractor.extract(parse_field(expr), data) for name, expr in spec["extract"].items()
    }


def fetch_and_process(spec: dict, base_url: str) -> dict:
    """Fetch from API and process extraction spec."""
    import requests

    url = base_url + spec["request"]["path"]
    data = requests.get(url).json()
    return process(spec, data)
