"""
Unit tests for filter operators in the chain query engine.

Tests eval_condition and eval_filter in isolation.
"""

import pytest
from siphon._chain import eval_condition, eval_filter


class TestEvalCondition:
    """Test single-field operator evaluation."""

    # Equality operators
    def test_eq_match(self):
        assert eval_condition("active", {"$eq": "active"})

    def test_eq_no_match(self):
        assert not eval_condition("inactive", {"$eq": "active"})

    def test_eq_shorthand(self):
        """Bare value is shorthand for $eq."""
        assert eval_condition("active", "active")
        assert not eval_condition("inactive", "active")

    # Inequality
    def test_ne_match(self):
        assert eval_condition("inactive", {"$ne": "active"})

    def test_ne_no_match(self):
        assert not eval_condition("active", {"$ne": "active"})

    # Greater than
    def test_gt_above(self):
        assert eval_condition(100, {"$gt": 50})

    def test_gt_equal(self):
        assert not eval_condition(50, {"$gt": 50})

    def test_gt_below(self):
        assert not eval_condition(25, {"$gt": 50})

    def test_gt_none_returns_false(self):
        """None is always False for numeric comparisons."""
        assert not eval_condition(None, {"$gt": 50})

    # Greater than or equal
    def test_gte_equal(self):
        assert eval_condition(50, {"$gte": 50})

    def test_gte_above(self):
        assert eval_condition(100, {"$gte": 50})

    def test_gte_below(self):
        assert not eval_condition(25, {"$gte": 50})

    # Less than
    def test_lt_below(self):
        assert eval_condition(25, {"$lt": 50})

    def test_lt_equal(self):
        assert not eval_condition(50, {"$lt": 50})

    def test_lt_above(self):
        assert not eval_condition(100, {"$lt": 50})

    # Less than or equal
    def test_lte_equal(self):
        assert eval_condition(50, {"$lte": 50})

    def test_lte_below(self):
        assert eval_condition(25, {"$lte": 50})

    def test_lte_above(self):
        assert not eval_condition(100, {"$lte": 50})

    # In operator
    def test_in_present(self):
        assert eval_condition("admin", {"$in": ["admin", "mod", "user"]})

    def test_in_absent(self):
        assert not eval_condition("guest", {"$in": ["admin", "mod", "user"]})

    # Not in operator
    def test_nin_absent(self):
        assert eval_condition("guest", {"$nin": ["admin", "mod", "user"]})

    def test_nin_present(self):
        assert not eval_condition("admin", {"$nin": ["admin", "mod", "user"]})

    # Exists operator
    def test_exists_true_when_present(self):
        """$exists: true checks if field is not None."""
        assert eval_condition("value", {"$exists": True})
        assert eval_condition(0, {"$exists": True})
        assert eval_condition("", {"$exists": True})

    def test_exists_true_when_absent(self):
        assert not eval_condition(None, {"$exists": True})

    def test_exists_false_when_present(self):
        """$exists: false checks if field is None."""
        assert not eval_condition("value", {"$exists": False})

    def test_exists_false_when_absent(self):
        assert eval_condition(None, {"$exists": False})

    # Regex operator
    def test_regex_match(self):
        assert eval_condition("email@example.com", {"$regex": "@example"})

    def test_regex_no_match(self):
        assert not eval_condition("email@other.com", {"$regex": "@example"})

    def test_regex_on_none(self):
        """Regex on None returns False."""
        assert not eval_condition(None, {"$regex": "pattern"})

    def test_regex_on_number(self):
        """Regex coerces to string."""
        assert eval_condition(12345, {"$regex": "234"})

    # Multiple operators (all must pass)
    def test_multiple_operators(self):
        """All operators in a dict must be satisfied."""
        assert eval_condition(75, {"$gt": 50, "$lt": 100})
        assert not eval_condition(75, {"$gt": 50, "$lt": 75})  # $lt fails (equals, not less)

    # Unknown operator
    def test_unknown_operator_raises(self):
        with pytest.raises(ValueError, match="Unknown operator"):
            eval_condition(50, {"$fake": 100})


class TestEvalFilter:
    """Test full filter evaluation with logical operators."""

    @pytest.fixture
    def sample_item(self):
        return {"id": 1, "status": "active", "price": {"amount": 100, "currency": "USD"}}

    # Simple field matching
    def test_simple_field_match(self, sample_item):
        assert eval_filter({"status": "active"}, sample_item)

    def test_simple_field_no_match(self, sample_item):
        assert not eval_filter({"status": "inactive"}, sample_item)

    # Nested path matching
    def test_nested_path_filter(self, sample_item):
        assert eval_filter({"price.amount": {"$gt": 50}}, sample_item)
        assert not eval_filter({"price.amount": {"$gt": 200}}, sample_item)

    def test_nested_path_not_exists(self, sample_item):
        """Path that doesn't exist returns False."""
        assert not eval_filter({"price.amount": 100}, {"price": {"currency": "USD"}})

    # None where (always true)
    def test_none_where(self, sample_item):
        assert eval_filter(None, sample_item)

    # Empty where (always true)
    def test_empty_where(self, sample_item):
        assert eval_filter({}, sample_item)

    # Logical operators
    def test_and_all_true(self, sample_item):
        where = {"$and": [{"status": "active"}, {"id": {"$gt": 0}}]}
        assert eval_filter(where, sample_item)

    def test_and_one_false(self, sample_item):
        where = {"$and": [{"status": "active"}, {"id": {"$gt": 10}}]}
        assert not eval_filter(where, sample_item)

    def test_or_one_true(self, sample_item):
        where = {"$or": [{"status": "inactive"}, {"id": {"$gt": 0}}]}
        assert eval_filter(where, sample_item)

    def test_or_all_false(self, sample_item):
        where = {"$or": [{"status": "inactive"}, {"id": {"$gt": 10}}]}
        assert not eval_filter(where, sample_item)

    def test_not_negates_true(self, sample_item):
        where = {"$not": {"status": "active"}}
        assert not eval_filter(where, sample_item)

    def test_not_negates_false(self, sample_item):
        where = {"$not": {"status": "inactive"}}
        assert eval_filter(where, sample_item)

    def test_nor_none_match(self, sample_item):
        where = {"$nor": [{"status": "inactive"}, {"id": {"$lt": 0}}]}
        assert eval_filter(where, sample_item)

    def test_nor_one_matches(self, sample_item):
        where = {"$nor": [{"status": "active"}, {"id": {"$lt": 0}}]}
        assert not eval_filter(where, sample_item)

    # Complex nested logical
    def test_and_with_operators(self, sample_item):
        where = {"$and": [{"price.amount": {"$gt": 50}}, {"price.amount": {"$lt": 150}}]}
        assert eval_filter(where, sample_item)

    def test_nested_logical_and_or(self, sample_item):
        where = {"$and": [{"status": "active"}, {"$or": [{"id": 1}, {"id": 2}]}]}
        assert eval_filter(where, sample_item)

    # Multiple field conditions (implicit AND)
    def test_multiple_fields_implicit_and(self, sample_item):
        """Multiple top-level keys act as AND."""
        where = {"status": "active", "id": {"$gt": 0}}
        assert eval_filter(where, sample_item)

    def test_multiple_fields_one_fails(self, sample_item):
        where = {"status": "active", "id": {"$gt": 10}}
        assert not eval_filter(where, sample_item)
