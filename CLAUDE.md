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

# Format + lint (run together; format first to avoid fixable errors)
uv run ruff format libs tests && uv run ruff check libs tests

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
- Extended: `{path, where, select, collect, reduce}` - filtering, projection, and aggregation

---

## Development Workflow

### TDD (mandatory for all code changes)

1. **Write the test first** — define input, expected output, and edge cases before touching implementation. Group tests in a class matching the feature (e.g. `TestReduceSumCount`).
2. **Run new tests and confirm they fail** — `uv run pytest <test_path> -v`. This proves the test actually exercises the new code path.
3. **Implement** — minimum change to make the tests pass.
4. **Run the full suite** — `uv run pytest`. Confirm no regressions.

Never write implementation before a failing test exists. Never skip the failure-confirmation step.

---

### After adding or changing a feature — checklist

Every feature change must propagate through **all** of the following layers. Do not skip any.

#### 1. Core implementation (`libs/siphon-dsl/siphon/__init__.py`)
- Update `FieldSpec` dataclass if new fields are introduced
- Update `parse_field()` to handle the new field
- Implement logic in `Extractor.extract()` or an appropriate helper

#### 2. Typed spec (`libs/siphon-dsl/siphon/typed.py`)
- Mirror any new `FieldSpec` fields in the Pydantic `FieldSpec` model
- Include a docstring explaining accepted values
- `extra="forbid"` means omitting a field causes a `ValidationError` — always keep in sync
- Add tests in `tests/test_typed.py` covering: field default, string form, dict form, `model_dump` serialisation, and end-to-end `process_spec`

#### 3. Spec version doc (`specs/`)
- Create a new `specs/vX.Y.md` for the new version (e.g. `specs/v0.8.md`)
- Follow the structure of `specs/v0.5.md`: Overview, FieldSpec Schema, feature sections with examples, Behavior Reference, Changes from vX.Y-1
- Move the old `specs/vX.Y.md` to `specs/history/` only when a newer version fully supersedes it
- The current latest spec file stays at the root of `specs/`

#### 4. README (`libs/siphon-dsl/README.md`)
- Add the new feature to the Features table
- Add a concise section under "Spec Format" with YAML/Python examples
- Update the Spec History link to point to the latest spec version

#### 5. Developer docs (`docs/index.html`)
- Add a sidebar nav entry (sub-link under the relevant API section)
- Update the FieldSpec schema tab to show the new field
- Add a new `<h3>` subsection with code examples and an operator/behaviour table
- Add to the Behavior Reference section if return-value semantics change

#### 6. PM/overview docs (`docs/index-pm.html`)
- Add a Key Benefits card if the feature is user-facing and significant
- Update the relevant feature tab (`tab-process`, etc.) — "When to use it" blurb
- Add a FAQ entry (collapsible) for the feature
- Add a Glossary entry
