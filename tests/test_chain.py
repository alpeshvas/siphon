"""
Tests for the chaining query engine - untyped query() function.

Organized by feature: single-level, sort, limit/offset, then chaining, etc.
"""

import pytest
from siphon._chain import query


@pytest.fixture
def flat_data():
    """Simple flat data with one array."""
    return {
        "items": [
            {"id": 1, "status": "active", "name": "Alice"},
            {"id": 2, "status": "inactive", "name": "Bob"},
            {"id": 3, "status": "active", "name": "Charlie"},
        ]
    }


@pytest.fixture
def prices():
    """Numeric data for sorting."""
    return {
        "products": [
            {"id": 1, "name": "Widget", "price": 100},
            {"id": 2, "name": "Gadget", "price": 50},
            {"id": 3, "name": "Thing", "price": 150},
        ]
    }


class TestSingleLevel:
    """Test single-level chain specs (no 'then')."""

    def test_from_absolute_path_collect_true(self, flat_data):
        """Extract all items from absolute path."""
        spec = {
            "from": "$.items[*]",
            "collect": True
        }
        result = query(spec, flat_data)
        assert isinstance(result, list)
        assert len(result) == 3
        assert result[0]["id"] == 1

    def test_from_relative_path(self, flat_data):
        """Relative path (no $.)."""
        spec = {
            "from": "items[*]",
            "collect": True
        }
        result = query(spec, flat_data)
        assert isinstance(result, list)
        assert len(result) == 3

    def test_from_returns_first_match_by_default(self, flat_data):
        """Without collect, returns first item as dict, not list."""
        spec = {
            "from": "$.items[*]"
        }
        result = query(spec, flat_data)
        assert isinstance(result, dict)
        assert result["id"] == 1

    def test_where_equality_shorthand(self, flat_data):
        """Filter with equality shorthand."""
        spec = {
            "from": "$.items[*]",
            "where": {"status": "active"},
            "collect": True
        }
        result = query(spec, flat_data)
        assert len(result) == 2
        assert all(item["status"] == "active" for item in result)

    def test_where_operator(self, flat_data):
        """Filter with operator."""
        spec = {
            "from": "$.items[*]",
            "where": {"id": {"$gt": 1}},
            "collect": True
        }
        result = query(spec, flat_data)
        assert len(result) == 2
        assert all(item["id"] > 1 for item in result)

    def test_where_multiple_conditions(self, flat_data):
        """Multiple where conditions (implicit AND)."""
        spec = {
            "from": "$.items[*]",
            "where": {"status": "active", "id": {"$gt": 1}},
            "collect": True
        }
        result = query(spec, flat_data)
        assert len(result) == 1
        assert result[0]["id"] == 3

    def test_select_renames_fields(self, flat_data):
        """Projection renames fields."""
        spec = {
            "from": "$.items[*]",
            "select": {"person_id": "id", "person_name": "name"},
            "collect": True
        }
        result = query(spec, flat_data)
        assert result[0] == {"person_id": 1, "person_name": "Alice"}

    def test_collect_returns_all(self, flat_data):
        """collect: true returns list of all matches."""
        spec = {
            "from": "$.items[*]",
            "where": {"status": "active"},
            "collect": True
        }
        result = query(spec, flat_data)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_collect_false_returns_first(self, flat_data):
        """collect: false (default) returns first match as dict."""
        spec = {
            "from": "$.items[*]",
            "where": {"status": "active"}
        }
        result = query(spec, flat_data)
        assert isinstance(result, dict)
        assert result["name"] == "Alice"

    def test_no_match_collect_false_returns_none(self, flat_data):
        """No match with collect: false returns None."""
        spec = {
            "from": "$.items[*]",
            "where": {"status": "deleted"}
        }
        result = query(spec, flat_data)
        assert result is None

    def test_no_match_collect_true_returns_empty_list(self, flat_data):
        """No match with collect: true returns empty list."""
        spec = {
            "from": "$.items[*]",
            "where": {"status": "deleted"},
            "collect": True
        }
        result = query(spec, flat_data)
        assert result == []

    def test_select_without_collect(self, flat_data):
        """Select with collect: false returns first projected item."""
        spec = {
            "from": "$.items[*]",
            "where": {"status": "active"},
            "select": {"name": "name"}
        }
        result = query(spec, flat_data)
        assert result == {"name": "Alice"}

    def test_from_nonexistent_path(self):
        """Nonexistent path returns None/empty."""
        spec = {
            "from": "$.nonexistent[*]",
            "collect": True
        }
        result = query(spec, {"items": []})
        assert result == []

    def test_from_path_not_array(self):
        """Path that doesn't resolve to array returns empty."""
        spec = {
            "from": "$.notanarray[*]",
            "collect": True
        }
        result = query(spec, {"notanarray": "just a string"})
        assert result == []


@pytest.fixture
def nested_data():
    """Multi-level nested data (similar to Bokun structure)."""
    return {
        "pricesByDateRange": [
            {
                "dateRange": "2024-01-01",
                "rates": [
                    {
                        "rateId": 100,
                        "name": "Standard",
                        "passengers": [
                            {"pricingCategoryId": 1, "price": 50},
                            {"pricingCategoryId": 2, "price": 25},
                        ],
                    },
                    {
                        "rateId": 200,
                        "name": "Premium",
                        "passengers": [
                            {"pricingCategoryId": 1, "price": 75},
                            {"pricingCategoryId": 2, "price": 40},
                        ],
                    },
                ],
            },
            {
                "dateRange": "2024-01-02",
                "rates": [
                    {
                        "rateId": 100,
                        "name": "Standard",
                        "passengers": [
                            {"pricingCategoryId": 1, "price": 55},
                        ],
                    },
                ],
            },
        ]
    }


class TestThenChaining:
    """Test multi-level chaining with then."""

    def test_two_level_chain_basic(self, nested_data):
        """Basic two-level chain."""
        spec = {
            "from": "$.pricesByDateRange[*].rates[*]",
            "where": {"rateId": 200},
            "select": {"rate_id": "rateId", "rate_name": "name"},
            "collect": True
        }
        result = query(spec, nested_data)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["rate_id"] == 200
        assert result[0]["rate_name"] == "Premium"

    def test_carry_forward_from_parent_select(self, nested_data):
        """Parent select contributes fields to final output."""
        spec = {
            "from": "$.pricesByDateRange[*]",
            "select": {"dateRange": "dateRange"},
            "then": {
                "from": "rates[*]",
                "where": {"rateId": 200},
                "select": {"rate_id": "rateId"},
                "collect": True
            }
        }
        result = query(spec, nested_data)
        assert isinstance(result, list)
        assert len(result) == 1
        # Final output has both parent and child fields
        assert result[0]["dateRange"] == "2024-01-01"
        assert result[0]["rate_id"] == 200

    def test_carry_forward_absent_when_no_select(self, nested_data):
        """Without select at intermediate level, no fields carried forward."""
        spec = {
            "from": "$.pricesByDateRange[*]",
            # No select here
            "then": {
                "from": "rates[*]",
                "where": {"rateId": 200},
                "select": {"rate_id": "rateId"},
                "collect": True
            }
        }
        result = query(spec, nested_data)
        assert isinstance(result, list)
        assert len(result) == 1
        # Only child fields in output
        assert result[0] == {"rate_id": 200}
        assert "dateRange" not in result[0]

    def test_child_wins_on_key_collision(self, nested_data):
        """Child select value overwrites parent on key collision."""
        spec = {
            "from": "$.pricesByDateRange[*]",
            "select": {"id": "dateRange"},  # id = dateRange from parent
            "then": {
                "from": "rates[*]",
                "where": {"rateId": 200},
                "select": {"id": "rateId"},  # id = rateId from child
                "collect": True
            }
        }
        result = query(spec, nested_data)
        assert isinstance(result, list)
        # Child's "id" (rateId=200) should win
        assert result[0]["id"] == 200

    def test_three_level_chain(self, nested_data):
        """Three levels of nesting."""
        spec = {
            "from": "$.pricesByDateRange[*]",
            "select": {"dateRange": "dateRange"},
            "then": {
                "from": "rates[*]",
                "where": {"rateId": 200},
                "select": {"rate_id": "rateId"},
                "then": {
                    "from": "passengers[*]",
                    "select": {"price": "price"},
                    "collect": True
                }
            }
        }
        result = query(spec, nested_data)
        assert isinstance(result, list)
        assert len(result) == 2
        assert all("dateRange" in item for item in result)
        assert all("rate_id" in item for item in result)
        assert all("price" in item for item in result)

    def test_then_uses_original_item(self, nested_data):
        """Child then operates on original item, not projected."""
        spec = {
            "from": "$.pricesByDateRange[*].rates[*]",
            "select": {"rate_name": "name"},
            "then": {
                "from": "passengers[*]",  # This still resolves against original "passengers" key
                "select": {"price": "price"},
                "collect": True
            }
        }
        result = query(spec, nested_data)
        # Should get passengers even though name was projected
        assert len(result) > 0
        assert all("price" in item for item in result)

    def test_where_at_parent_restricts_children(self, nested_data):
        """Parent where filter restricts what children see."""
        spec = {
            "from": "$.pricesByDateRange[*]",
            "where": {"dateRange": "2024-01-01"},
            "then": {
                "from": "rates[*]",
                "select": {"rate_id": "rateId"},
                "collect": True
            }
        }
        result = query(spec, nested_data)
        assert isinstance(result, list)
        # Only rates from 2024-01-01 (which has rateIds 100, 200)
        assert len(result) == 2
        rate_ids = [r["rate_id"] for r in result]
        assert set(rate_ids) == {100, 200}

    def test_where_at_both_levels(self, nested_data):
        """Filtering at both parent and child level."""
        spec = {
            "from": "$.pricesByDateRange[*]",
            "where": {"dateRange": "2024-01-01"},
            "then": {
                "from": "rates[*]",
                "where": {"rateId": 200},
                "select": {"rate_id": "rateId"},
                "collect": True
            }
        }
        result = query(spec, nested_data)
        assert len(result) == 1
        assert result[0]["rate_id"] == 200

    def test_sort_at_intermediate_level(self, nested_data):
        """Sort applies at the level before then."""
        spec = {
            "from": "$.pricesByDateRange[*]",
            "select": {"dateRange": "dateRange"},
            "then": {
                "from": "rates[*]",
                "select": {"rate_id": "rateId"},
                "sort": [{"field": "rateId", "order": "desc"}],
                "collect": True
            }
        }
        result = query(spec, nested_data)
        # Should be sorted descending by rateId within each dateRange
        assert result[0]["rate_id"] > result[1]["rate_id"]


class TestSort:
    """Test sorting at single level."""

    def test_sort_ascending(self, prices):
        """Sort by price ascending."""
        spec = {
            "from": "$.products[*]",
            "sort": [{"field": "price", "order": "asc"}],
            "collect": True
        }
        result = query(spec, prices)
        assert result[0]["price"] == 50
        assert result[1]["price"] == 100
        assert result[2]["price"] == 150

    def test_sort_descending(self, prices):
        """Sort descending."""
        spec = {
            "from": "$.products[*]",
            "sort": [{"field": "price", "order": "desc"}],
            "collect": True
        }
        result = query(spec, prices)
        assert result[0]["price"] == 150
        assert result[1]["price"] == 100
        assert result[2]["price"] == 50

    def test_sort_multi_key(self):
        """Multi-key sort."""
        data = {
            "items": [
                {"category": "A", "value": 2},
                {"category": "B", "value": 1},
                {"category": "A", "value": 1},
            ]
        }
        spec = {
            "from": "$.items[*]",
            "sort": [
                {"field": "category", "order": "asc"},
                {"field": "value", "order": "asc"}
            ],
            "collect": True
        }
        result = query(spec, data)
        assert result[0] == {"category": "A", "value": 1}
        assert result[1] == {"category": "A", "value": 2}
        assert result[2] == {"category": "B", "value": 1}

    def test_sort_with_none_values(self):
        """None values sort last."""
        data = {
            "items": [
                {"id": 1, "value": 50},
                {"id": 2, "value": None},
                {"id": 3, "value": 30},
            ]
        }
        spec = {
            "from": "$.items[*]",
            "sort": [{"field": "value", "order": "asc"}],
            "collect": True
        }
        result = query(spec, data)
        assert result[0]["value"] == 30
        assert result[1]["value"] == 50
        assert result[2]["value"] is None

    def test_sort_none_values_desc_still_last(self):
        """None values sort last even in descending order."""
        data = {
            "items": [
                {"id": 1, "value": 50},
                {"id": 2, "value": None},
                {"id": 3, "value": 30},
            ]
        }
        spec = {
            "from": "$.items[*]",
            "sort": [{"field": "value", "order": "desc"}],
            "collect": True
        }
        result = query(spec, data)
        assert result[0]["value"] == 50
        assert result[1]["value"] == 30
        assert result[2]["value"] is None


class TestLimitOffset:
    """Test limit and offset."""

    def test_limit_restricts_results(self, flat_data):
        """Limit returns only first N items."""
        spec = {
            "from": "$.items[*]",
            "limit": 2,
            "collect": True
        }
        result = query(spec, flat_data)
        assert len(result) == 2

    def test_offset_skips_results(self, flat_data):
        """Offset skips first N items."""
        spec = {
            "from": "$.items[*]",
            "offset": 1,
            "collect": True
        }
        result = query(spec, flat_data)
        assert len(result) == 2
        assert result[0]["id"] == 2

    def test_limit_and_offset_combined(self, flat_data):
        """Offset + limit returns a window."""
        spec = {
            "from": "$.items[*]",
            "offset": 1,
            "limit": 1,
            "collect": True
        }
        result = query(spec, flat_data)
        assert len(result) == 1
        assert result[0]["id"] == 2

    def test_offset_beyond_length(self, flat_data):
        """Offset beyond available items returns empty."""
        spec = {
            "from": "$.items[*]",
            "offset": 100,
            "collect": True
        }
        result = query(spec, flat_data)
        assert result == []

    def test_limit_larger_than_available(self, flat_data):
        """Limit larger than available returns all remaining."""
        spec = {
            "from": "$.items[*]",
            "limit": 100,
            "collect": True
        }
        result = query(spec, flat_data)
        assert len(result) == 3

    def test_sort_then_limit(self, prices):
        """Sort is applied before limit."""
        spec = {
            "from": "$.products[*]",
            "sort": [{"field": "price", "order": "asc"}],
            "limit": 2,
            "collect": True
        }
        result = query(spec, prices)
        assert len(result) == 2
        assert result[0]["price"] == 50
        assert result[1]["price"] == 100

    def test_sort_offset_limit(self, prices):
        """All three together."""
        spec = {
            "from": "$.products[*]",
            "sort": [{"field": "price", "order": "asc"}],
            "offset": 1,
            "limit": 1,
            "collect": True
        }
        result = query(spec, prices)
        assert len(result) == 1
        assert result[0]["price"] == 100
