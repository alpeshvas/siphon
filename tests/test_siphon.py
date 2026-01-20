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


@pytest.fixture
def nested_array_data():
    """Data structure similar to Bokun pricing API with nested arrays."""
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


class TestNestedArrays:
    def test_double_nested_array_first(self, nested_array_data):
        """Extract first passenger from nested rates."""
        spec = {
            "extract": {"first_passenger": "$.pricesByDateRange[*].rates[*].passengers[*].price"}
        }
        result = process(spec, nested_array_data)
        assert result["first_passenger"] == 50

    def test_double_nested_array_collect(self, nested_array_data):
        """Collect all passengers from all rates."""
        spec = {
            "extract": {
                "all_prices": {
                    "path": "$.pricesByDateRange[*].rates[*].passengers[*].price",
                    "collect": True,
                }
            }
        }
        result = process(spec, nested_array_data)
        assert result["all_prices"] == [50, 25, 75, 40, 55]

    def test_nested_with_where_at_rate_level(self, nested_array_data):
        """Filter rates by rateId, extract passengers from matching rate."""
        spec = {
            "extract": {
                "premium_rate": {
                    "path": "$.pricesByDateRange[*].rates[*]",
                    "where": {"rateId": 200},
                    "select": {"name": "name", "passengers": "passengers"},
                }
            }
        }
        result = process(spec, nested_array_data)
        assert result["premium_rate"]["name"] == "Premium"
        assert result["premium_rate"]["passengers"] == [
            {"pricingCategoryId": 1, "price": 75},
            {"pricingCategoryId": 2, "price": 40},
        ]

    def test_nested_with_where_on_innermost_level(self, nested_array_data):
        """Filter by pricingCategoryId at innermost level."""
        spec = {
            "extract": {
                "adult_prices": {
                    "path": "$.pricesByDateRange[*].rates[*].passengers[*]",
                    "where": {"pricingCategoryId": 1},
                    "select": {"price": "price"},
                    "collect": True,
                }
            }
        }
        result = process(spec, nested_array_data)
        assert result["adult_prices"] == [{"price": 50}, {"price": 75}, {"price": 55}]

    def test_triple_nested_collect_objects(self, nested_array_data):
        """Collect full passenger objects from triple nested arrays."""
        spec = {
            "extract": {
                "all_passengers": {
                    "path": "$.pricesByDateRange[*].rates[*].passengers[*]",
                    "collect": True,
                }
            }
        }
        result = process(spec, nested_array_data)
        assert len(result["all_passengers"]) == 5
        assert result["all_passengers"][0] == {"pricingCategoryId": 1, "price": 50}

    def test_nested_collect_with_select_projection(self, nested_array_data):
        """Collect nested items with field projection."""
        spec = {
            "extract": {
                "rate_names": {
                    "path": "$.pricesByDateRange[*].rates[*]",
                    "select": {"id": "rateId", "label": "name"},
                    "collect": True,
                }
            }
        }
        result = process(spec, nested_array_data)
        assert result["rate_names"] == [
            {"id": 100, "label": "Standard"},
            {"id": 200, "label": "Premium"},
            {"id": 100, "label": "Standard"},
        ]

    def test_filter_by_ancestor_property(self, nested_array_data):
        """Filter passengers by rateId from parent rate (ancestor filtering)."""
        spec = {
            "extract": {
                "premium_passengers": {
                    "path": "$.pricesByDateRange[*].rates[*].passengers[*]",
                    "where": {"rateId": 200},
                    "select": {"category": "pricingCategoryId", "amount": "price"},
                    "collect": True,
                }
            }
        }
        result = process(spec, nested_array_data)
        # Should return only passengers from rate 200 (Premium)
        assert result["premium_passengers"] == [
            {"category": 1, "amount": 75},
            {"category": 2, "amount": 40},
        ]

    def test_filter_by_multiple_ancestor_levels(self, nested_array_data):
        """Filter passengers by properties from multiple ancestor levels."""
        spec = {
            "extract": {
                "specific_passengers": {
                    "path": "$.pricesByDateRange[*].rates[*].passengers[*]",
                    "where": {"dateRange": "2024-01-01", "rateId": 100},
                    "select": {"category": "pricingCategoryId", "amount": "price"},
                    "collect": True,
                }
            }
        }
        result = process(spec, nested_array_data)
        # Should return passengers from rate 100 on date 2024-01-01 only
        assert result["specific_passengers"] == [
            {"category": 1, "amount": 50},
            {"category": 2, "amount": 25},
        ]


@pytest.fixture
def bokun_price_list_data():
    """Data structure matching Bokun /activity.json/<activityId>/price-list endpoint."""
    return {
        "activityId": 814165,
        "isPriceConverted": True,
        "conversionRate": 0.62,
        "defaultCurrency": "CAD",
        "pricesByDateRange": [
            {
                "from": "2026-01-20",
                "to": "2027-01-20",
                "rates": [
                    {
                        "rateId": 1565415,
                        "title": "All Inclusive Package",
                        "passengers": [
                            {
                                "pricingCategoryId": 789585,
                                "title": "Option 3: Adult with all add-ons",
                                "ticketCategory": "ADULT",
                                "price": {
                                    "currency": "EUR",
                                    "amount": 184.35,
                                    "ofWhichTax": 0.0,
                                    "converted": True,
                                    "conversionRate": 0.62,
                                    "inferred": True,
                                },
                                "tieredPrices": [],
                                "extras": [],
                            },
                            {
                                "pricingCategoryId": 789586,
                                "title": "Option 3: Child + all options",
                                "ticketCategory": "CHILD",
                                "price": {
                                    "currency": "EUR",
                                    "amount": 159.69,
                                    "ofWhichTax": 0.0,
                                    "converted": True,
                                    "conversionRate": 0.62,
                                    "inferred": True,
                                },
                                "tieredPrices": [],
                                "extras": [],
                            },
                        ],
                        "extras": [],
                    },
                    {
                        "rateId": 1760309,
                        "title": "Standard Tour: No Add-ons",
                        "passengers": [
                            {
                                "pricingCategoryId": 887614,
                                "title": "Option 1: Adult without add-ons",
                                "ticketCategory": "ADULT",
                                "price": {
                                    "currency": "EUR",
                                    "amount": 67.21,
                                    "ofWhichTax": 0.0,
                                    "converted": True,
                                    "conversionRate": 0.62,
                                    "inferred": True,
                                },
                                "tieredPrices": [],
                                "extras": [],
                            },
                            {
                                "pricingCategoryId": 887615,
                                "title": "Option 1: Child without Add-ons",
                                "ticketCategory": "ADULT",
                                "price": {
                                    "currency": "EUR",
                                    "amount": 61.04,
                                    "ofWhichTax": 0.0,
                                    "converted": True,
                                    "conversionRate": 0.62,
                                    "inferred": True,
                                },
                                "tieredPrices": [],
                                "extras": [],
                            },
                        ],
                        "extras": [],
                    },
                    {
                        "rateId": 1567944,
                        "title": "Attractions Package",
                        "passengers": [
                            {
                                "pricingCategoryId": 788209,
                                "title": "Option 2: Child + both attractions",
                                "ticketCategory": "CHILD",
                                "price": {
                                    "currency": "EUR",
                                    "amount": 113.45,
                                    "ofWhichTax": 0.0,
                                    "converted": True,
                                    "conversionRate": 0.62,
                                    "inferred": True,
                                },
                                "tieredPrices": [],
                                "extras": [],
                            },
                            {
                                "pricingCategoryId": 788208,
                                "title": "Option 2: Adult with attractions",
                                "ticketCategory": "ADULT",
                                "price": {
                                    "currency": "EUR",
                                    "amount": 135.03,
                                    "ofWhichTax": 0.0,
                                    "converted": True,
                                    "conversionRate": 0.62,
                                    "inferred": True,
                                },
                                "tieredPrices": [],
                                "extras": [],
                            },
                        ],
                        "extras": [],
                    },
                ],
            }
        ],
    }


class TestBokunPriceList:
    def test_extract_passengers_by_rate_id(self, bokun_price_list_data):
        """Real-world use case: extract passengers filtered by rateId with field projection."""
        spec = {
            "extract": {
                "passengers": {
                    "path": "$.pricesByDateRange[*].rates[*].passengers[*]",
                    "where": {"rateId": 1760309},
                    "select": {
                        "pricingCategoryId": "pricingCategoryId",
                        "title": "title",
                        "ticketCategory": "ticketCategory",
                        "amount": "price.amount",
                        "currency": "price.currency",
                    },
                    "collect": True,
                }
            }
        }
        result = process(spec, bokun_price_list_data)
        assert result["passengers"] == [
            {
                "pricingCategoryId": 887614,
                "title": "Option 1: Adult without add-ons",
                "ticketCategory": "ADULT",
                "amount": 67.21,
                "currency": "EUR",
            },
            {
                "pricingCategoryId": 887615,
                "title": "Option 1: Child without Add-ons",
                "ticketCategory": "ADULT",
                "amount": 61.04,
                "currency": "EUR",
            },
        ]
