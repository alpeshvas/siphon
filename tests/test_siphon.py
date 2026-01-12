import pytest

from siphon import process


@pytest.fixture
def sample_data():
    return {
        "data": {
            "id": "prod_123",
            "items": [
                {
                    "id": 1,
                    "status": "active",
                    "name": "Widget",
                    "pricing": {"amount": 100, "currency": "USD"},
                },
                {
                    "id": 2,
                    "status": "inactive",
                    "name": "Gadget",
                    "pricing": {"amount": 200, "currency": "EUR"},
                },
                {
                    "id": 3,
                    "status": "active",
                    "name": "Thing",
                    "pricing": {"amount": 50, "currency": "GBP"},
                },
            ],
        }
    }


class TestSimplePath:
    def test_extracts_simple_path(self, sample_data):
        spec = {"extract": {"id": "$.data.id"}}
        assert process(spec, sample_data) == {"id": "prod_123"}

    def test_extracts_nested_path(self, sample_data):
        spec = {"extract": {"price": "$.data.items[*].pricing.amount"}}
        assert process(spec, sample_data) == {"price": 100}

    def test_returns_none_for_missing_path(self, sample_data):
        spec = {"extract": {"missing": "$.data.nonexistent"}}
        assert process(spec, sample_data) == {"missing": None}


class TestArrayIteration:
    def test_returns_first_item(self, sample_data):
        spec = {"extract": {"first_name": "$.data.items[*].name"}}
        assert process(spec, sample_data) == {"first_name": "Widget"}

    def test_returns_first_item_full_object(self, sample_data):
        spec = {"extract": {"first": {"path": "$.data.items[*]"}}}
        result = process(spec, sample_data)
        assert result["first"]["id"] == 1
        assert result["first"]["name"] == "Widget"


class TestWhere:
    def test_filters_by_field(self, sample_data):
        spec = {
            "extract": {
                "inactive": {
                    "path": "$.data.items[*]",
                    "where": {"status": "inactive"},
                }
            }
        }
        result = process(spec, sample_data)
        assert result["inactive"]["name"] == "Gadget"

    def test_returns_none_when_no_match(self, sample_data):
        spec = {
            "extract": {
                "missing": {
                    "path": "$.data.items[*]",
                    "where": {"status": "deleted"},
                }
            }
        }
        assert process(spec, sample_data) == {"missing": None}


class TestSelect:
    def test_projects_fields(self, sample_data):
        spec = {
            "extract": {
                "item": {
                    "path": "$.data.items[*]",
                    "select": {"item_id": "id", "item_name": "name"},
                }
            }
        }
        assert process(spec, sample_data) == {"item": {"item_id": 1, "item_name": "Widget"}}

    def test_projects_nested_fields(self, sample_data):
        spec = {
            "extract": {
                "pricing": {
                    "path": "$.data.items[*]",
                    "select": {"cost": "pricing.amount", "curr": "pricing.currency"},
                }
            }
        }
        assert process(spec, sample_data) == {"pricing": {"cost": 100, "curr": "USD"}}


class TestCollect:
    def test_collects_all_items(self, sample_data):
        spec = {
            "extract": {
                "all_names": {
                    "path": "$.data.items[*].name",
                    "collect": True,
                }
            }
        }
        assert process(spec, sample_data) == {"all_names": ["Widget", "Gadget", "Thing"]}

    def test_collects_with_where(self, sample_data):
        spec = {
            "extract": {
                "active": {
                    "path": "$.data.items[*]",
                    "where": {"status": "active"},
                    "select": {"name": "name"},
                    "collect": True,
                }
            }
        }
        assert process(spec, sample_data) == {"active": [{"name": "Widget"}, {"name": "Thing"}]}

    def test_collect_returns_empty_list_when_no_match(self, sample_data):
        spec = {
            "extract": {
                "deleted": {
                    "path": "$.data.items[*]",
                    "where": {"status": "deleted"},
                    "collect": True,
                }
            }
        }
        assert process(spec, sample_data) == {"deleted": []}


class TestCombined:
    def test_multiple_extractions(self, sample_data):
        spec = {
            "extract": {
                "id": "$.data.id",
                "first_active": {
                    "path": "$.data.items[*]",
                    "where": {"status": "active"},
                    "select": {"item_id": "id", "item_name": "name"},
                },
                "all_active": {
                    "path": "$.data.items[*]",
                    "where": {"status": "active"},
                    "select": {"item_id": "id", "item_name": "name"},
                    "collect": True,
                },
            }
        }
        result = process(spec, sample_data)
        assert result["id"] == "prod_123"
        assert result["first_active"] == {"item_id": 1, "item_name": "Widget"}
        assert result["all_active"] == [
            {"item_id": 1, "item_name": "Widget"},
            {"item_id": 3, "item_name": "Thing"},
        ]
