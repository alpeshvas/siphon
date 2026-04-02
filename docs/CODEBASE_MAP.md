# Siphon Codebase Map

## Project Overview

Siphon is a minimal DSL for extracting data from JSON APIs. It provides a declarative, spec-based approach to traversing nested JSON structures, filtering items, projecting/renaming fields, and joining sibling arrays. The core library has zero runtime dependencies and is published to PyPI as `siphon-dsl`.

**Current version:** 0.7.0
**License:** MIT
**Python:** >=3.10
**Repository:** https://github.com/alpeshvas/siphon

---

## Directory Structure

```
siphon/
├── .github/
│   └── workflows/
│       ├── test.yml              # CI: lint + test on Python 3.10/3.11/3.12
│       └── workflow.yml          # CD: build and publish to PyPI on release
├── libs/
│   └── siphon-dsl/              # Publishable package
│       ├── siphon/
│       │   ├── __init__.py      # Core extraction engine (~145 lines)
│       │   ├── _chain.py        # Chaining query engine + pipeline (~390 lines)
│       │   └── typed.py         # Pydantic models for typed specs (~190 lines)
│       ├── pyproject.toml       # Package metadata, build config (hatchling)
│       └── README.md            # Package README (symlinked to root)
├── specs/
│   └── v0.5.md                  # Spec document for legacy extract API
├── tests/
│   ├── test_siphon.py           # Legacy process() API tests
│   ├── test_typed.py            # Pydantic ExtractSpec/FieldSpec model tests
│   ├── test_chain.py            # Chaining query() engine tests
│   ├── test_chain_typed.py      # Typed ChainSpec/query_typed tests
│   ├── test_filter_ops.py       # MongoDB-style filter operator unit tests
│   └── test_pipeline.py         # Multi-stage pipeline() tests
├── pyproject.toml               # Workspace root (uv workspace config, dev deps)
├── CLAUDE.md                    # AI assistant project instructions
├── README.md -> libs/siphon-dsl/README.md  # Symlink to package README
├── .pre-commit-config.yaml      # Pre-commit hooks
├── .python-version              # Python version pin
└── uv.lock                      # Lockfile
```

---

## Architecture Overview

Siphon provides three progressively powerful APIs, each building on the one below:

```
┌─────────────────────────────────────────────┐
│  pipeline()  (v0.7.0+)                      │
│  Multi-stage, GitHub Actions-style           │
│  Cross-references via $stages.<id>.<field>   │
├─────────────────────────────────────────────┤
│  query()  (v0.6.0+)                         │
│  Hierarchical chaining with "then"           │
│  MongoDB-style filters, sort, limit, offset  │
├─────────────────────────────────────────────┤
│  process()  (v0.4+)                         │
│  Legacy flat extract API                     │
│  Simple path, where, select, collect         │
└─────────────────────────────────────────────┘
```

### Data Flow

1. **Input:** JSON data (dict) + a spec (dict or Pydantic model)
2. **Path resolution:** Dot-notation paths are traversed; `[*]` triggers array iteration
3. **Filtering:** Items matched against `where` conditions (equality or MongoDB-style operators)
4. **Sorting/pagination:** Optional sort, offset, and limit applied
5. **Projection:** `select` renames and reshapes output fields
6. **Output:** Extracted dict, list, scalar, or None

---

## Key Modules

### `siphon/__init__.py` -- Core Extraction Engine

The original extraction engine supporting the flat `process()` API.

| Component | Purpose |
|-----------|---------|
| `FieldSpec` (dataclass) | Holds `path`, `where`, `select`, `collect` for a single extraction |
| `parse_field(value)` | Converts a string or dict to a `FieldSpec` |
| `get_by_path(obj, path)` | Traverses dot-notation paths (e.g., `"pricing.amount"`) |
| `extract_all(data, path, context)` | Recursively iterates `[*]` arrays, accumulating ancestor context |
| `matches(item, where)` | Simple equality-based filter (AND logic) |
| `project(item, select)` | Renames/reshapes fields via `{new_name: old_path}` mapping |
| `Extractor.extract(spec, data)` | Main extraction logic for a single field |
| `process(spec, data)` | Public API: extracts all fields defined in `spec["extract"]` |
| `fetch_and_process(spec, base_url)` | Fetches JSON from an API, then calls `process()` (requires `requests`) |

Re-exports from `_chain`: `query`, `pipeline`.

### `siphon/_chain.py` -- Chaining Query Engine

The advanced extraction engine supporting hierarchical chaining and pipelines.

| Component | Purpose |
|-----------|---------|
| `eval_condition(value, condition)` | Evaluates a single value against an operator (`$eq`, `$gt`, `$in`, `$regex`, etc.) |
| `eval_filter(where, item)` | Full filter evaluation with logical operators (`$and`, `$or`, `$not`, `$nor`) |
| `sort_items(items, sort_specs)` | Stable multi-key sort; `None` values always sort last |
| `resolve_from(from_path, data)` | Resolves a `from` path to an array (absolute `$.` or relative) |
| `execute_chain(spec, data, carry_context, root_data)` | Recursive chain executor: filter -> sort -> offset -> limit -> project/recurse |
| `decompose_multi_star(spec)` | Auto-decomposes `$.a[*].b[*].c` into nested chain specs |
| `query(chain_spec, data)` | Public API: executes a chain query spec |
| `resolve_ref(value, ctx)` | Resolves a `$stages.<id>.<field>` reference |
| `resolve_refs(obj, ctx)` | Recursively resolves `$stages` references in where dicts |
| `pipeline(stages, data)` | Public API: executes a multi-stage pipeline with cross-references |

**Carry-forward semantics:** When using `then` chaining, intermediate-level `select` fields are merged into child results. Child values win on key collision.

### `siphon/typed.py` -- Pydantic Models

Typed wrappers around the core APIs for validation, serialization, and LLM tool-call schemas.

| Model | Purpose |
|-------|---------|
| `FieldSpec` | Pydantic model for legacy extraction field (path, where, select, collect) |
| `RequestSpec` | API request config (path) |
| `ExtractSpec` | Root spec for `process()` with `extract` and optional `request` |
| `SortSpec` | Sort field + order (`asc`/`desc`) |
| `ChainSpec` | Self-referential model for chaining queries (from, where, select, sort, limit, offset, collect, then) |
| `PipelineSpec` | List of `ChainSpec` stages |

Functions: `process_spec()`, `fetch_and_process_spec()`, `query_typed()`, `pipeline_typed()`.

The `ChainSpec` model uses `from_` as the Python field name with `"from"` as the alias (since `from` is a Python keyword). It includes an optional `id` field for pipeline stage references.

---

## Spec Format and DSL Syntax

### Legacy Extract API (`process`)

```python
spec = {
    "extract": {
        "field_name": "$.path.to.value",          # Simple path
        "another_field": {                          # Extended extraction
            "path": "$.data.items[*]",
            "where": {"status": "active"},          # Filter (AND logic)
            "select": {"new_name": "old_path"},     # Projection
            "collect": True,                        # All matches (default: first only)
        },
    }
}
result = process(spec, data)
```

**Path syntax:**
- `$.data.id` -- nested value access (`$` prefix is optional)
- `$.items[*].name` -- array iteration (returns first match without `collect`)
- `$.a[*].b[*].c` -- multi-level nested array traversal

**Ancestor filtering:** `where` conditions can match properties from any parent array level, not just the innermost item.

### Chaining Query API (`query`)

```python
spec = {
    "from": "$.items[*]",
    "where": {"price": {"$gt": 50}},               # MongoDB-style operators
    "select": {"id": "item_id", "cost": "price"},
    "sort": [{"field": "price", "order": "asc"}],
    "limit": 10,
    "offset": 5,
    "collect": True,
    "then": {                                        # Nested level
        "from": "variants[*]",
        "select": {"sku": "sku"},
        "collect": True,
    },
}
result = query(spec, data)
```

**Filter operators:**
| Operator | Description |
|----------|-------------|
| `$eq` | Equal (default for bare values) |
| `$ne` | Not equal |
| `$gt`, `$gte` | Greater than / greater or equal |
| `$lt`, `$lte` | Less than / less or equal |
| `$in`, `$nin` | In / not in a list |
| `$exists` | Field exists (not None) |
| `$regex` | Regex match against string |

**Logical operators:** `$and`, `$or`, `$not`, `$nor`

### Pipeline API (`pipeline`)

```python
stages = [
    {
        "id": "rate",
        "from": "$.rates[*]",
        "where": {"id": 1},
        "select": {"startTimeIds": "startTimeIds"},
    },
    {
        "from": "$.startTimes[*]",
        "where": {"id": {"$in": "$stages.rate.startTimeIds"}},
        "collect": True,
        "select": {"hour": "hour", "minute": "minute"},
    },
]
result = pipeline(stages, data)
```

Key behaviors:
- Each stage's `from` resolves against the **root data** (not previous stage output)
- Stages reference prior outputs via `$stages.<id>.<field>` in where clauses
- When a referenced stage returned a list, the field is gathered from all items
- When a referenced stage returned a dict, the field is extracted directly
- The return value is the **last stage's output**

---

## Testing Structure

All tests live in `tests/` and use pytest. The test suite is organized by API layer and feature:

| File | Scope | Test count (approx) |
|------|-------|---------------------|
| `test_siphon.py` | Legacy `process()` API: simple paths, where, select, collect, nested arrays, ancestor filtering, real-world Bokun data | ~15 tests |
| `test_typed.py` | Pydantic models (`FieldSpec`, `ExtractSpec`, `RequestSpec`) and `process_spec()` | ~15 tests |
| `test_chain.py` | Chaining `query()`: single-level, then chaining, sort, limit/offset, carry-forward | ~25 tests |
| `test_chain_typed.py` | Typed `ChainSpec`, `SortSpec`, `query_typed()`, `PipelineSpec`, serialization round-trips | ~20 tests |
| `test_filter_ops.py` | Unit tests for `eval_condition()` and `eval_filter()`: all operators, logical operators, edge cases | ~30 tests |
| `test_pipeline.py` | Pipeline `pipeline()`: stage references, multi-stage joins, real-world Bokun activity data | ~15 tests |

Tests include real-world fixtures based on the Bokun travel/activity API.

---

## CI/CD Pipeline

### `.github/workflows/test.yml` -- Continuous Integration

- **Trigger:** Push to `main`, pull requests to `main`
- **Matrix:** Python 3.10, 3.11, 3.12 on Ubuntu
- **Steps:** Install uv, sync dev dependencies, lint with ruff, run pytest

### `.github/workflows/workflow.yml` -- Publish to PyPI

- **Trigger:** GitHub release published
- **Steps:** Install uv, build `siphon-dsl` package, publish via trusted publisher (OIDC)

---

## Quick Reference

### Development Commands

```bash
# Install dependencies
uv sync --group dev

# Run all tests
uv run pytest

# Run a single test
uv run pytest tests/test_siphon.py::TestSimplePath::test_extracts_simple_path

# Lint
uv run ruff check libs tests

# Build the package
uv build --package siphon-dsl
```

### Package Installation

```bash
pip install siphon-dsl             # Core (no dependencies)
pip install siphon-dsl[http]       # + requests for fetch_and_process
pip install siphon-dsl[typed]      # + pydantic for typed specs
```

### Public API Summary

```python
from siphon import process, fetch_and_process, query, pipeline
from siphon.typed import (
    process_spec, fetch_and_process_spec,
    query_typed, pipeline_typed,
    ExtractSpec, FieldSpec, ChainSpec, PipelineSpec, SortSpec,
)
```

### Key Design Decisions

- **Zero runtime dependencies:** The core library imports only `dataclasses`, `typing`, and `re`
- **Pydantic is optional:** Typed models require `pip install siphon-dsl[typed]`
- **`from` is aliased to `from_`:** Python keyword conflict resolved via Pydantic's `Field(alias="from")`
- **`None` sorts last:** In both ascending and descending order
- **Child wins on collision:** In carry-forward merges, child-level field values overwrite parent-level values with the same key
- **Multi-star auto-decomposition:** Paths like `$.a[*].b[*]` are automatically decomposed into nested chain specs
