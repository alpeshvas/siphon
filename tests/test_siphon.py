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
def availability_data():
    """Availability items with datetime fields across different dates."""
    return {
        "content": {
            "data": {
                "data": {
                    "items": [
                        {
                            "availability_from_date_time": "2026-04-11T13:30:00+04:00",
                            "availability_to_date_time": "2026-04-11T13:45:00+04:00",
                        },
                        {
                            "availability_from_date_time": "2026-04-12T09:15:00+04:00",
                            "availability_to_date_time": "2026-04-12T22:00:00+04:00",
                        },
                        {
                            "availability_from_date_time": "2026-04-13T14:00:00+04:00",
                            "availability_to_date_time": "2026-04-13T14:15:00+04:00",
                        },
                    ]
                }
            }
        }
    }


class TestReduceTimeOp:
    def test_min_time_returns_earliest_time_of_day(self, availability_data):
        """min_time picks the item whose time-of-day (ignoring date) is earliest."""
        spec = {
            "extract": {
                "earliest_from": {
                    "path": "$.content.data.data.items[*].availability_from_date_time",
                    "reduce": "min_time",
                }
            }
        }
        result = process(spec, availability_data)
        # 09:15 (item 2) is earlier than 13:30 (item 1) and 14:00 (item 3)
        assert result["earliest_from"] == "2026-04-12T09:15:00+04:00"

    def test_max_time_returns_latest_time_of_day(self, availability_data):
        """max_time picks the item whose time-of-day (ignoring date) is latest."""
        spec = {
            "extract": {
                "latest_to": {
                    "path": "$.content.data.data.items[*].availability_to_date_time",
                    "reduce": "max_time",
                }
            }
        }
        result = process(spec, availability_data)
        # 22:00 (item 2) is later than 13:45 (item 1) and 14:15 (item 3)
        assert result["latest_to"] == "2026-04-12T22:00:00+04:00"

    def test_combined_projection_two_fields_only(self, availability_data):
        """Real-world use: project earliest from-time and latest to-time."""
        spec = {
            "extract": {
                "earliest_from_datetime": {
                    "path": "$.content.data.data.items[*].availability_from_date_time",
                    "reduce": "min_time",
                },
                "latest_to_datetime": {
                    "path": "$.content.data.data.items[*].availability_to_date_time",
                    "reduce": "max_time",
                },
            }
        }
        result = process(spec, availability_data)
        assert result == {
            "earliest_from_datetime": "2026-04-12T09:15:00+04:00",
            "latest_to_datetime": "2026-04-12T22:00:00+04:00",
        }

    def test_reduce_returns_none_on_empty_array(self):
        spec = {
            "extract": {
                "val": {
                    "path": "$.items[*].dt",
                    "reduce": "min_time",
                }
            }
        }
        assert process(spec, {"items": []}) == {"val": None}


@pytest.fixture
def dated_items():
    return {
        "items": [
            {"created": "2026-03-15T10:00:00+00:00", "score": 42, "price": 19.99},
            {"created": "2026-01-01T23:59:00+00:00", "score": 7, "price": 5.5},
            {"created": "2026-06-30T08:00:00+00:00", "score": 99, "price": 150.0},
        ]
    }


class TestReduceDateOp:
    def test_min_date_returns_earliest_date(self, dated_items):
        """min_date picks the item with the earliest calendar date (ignoring time)."""
        spec = {"extract": {"earliest": {"path": "$.items[*].created", "reduce": "min_date"}}}
        result = process(spec, dated_items)
        assert result["earliest"] == "2026-01-01T23:59:00+00:00"

    def test_max_date_returns_latest_date(self, dated_items):
        """max_date picks the item with the latest calendar date (ignoring time)."""
        spec = {"extract": {"latest": {"path": "$.items[*].created", "reduce": "max_date"}}}
        result = process(spec, dated_items)
        assert result["latest"] == "2026-06-30T08:00:00+00:00"

    def test_min_date_empty_returns_none(self):
        spec = {"extract": {"val": {"path": "$.items[*].dt", "reduce": "min_date"}}}
        assert process(spec, {"items": []}) == {"val": None}


class TestReduceNumOp:
    def test_min_int_returns_smallest(self, dated_items):
        spec = {"extract": {"lowest": {"path": "$.items[*].score", "reduce": "min_int"}}}
        result = process(spec, dated_items)
        assert result["lowest"] == 7

    def test_max_int_returns_largest(self, dated_items):
        spec = {"extract": {"highest": {"path": "$.items[*].score", "reduce": "max_int"}}}
        result = process(spec, dated_items)
        assert result["highest"] == 99

    def test_min_int_works_with_floats(self, dated_items):
        spec = {"extract": {"cheapest": {"path": "$.items[*].price", "reduce": "min_int"}}}
        result = process(spec, dated_items)
        assert result["cheapest"] == 5.5

    def test_max_int_works_with_floats(self, dated_items):
        spec = {"extract": {"priciest": {"path": "$.items[*].price", "reduce": "max_int"}}}
        result = process(spec, dated_items)
        assert result["priciest"] == 150.0

    def test_min_int_empty_returns_none(self):
        spec = {"extract": {"val": {"path": "$.items[*].n", "reduce": "min_int"}}}
        assert process(spec, {"items": []}) == {"val": None}


class TestReduceSumCount:
    def test_sum_integers(self, dated_items):
        spec = {"extract": {"total": {"path": "$.items[*].score", "reduce": "sum"}}}
        assert process(spec, dated_items)["total"] == 148  # 42 + 7 + 99

    def test_sum_floats(self, dated_items):
        spec = {"extract": {"total": {"path": "$.items[*].price", "reduce": "sum"}}}
        assert process(spec, dated_items)["total"] == pytest.approx(175.49)

    def test_count_items(self, dated_items):
        spec = {"extract": {"n": {"path": "$.items[*].score", "reduce": "count"}}}
        assert process(spec, dated_items)["n"] == 3

    def test_sum_empty_returns_none(self):
        spec = {"extract": {"val": {"path": "$.items[*].n", "reduce": "sum"}}}
        assert process(spec, {"items": []}) == {"val": None}

    def test_count_empty_returns_zero(self):
        spec = {"extract": {"n": {"path": "$.items[*].n", "reduce": "count"}}}
        assert process(spec, {"items": []}) == {"n": 0}


class TestReduceFirstLast:
    def test_first_returns_first_item(self, dated_items):
        spec = {"extract": {"first": {"path": "$.items[*].score", "reduce": "first"}}}
        assert process(spec, dated_items)["first"] == 42

    def test_last_returns_last_item(self, dated_items):
        spec = {"extract": {"last": {"path": "$.items[*].score", "reduce": "last"}}}
        assert process(spec, dated_items)["last"] == 99

    def test_first_empty_returns_none(self):
        spec = {"extract": {"val": {"path": "$.items[*].n", "reduce": "first"}}}
        assert process(spec, {"items": []}) == {"val": None}

    def test_last_empty_returns_none(self):
        spec = {"extract": {"val": {"path": "$.items[*].n", "reduce": "last"}}}
        assert process(spec, {"items": []}) == {"val": None}


class TestReduceDatetime:
    def test_min_datetime_normalises_across_timezones(self):
        data = {
            "events": [
                {"dt": "2026-04-11T10:00:00+05:30"},  # 04:30 UTC
                {"dt": "2026-04-11T01:00:00+00:00"},  # 01:00 UTC — earliest
                {"dt": "2026-04-11T12:00:00+04:00"},  # 08:00 UTC
            ]
        }
        spec = {"extract": {"earliest": {"path": "$.events[*].dt", "reduce": "min_datetime"}}}
        assert process(spec, data)["earliest"] == "2026-04-11T01:00:00+00:00"

    def test_max_datetime_normalises_across_timezones(self):
        data = {
            "events": [
                {"dt": "2026-04-11T10:00:00+05:30"},  # 04:30 UTC
                {"dt": "2026-04-11T01:00:00+00:00"},  # 01:00 UTC
                {"dt": "2026-04-11T12:00:00+04:00"},  # 08:00 UTC — latest
            ]
        }
        spec = {"extract": {"latest": {"path": "$.events[*].dt", "reduce": "max_datetime"}}}
        assert process(spec, data)["latest"] == "2026-04-11T12:00:00+04:00"

    def test_min_datetime_empty_returns_none(self):
        spec = {"extract": {"val": {"path": "$.items[*].dt", "reduce": "min_datetime"}}}
        assert process(spec, {"items": []}) == {"val": None}


class TestReduceConcat:
    def test_concat_default_separator(self):
        data = {"tags": [{"name": "alpha"}, {"name": "beta"}, {"name": "gamma"}]}
        spec = {"extract": {"tags": {"path": "$.tags[*].name", "reduce": "concat"}}}
        assert process(spec, data)["tags"] == "alpha, beta, gamma"

    def test_concat_custom_separator(self):
        data = {"tags": [{"name": "alpha"}, {"name": "beta"}, {"name": "gamma"}]}
        spec = {
            "extract": {
                "tags": {
                    "path": "$.tags[*].name",
                    "reduce": {"op": "concat", "sep": " | "},
                }
            }
        }
        assert process(spec, data)["tags"] == "alpha | beta | gamma"

    def test_concat_empty_returns_none(self):
        spec = {"extract": {"val": {"path": "$.items[*].n", "reduce": "concat"}}}
        assert process(spec, {"items": []}) == {"val": None}


class TestReduceDistinct:
    def test_distinct_deduplicates_preserving_order(self):
        data = {"items": [{"cat": "A"}, {"cat": "B"}, {"cat": "A"}, {"cat": "C"}, {"cat": "B"}]}
        spec = {"extract": {"cats": {"path": "$.items[*].cat", "reduce": "distinct"}}}
        assert process(spec, data)["cats"] == ["A", "B", "C"]

    def test_distinct_numeric(self):
        data = {"items": [{"v": 3}, {"v": 1}, {"v": 2}, {"v": 1}, {"v": 3}]}
        spec = {"extract": {"vals": {"path": "$.items[*].v", "reduce": "distinct"}}}
        assert process(spec, data)["vals"] == [3, 1, 2]

    def test_distinct_empty_returns_none(self):
        spec = {"extract": {"val": {"path": "$.items[*].n", "reduce": "distinct"}}}
        assert process(spec, {"items": []}) == {"val": None}


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
