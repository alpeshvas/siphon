# Siphon

A minimal DSL for extracting data from JSON APIs.

Like a siphon draws liquid from a container, Siphon draws the data you need from nested JSON structures—just define the paths, and let it flow.

## Install
```bash
pip install siphon-dsl
```

Or with uv:
```bash
uv add siphon-dsl
```

## Quick Start
```python
from siphon import process

data = {
    "data": {
        "id": "prod_123",
        "items": [
            {"id": 1, "status": "active", "name": "Widget"},
            {"id": 2, "status": "inactive", "name": "Gadget"},
            {"id": 3, "status": "active", "name": "Thing"},
        ],
    }
}

spec = {
    "extract": {
        "id": "$.data.id",
        "all_active": {
            "path": "$.data.items[*]",
            "where": {"status": "active"},
            "select": {"item_id": "id", "item_name": "name"},
            "collect": True,
        },
    }
}

result = process(spec, data)
```

Output:
```json
{
  "id": "prod_123",
  "all_active": [
    {"item_id": 1, "item_name": "Widget"},
    {"item_id": 3, "item_name": "Thing"}
  ]
}
```

## Features

| Feature | Syntax | Description |
|---------|--------|-------------|
| **Simple paths** | `$.data.id` | Extract nested values |
| **Array iteration** | `$.items[*].name` | Traverse arrays |
| **Filtering** | `where: {status: "active"}` | Filter by field values |
| **Ancestor filtering** | `where: {parentId: 123}` | Filter by parent-level properties |
| **Projection** | `select: {new: "old"}` | Rename and reshape fields |
| **Collect** | `collect: true` | Return all matches (default: first only) |
| **Reduce** | `reduce: "min_time"` | Aggregate array values to a single result |

## Spec Format

### Simple extraction
```yaml
extract:
  id: "$.data.id"
  name: "$.data.name"
```

### Extended extraction
```yaml
extract:
  active_items:
    path: "$.data.items[*]"
    where: {status: "active"}
    select: {item_id: "id", item_name: "name"}
    collect: true
```

### Reduce (aggregation)
```yaml
extract:
  earliest_slot:
    path: "$.items[*].from_datetime"
    reduce: min_time          # earliest time-of-day across all items

  latest_slot:
    path: "$.items[*].to_datetime"
    reduce: max_time          # latest time-of-day across all items

  total_price:
    path: "$.items[*].price"
    reduce: sum

  unique_categories:
    path: "$.items[*].category"
    reduce: distinct
```

Available operators:

| Operator | Description |
|---|---|
| `min_time` / `max_time` | Earliest/latest time-of-day (ignores date + timezone) |
| `min_date` / `max_date` | Earliest/latest calendar date (ignores time) |
| `min_datetime` / `max_datetime` | Earliest/latest full datetime (timezone-normalised) |
| `min_int` / `max_int` | Minimum/maximum numeric value |
| `sum` | Sum of numeric values |
| `count` | Count of non-null values (returns `0` for empty) |
| `first` / `last` | First or last value in traversal order |
| `concat` | Join values as a string (default separator `", "`) |
| `distinct` | Deduplicated list, preserving first-seen order |

For `concat` with a custom separator use the dict form:
```python
"reduce": {"op": "concat", "sep": " | "}
```

## Fetch from API
```python
from siphon import fetch_and_process

spec = {
    "request": {"path": "/products"},
    "extract": {
        "id": "$.data.id",
        "names": {"path": "$.data.items[*].name", "collect": True},
    },
}

result = fetch_and_process(spec, "https://api.example.com")
```

Requires `requests`:
```bash
pip install siphon-dsl[http]
```

## Typed Specs (Pydantic)
```python
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
```

Requires `pydantic`:
```bash
pip install siphon-dsl[typed]
```

## Why Siphon?

- **Minimal** — ~100 lines of code, no dependencies
- **Declarative** — specs are data, not code
- **Composable** — combine paths, filters, and projections

## Spec History

See [specs/](specs/) for version history and full documentation. Latest: [v0.8](../../specs/v0.8.md) — adds `reduce` aggregation operators.

## License

MIT
