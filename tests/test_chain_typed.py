"""
Tests for the typed chain query interface (ChainSpec, SortSpec, query_typed).
"""

import json

import pytest
from siphon.typed import ChainSpec, SortSpec, query_typed


class TestSortSpec:
    """Test SortSpec Pydantic model."""

    def test_default_order_is_asc(self):
        """Default order is ascending."""
        spec = SortSpec(field="price")
        assert spec.order == "asc"

    def test_explicit_desc(self):
        """Explicit descending order."""
        spec = SortSpec(field="price", order="desc")
        assert spec.order == "desc"

    def test_rejects_invalid_order(self):
        """Invalid order value is rejected."""
        with pytest.raises(Exception):  # ValidationError
            SortSpec(field="price", order="invalid")

    def test_extra_fields_rejected(self):
        """Extra fields are rejected."""
        with pytest.raises(Exception):
            SortSpec(field="price", unknown_field="value")


class TestChainSpec:
    """Test ChainSpec Pydantic model."""

    def test_minimal_spec(self):
        """Only from is required."""
        spec = ChainSpec(from_="$.items[*]")
        assert spec.from_ == "$.items[*]"
        assert spec.where is None
        assert spec.collect is False

    def test_from_alias_in_json(self):
        """from_ field uses 'from' alias in JSON."""
        data = {"from": "$.items[*]"}
        spec = ChainSpec.model_validate(data)
        assert spec.from_ == "$.items[*]"

    def test_model_dump_uses_from_alias(self):
        """model_dump by_alias produces 'from' key."""
        spec = ChainSpec(from_="$.items[*]")
        dumped = spec.model_dump(by_alias=True)
        assert "from" in dumped
        assert "from_" not in dumped
        assert dumped["from"] == "$.items[*]"

    def test_full_spec(self):
        """All fields populated."""
        spec = ChainSpec(
            from_="$.items[*]",
            where={"status": "active"},
            select={"id": "item_id"},
            sort=[SortSpec(field="price", order="asc")],
            limit=10,
            offset=5,
            collect=True,
        )
        assert spec.where == {"status": "active"}
        assert spec.collect is True
        assert len(spec.sort) == 1

    def test_self_referential_then(self):
        """then field is self-referential."""
        spec = ChainSpec(
            from_="$.items[*]",
            then=ChainSpec(from_="subitems[*]")
        )
        assert isinstance(spec.then, ChainSpec)
        assert spec.then.from_ == "subitems[*]"

    def test_three_level_nesting(self):
        """Three levels of nesting."""
        spec = ChainSpec(
            from_="$.level1[*]",
            then=ChainSpec(
                from_="level2[*]",
                then=ChainSpec(from_="level3[*]")
            )
        )
        assert spec.then.then.from_ == "level3[*]"

    def test_rejects_extra_fields(self):
        """Extra fields rejected."""
        with pytest.raises(Exception):
            ChainSpec(from_="$.items[*]", unknown_field="value")


class TestChainSpecSerialization:
    """Test JSON serialization for LLM tool calls."""

    def test_json_schema_generation(self):
        """ChainSpec produces valid JSON schema."""
        schema = ChainSpec.model_json_schema()
        # The schema should have "from" in properties, not "from_"
        # Pydantic v2 may have properties under the main schema or $defs
        if "$defs" in schema:
            chain_spec_schema = schema.get("$defs", {}).get("ChainSpec", schema)
        else:
            chain_spec_schema = schema
        assert "from" in chain_spec_schema.get("properties", {})
        assert "from_" not in chain_spec_schema.get("properties", {})

    def test_schema_has_required_from(self):
        """'from' is required in schema."""
        schema = ChainSpec.model_json_schema()
        if "$defs" in schema:
            chain_spec_schema = schema.get("$defs", {}).get("ChainSpec", schema)
        else:
            chain_spec_schema = schema
        assert "from" in chain_spec_schema.get("required", [])

    def test_schema_then_is_recursive(self):
        """Schema for 'then' references ChainSpec."""
        schema = ChainSpec.model_json_schema()
        if "$defs" in schema:
            chain_spec_schema = schema.get("$defs", {}).get("ChainSpec", schema)
        else:
            chain_spec_schema = schema
        # then should be in properties
        assert "then" in chain_spec_schema.get("properties", {})

    def test_round_trip_serialization(self):
        """Spec can serialize and deserialize."""
        original = ChainSpec(
            from_="$.items[*]",
            where={"status": "active"},
            select={"id": "item_id"},
            collect=True
        )
        dumped = original.model_dump(by_alias=True, exclude_none=True)
        restored = ChainSpec.model_validate(dumped)
        assert restored.from_ == original.from_
        assert restored.where == original.where


class TestQueryTyped:
    """Test query_typed function."""

    @pytest.fixture
    def sample_data(self):
        return {
            "items": [
                {"id": 1, "status": "active", "price": 100},
                {"id": 2, "status": "inactive", "price": 50},
                {"id": 3, "status": "active", "price": 150},
            ]
        }

    def test_simple_path(self, sample_data):
        """Simple extraction with typed model."""
        spec = ChainSpec(
            from_="$.items[*]",
            where={"status": "active"},
            collect=True
        )
        result = query_typed(spec, sample_data)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_with_select(self, sample_data):
        """Field projection via typed model."""
        spec = ChainSpec(
            from_="$.items[*]",
            where={"status": "active"},
            select={"item_id": "id"},
            collect=True
        )
        result = query_typed(spec, sample_data)
        assert len(result) == 2
        assert result[0] == {"item_id": 1}

    def test_with_sort(self, sample_data):
        """Sorting via typed model."""
        spec = ChainSpec(
            from_="$.items[*]",
            sort=[SortSpec(field="price", order="asc")],
            collect=True
        )
        result = query_typed(spec, sample_data)
        assert result[0]["price"] == 50

    def test_with_limit(self, sample_data):
        """Limit via typed model."""
        spec = ChainSpec(
            from_="$.items[*]",
            limit=2,
            collect=True
        )
        result = query_typed(spec, sample_data)
        assert len(result) == 2

    def test_with_then(self):
        """Multi-level extraction with typed models."""
        data = {
            "departments": [
                {
                    "name": "Engineering",
                    "employees": [
                        {"id": 1, "name": "Alice"},
                        {"id": 2, "name": "Bob"},
                    ]
                },
                {
                    "name": "Sales",
                    "employees": [
                        {"id": 3, "name": "Charlie"}
                    ]
                }
            ]
        }
        spec = ChainSpec(
            from_="$.departments[*]",
            select={"dept": "name"},
            then=ChainSpec(
                from_="employees[*]",
                select={"emp_name": "name"},
                collect=True
            )
        )
        result = query_typed(spec, data)
        assert isinstance(result, list)
        assert len(result) == 3
        assert result[0]["dept"] == "Engineering"
        assert result[0]["emp_name"] == "Alice"

    def test_typed_produces_same_results_as_untyped(self, sample_data):
        """Typed and untyped produce identical results."""
        from siphon._chain import query

        spec_obj = ChainSpec(
            from_="$.items[*]",
            where={"status": "active"},
            select={"item_id": "id"},
            collect=True
        )
        spec_dict = spec_obj.model_dump(by_alias=True, exclude_none=True)

        typed_result = query_typed(spec_obj, sample_data)
        untyped_result = query(spec_dict, sample_data)

        assert typed_result == untyped_result


class TestChainSpecValidation:
    """Test validation of ChainSpec values."""

    def test_where_accepts_any_dict(self):
        """where accepts arbitrary dict structure."""
        spec = ChainSpec(
            from_="$.items[*]",
            where={"custom_op": "custom_value"}
        )
        assert spec.where == {"custom_op": "custom_value"}

    def test_select_must_have_string_values(self):
        """select values must be strings (paths)."""
        # This should pass
        spec = ChainSpec(
            from_="$.items[*]",
            select={"a": "path.to.field"}
        )
        assert spec.select == {"a": "path.to.field"}

    def test_collect_defaults_to_false(self):
        """collect defaults to False."""
        spec = ChainSpec(from_="$.items[*]")
        assert spec.collect is False

    def test_offset_and_limit_are_ints(self):
        """offset and limit must be integers."""
        spec = ChainSpec(
            from_="$.items[*]",
            offset=10,
            limit=20
        )
        assert spec.offset == 10
        assert spec.limit == 20
