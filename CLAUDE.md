# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Siphon is a minimal DSL for extracting data from JSON APIs. The library is ~100 lines of code with no runtime dependencies.

## Development Commands

```bash
# Install dependencies (requires uv)
uv sync --group dev

# Run tests
uv run pytest

# Run a single test
uv run pytest tests/test_siphon.py::TestClassName::test_method_name

# Lint
uv run ruff check libs tests

# Build the package
uv build --package siphon-dsl
```

## Architecture

This is a uv workspace monorepo:

- **Root `pyproject.toml`**: Workspace configuration with dev dependencies (pytest, ruff, pyyaml)
- **`libs/siphon-dsl/`**: The publishable package (`siphon-dsl` on PyPI)
  - **`siphon/__init__.py`**: All library code lives here (~100 lines)

### Core Components

The library exports two main functions:
- `process(spec, data)` - Extract data from a dict using a spec
- `fetch_and_process(spec, base_url)` - Fetch from API and extract (requires `requests`)

Internal structure in `siphon/__init__.py`:
- `FieldSpec` dataclass: Holds path, where, select, collect options
- `parse_field()`: Converts spec dict/string to FieldSpec
- `get_by_path()`: Traverses dot notation paths
- `extract_array_with_path()`: Handles `[*]` array iteration
- `matches()`: Filters items by where conditions
- `project()`: Renames/projects fields via select
- `Extractor.extract()`: Main extraction logic

### Spec Format

Specs use JSONPath-like syntax:
- Simple: `"$.data.id"` - extract nested values
- Arrays: `"$.items[*].name"` - iterate with `[*]`
- Extended: `{path, where, select, collect}` - filtering and projection
