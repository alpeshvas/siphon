"""
Siphon - Minimal DSL for API Data Extraction

Supports (legacy flat API):
- Simple JSONPath extraction: "$.data.id"
- Array iteration with [*]
- Filtering with `where` (returns first match by default)
- Ancestor filtering: `where` can match properties from any parent level
- Field projection/renaming with `select`
- Collect all matches with `collect: true`
- Aggregation with `reduce`: min_time, max_time, min_date, max_date,
  min_datetime, max_datetime, min_int, max_int, sum, count, first, last,
  concat, distinct

Supports (chaining API v0.6.0+):
- Hierarchical multi-level extraction with "then" chaining
- MongoDB-style filter operators: $eq, $ne, $gt, $gte, $lt, $lte, $in, $nin, $exists, $regex
- Logical operators: $and, $or, $not, $nor
- Sort, limit, offset at each level
- Field carry-forward from parent levels

Supports (pipeline API v0.7.0+):
- GitHub Actions-style multi-stage pipeline with named stages
- Cross-reference sibling arrays via $stages.<id>.<field> in where clauses
- Each stage's `from` resolves against root data
"""

from dataclasses import dataclass
from typing import Any

__version__ = "0.10.0"


@dataclass
class FieldSpec:
    path: str
    where: dict | None = None
    select: dict | None = None
    collect: bool = False
    reduce: str | dict | None = None


def parse_field(value) -> FieldSpec:
    if isinstance(value, str):
        return FieldSpec(path=value)
    return FieldSpec(
        path=value["path"],
        where=value.get("where"),
        select=value.get("select"),
        collect=value.get("collect", False),
        reduce=value.get("reduce"),
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
    """Project/rename fields from item.

    A select value is a path string. If the string contains "||", it is
    treated as a coalesce: paths are tried left-to-right and the first
    non-None value wins. Whitespace around each segment is ignored;
    empty segments are skipped.
    """
    result = {}
    for new_name, source in select.items():
        if "||" in source:
            value = None
            for path in source.split("||"):
                path = path.strip()
                if not path:
                    continue
                value = get_by_path(item, path)
                if value is not None:
                    break
            result[new_name] = value
        else:
            result[new_name] = get_by_path(item, source)
    return result


def _time_key(dt_str: str) -> tuple:
    """Return (H, M, S) from an ISO 8601 datetime or plain HH:MM / HH:MM:SS string."""
    if not dt_str:
        return 0, 0, 0
    if "T" not in dt_str:
        parts = dt_str.split(":")
        h = int(parts[0]) if len(parts) > 0 else 0
        m = int(parts[1]) if len(parts) > 1 else 0
        s = int(parts[2]) if len(parts) > 2 else 0
        return h, m, s
    time_part = dt_str.split("T")[1]
    # Strip timezone: +HH:MM, -HH:MM, or Z
    for sep in ("+", "-", "Z"):
        idx = time_part.find(sep)
        if idx != -1:
            time_part = time_part[:idx]
            break
    parts = time_part.split(":")
    return tuple(int(p) for p in parts[:3])


def _date_key(dt_str: str) -> tuple:
    """Return (Y, M, D) from an ISO 8601 datetime or date string, ignoring time."""
    if not dt_str:
        return (0, 0, 0)
    date_part = dt_str.split("T")[0]
    parts = date_part.split("-")
    return tuple(int(p) for p in parts[:3])


def _datetime_key(dt_str: str):
    """Return a timezone-aware datetime for full ISO 8601 comparison across timezones."""
    from datetime import datetime

    return datetime.fromisoformat(dt_str)


class Extractor:
    def extract(self, spec: FieldSpec, data: dict) -> Any:
        # Simple path, no array iteration
        if "[*]" not in spec.path:
            return get_by_path(data, spec.path.lstrip("$."))

        # Reduce: aggregate all values with a named operator
        if spec.reduce:
            op = spec.reduce if isinstance(spec.reduce, str) else spec.reduce["op"]
            values = [v for _, v in extract_all(data, spec.path) if v is not None]

            # count is the only op that has a meaningful result for empty arrays
            if op == "count":
                return len(values)

            if not values:
                return None

            if op == "min_time":
                return min(values, key=_time_key)
            if op == "max_time":
                return max(values, key=_time_key)
            if op == "min_date":
                return min(values, key=_date_key)
            if op == "max_date":
                return max(values, key=_date_key)
            if op == "min_datetime":
                return min(values, key=_datetime_key)
            if op == "max_datetime":
                return max(values, key=_datetime_key)
            if op == "min_int":
                return min(values)
            if op == "max_int":
                return max(values)
            if op == "sum":
                return sum(values)
            if op == "first":
                return values[0]
            if op == "last":
                return values[-1]
            if op == "concat":
                sep = spec.reduce.get("sep", ", ") if isinstance(spec.reduce, dict) else ", "
                return sep.join(str(v) for v in values)
            if op == "distinct":
                seen: set = set()
                result = []
                for v in values:
                    if v not in seen:
                        seen.add(v)
                        result.append(v)
                return result

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


# Import the chaining query API (v0.6.0+) and pipeline API (v0.7.0+)
from siphon._chain import pipeline as pipeline  # noqa: E402
from siphon._chain import query as query  # noqa: E402
