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
| **List indexing** | `items[0].id` / `names[-1]` | Pick a specific list position (supports negative) |
| **Root capture** | `from: "$"` | Iterate root once — lets a pipeline stage project top-level scalars |
| **Pipeline `$stages` in `select`** | `select: {x: "$stages.act.y"}` | Carry a prior stage's value as a literal into the current stage's projection |
| **Filtering** | `where: {status: "active"}` | Filter by field values |
| **Ancestor filtering** | `where: {parentId: 123}` | Filter by parent-level properties |
| **Projection** | `select: {new: "old"}` | Rename and reshape fields |
| **Coalesce** | `select: {price: "sale \|\| list"}` | First non-null path wins (SQL-style `\|\|`) |
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

### List indexing (`[N]`)
Any path segment can drill into a list at a specific position with `[N]`. Negative indices count from the end; out-of-bounds or non-list values resolve to `None`. Indexing composes with `||`:

```yaml
extract:
  rows:
    path: "$.items[*]"
    select:
      # Try the first tier, fall back to a flat price field
      amount: "tieredPrices[0].amount || price.amount"
      last_name: "names[-1]"
    collect: true
```

`[*]` and `[N]` are distinct — `[*]` iterates, `[N]` picks one element.

### Coalesce in `select`
A `select` path string may contain `||` to declare a fallback chain. Segments are tried left-to-right; the first one resolving to a non-`None` value wins; otherwise the field is `None`. Any number of segments is supported.

```yaml
extract:
  products:
    path: "$.products[*]"
    select:
      id: id
      price: "sale_price || list_price"   # fall back to list_price if sale_price is null
      label: "customLabel || title || ticketCategory"
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
| `min_time` / `max_time` | Earliest/latest time-of-day — accepts ISO 8601 datetime or plain `HH:MM` / `HH:MM:SS` (ignores date + timezone) |
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

See [specs/](specs/) for version history and full documentation. Latest: [v0.12](../../specs/v0.12.md) — pipeline stages can capture root scalars via `from: "$"` and reference prior stages from `select` via `$stages.<id>.<field>`.

## License

MIT
