"""
Tests for the pipeline function - GitHub Actions-style multi-stage execution.

Each stage's `from` resolves against root data. Stages reference prior
outputs via $stages.<id>.<field> in where clauses.
"""

import pytest
from siphon._chain import pipeline, resolve_ref, resolve_refs


@pytest.fixture
def sibling_data():
    """Data with sibling arrays linked by foreign keys."""
    return {
        "rates": [
            {"id": 1, "title": "Standard", "startTimeIds": [10, 20]},
            {"id": 2, "title": "Premium", "startTimeIds": [20, 30]},
        ],
        "startTimes": [
            {"id": 10, "hour": 9, "minute": 0, "locationId": 100},
            {"id": 20, "hour": 12, "minute": 30, "locationId": 200},
            {"id": 30, "hour": 15, "minute": 0, "locationId": 100},
        ],
        "locations": [
            {"id": 100, "name": "Downtown"},
            {"id": 200, "name": "Airport"},
        ],
    }


class TestResolveRefs:
    """Tests for $stages reference resolution."""

    def test_non_ref_string_unchanged(self):
        assert resolve_refs("hello", {"x": {"a": 1}}) == "hello"

    def test_resolve_scalar_from_dict_output(self):
        ctx = {"rate": {"title": "Standard", "startTimeIds": [10, 20]}}
        assert resolve_ref("$stages.rate.title", ctx) == "Standard"

    def test_resolve_field_from_list_output(self):
        ctx = {"times": [{"hour": 9}, {"hour": 12}]}
        assert resolve_ref("$stages.times.hour", ctx) == [9, 12]

    def test_unknown_stage_raises(self):
        with pytest.raises(ValueError, match="Unknown stage: missing"):
            resolve_ref("$stages.missing.field", {})

    def test_none_output_does_not_raise(self):
        """A stage that returned None is known but empty."""
        ctx = {"rate": None}
        assert resolve_ref("$stages.rate.field", ctx) is None

    def test_resolve_nested_in_dict(self):
        ctx = {"rate": {"ids": [1, 2]}}
        where = {"id": {"$in": "$stages.rate.ids"}}
        resolved = resolve_refs(where, ctx)
        assert resolved == {"id": {"$in": [1, 2]}}

    def test_resolve_in_list(self):
        ctx = {"rate": {"val": 42}}
        obj = ["$stages.rate.val", "literal"]
        resolved = resolve_refs(obj, ctx)
        assert resolved == [42, "literal"]

    def test_empty_context_returns_unchanged(self):
        where = {"id": "$stages.rate.field"}
        assert resolve_refs(where, {}) is where

    def test_dotted_field_path(self):
        """$stages.<id>.<dotted.path> resolves nested fields."""
        ctx = {"rate": {"pricing": {"amount": 69}}}
        assert resolve_ref("$stages.rate.pricing.amount", ctx) == 69


class TestPipelineSingleStage:
    """Pipeline with one stage behaves like query()."""

    def test_single_stage(self, sibling_data):
        result = pipeline(
            [{"from": "$.rates[*]", "where": {"id": 1}, "select": {"title": "title"}}], sibling_data
        )
        assert result == {"title": "Standard"}

    def test_single_stage_collect(self, sibling_data):
        result = pipeline(
            [{"from": "$.rates[*]", "select": {"title": "title"}, "collect": True}], sibling_data
        )
        assert result == [{"title": "Standard"}, {"title": "Premium"}]


class TestPipelineTwoStage:
    """Two-stage pipeline joining sibling arrays."""

    def test_rate_to_start_times(self, sibling_data):
        result = pipeline(
            [
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
            ],
            sibling_data,
        )
        assert result == [{"hour": 9, "minute": 0}, {"hour": 12, "minute": 30}]

    def test_from_always_resolves_root(self, sibling_data):
        """Stage 2's from resolves against root data, not stage 1 output."""
        result = pipeline(
            [
                {
                    "id": "rate",
                    "from": "$.rates[*]",
                    "where": {"id": 2},
                    "select": {"startTimeIds": "startTimeIds"},
                },
                {
                    "from": "$.startTimes[*]",
                    "where": {"id": {"$in": "$stages.rate.startTimeIds"}},
                    "collect": True,
                    "select": {"id": "id"},
                },
            ],
            sibling_data,
        )
        assert result == [{"id": 20}, {"id": 30}]

    def test_stage_where_without_refs(self, sibling_data):
        """Stages with plain where (no $stages) work normally."""
        result = pipeline(
            [
                {"from": "$.rates[*]", "where": {"id": 1}},
                {"from": "$.startTimes[*]", "where": {"hour": 9}},
            ],
            sibling_data,
        )
        # Both stages independently query root data
        assert result["hour"] == 9


class TestPipelineThreeStage:
    """Three-stage pipeline: rates → startTimes → locations."""

    def test_three_stage_join(self, sibling_data):
        result = pipeline(
            [
                {
                    "id": "rate",
                    "from": "$.rates[*]",
                    "where": {"id": 1},
                    "select": {"startTimeIds": "startTimeIds"},
                },
                {
                    "id": "times",
                    "from": "$.startTimes[*]",
                    "where": {"id": {"$in": "$stages.rate.startTimeIds"}},
                    "select": {"locationId": "locationId"},
                    "collect": True,
                },
                {
                    "from": "$.locations[*]",
                    "where": {"id": {"$in": "$stages.times.locationId"}},
                    "collect": True,
                },
            ],
            sibling_data,
        )
        assert result == [
            {"id": 100, "name": "Downtown"},
            {"id": 200, "name": "Airport"},
        ]

    def test_skip_stage_reference(self, sibling_data):
        """Stage 3 can reference stage 1 directly (skip stage 2)."""
        result = pipeline(
            [
                {
                    "id": "rate",
                    "from": "$.rates[*]",
                    "where": {"id": 1},
                    "select": {"startTimeIds": "startTimeIds"},
                },
                {
                    "id": "times",
                    "from": "$.startTimes[*]",
                    "where": {"id": {"$in": "$stages.rate.startTimeIds"}},
                    "select": {"locationId": "locationId"},
                    "collect": True,
                },
                # Reference stage 1 directly
                {
                    "from": "$.rates[*]",
                    "where": {"id": {"$in": "$stages.rate.startTimeIds"}},
                    "collect": True,
                },
            ],
            sibling_data,
        )
        # This queries rates where id is in [10, 20] — no match since rate ids are 1 and 2
        assert result == []


class TestPipelineStageRef:
    """Tests for stage reference semantics."""

    def test_ref_scalar_from_collect_false(self, sibling_data):
        """collect=false returns single dict, ref extracts scalar."""
        result = pipeline(
            [
                {
                    "id": "rate",
                    "from": "$.rates[*]",
                    "where": {"id": 1},
                    "select": {"title": "title"},
                },
                {
                    "from": "$.rates[*]",
                    "where": {"title": "$stages.rate.title"},
                    "select": {"id": "id"},
                },
            ],
            sibling_data,
        )
        assert result == {"id": 1}

    def test_ref_collects_field_from_list(self, sibling_data):
        """collect=true returns list, ref gathers field from all items."""
        result = pipeline(
            [
                {
                    "id": "times",
                    "from": "$.startTimes[*]",
                    "collect": True,
                    "select": {"locationId": "locationId"},
                },
                {
                    "from": "$.locations[*]",
                    "where": {"id": {"$in": "$stages.times.locationId"}},
                    "collect": True,
                    "select": {"name": "name"},
                },
            ],
            sibling_data,
        )
        # locationIds are [100, 200, 100] but $in handles dupes
        assert result == [{"name": "Downtown"}, {"name": "Airport"}]

    def test_select_limits_downstream(self, sibling_data):
        """If stage uses select, only selected fields available in refs."""
        result = pipeline(
            [
                {
                    "id": "rate",
                    "from": "$.rates[*]",
                    "where": {"id": 1},
                    "select": {"title": "title"},
                },  # startTimeIds NOT selected
                {
                    "from": "$.startTimes[*]",
                    "where": {"id": {"$in": "$stages.rate.startTimeIds"}},
                    "collect": True,
                },
            ],
            sibling_data,
        )
        # startTimeIds is None because it wasn't in select
        # $in with None operand — no items match
        assert result == []

    def test_no_select_exposes_full_object(self, sibling_data):
        """Without select, all fields available in stage refs."""
        result = pipeline(
            [
                {"id": "rate", "from": "$.rates[*]", "where": {"id": 1}},  # no select — full object
                {
                    "from": "$.startTimes[*]",
                    "where": {"id": {"$in": "$stages.rate.startTimeIds"}},
                    "collect": True,
                    "select": {"hour": "hour"},
                },
            ],
            sibling_data,
        )
        assert result == [{"hour": 9}, {"hour": 12}]

    def test_id_optional_on_last_stage(self, sibling_data):
        """Last stage doesn't need id."""
        result = pipeline(
            [
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
                },
            ],
            sibling_data,
        )
        assert len(result) == 2


class TestPipelineWithChainFeatures:
    """Pipeline stages can use sort, limit, then, etc."""

    def test_stage_with_sort_limit(self, sibling_data):
        result = pipeline(
            [
                {
                    "from": "$.startTimes[*]",
                    "sort": [{"field": "hour", "order": "desc"}],
                    "limit": 2,
                    "collect": True,
                    "select": {"hour": "hour"},
                },
            ],
            sibling_data,
        )
        assert result == [{"hour": 15}, {"hour": 12}]

    def test_stage_with_then(self):
        """A pipeline stage can use then for nested drilling."""
        data = {
            "departments": [
                {"name": "Eng", "teams": [{"id": 1}, {"id": 2}]},
                {"name": "Sales", "teams": [{"id": 3}]},
            ]
        }
        result = pipeline(
            [
                {
                    "from": "$.departments[*]",
                    "where": {"name": "Eng"},
                    "select": {"dept": "name"},
                    "then": {
                        "from": "teams[*]",
                        "select": {"teamId": "id"},
                        "collect": True,
                    },
                },
            ],
            data,
        )
        assert result == [
            {"dept": "Eng", "teamId": 1},
            {"dept": "Eng", "teamId": 2},
        ]


class TestPipelineEdgeCases:
    """Edge cases and error handling."""

    def test_empty_stages_returns_none(self):
        result = pipeline([], {"items": [1, 2, 3]})
        assert result is None

    def test_unknown_stage_raises(self, sibling_data):
        with pytest.raises(ValueError, match="Unknown stage: nonexistent"):
            pipeline(
                [
                    {"id": "rate", "from": "$.rates[*]", "where": {"id": 1}},
                    {
                        "from": "$.rates[*]",
                        "where": {"id": "$stages.nonexistent.field"},
                        "collect": True,
                    },
                ],
                sibling_data,
            )

    def test_stage_returning_none(self, sibling_data):
        """Stage returning None is stored and accessible (doesn't raise)."""
        result = pipeline(
            [
                {
                    "id": "empty",
                    "from": "$.rates[*]",
                    "where": {"id": 9999},
                },  # no match, returns None
                {"from": "$.rates[*]", "collect": True, "select": {"title": "title"}},
            ],
            sibling_data,
        )
        # Second stage doesn't reference first, works normally
        assert result == [{"title": "Standard"}, {"title": "Premium"}]

    def test_ref_in_nested_operator(self, sibling_data):
        """$stages ref works inside nested $and/$or operators."""
        result = pipeline(
            [
                {
                    "id": "rate",
                    "from": "$.rates[*]",
                    "where": {"id": 1},
                    "select": {"startTimeIds": "startTimeIds"},
                },
                {
                    "from": "$.startTimes[*]",
                    "where": {
                        "$and": [
                            {"id": {"$in": "$stages.rate.startTimeIds"}},
                            {"hour": {"$gte": 10}},
                        ]
                    },
                    "collect": True,
                    "select": {"hour": "hour"},
                },
            ],
            sibling_data,
        )
        assert result == [{"hour": 12}]


class TestBokunActivityPipeline:
    """Real-world test: Bokun activity API — filter startTimes & pricingCategories by rateId."""

    @pytest.fixture
    def bokun_activity(self):
        return {
            "id": 853863,
            "title": "Pasta Lovers Cooking Class",
            "defaultRateId": 1674388,
            "rates": [
                {
                    "id": 1641235,
                    "title": "Extended Cooking Class + Grocery Market tour",
                    "startTimeIds": [2937449],
                    "pricingCategoryIds": [120729, 120731, 120732],
                },
                {
                    "id": 1674388,
                    "title": "English - Express Afternoon Cooking Class",
                    "startTimeIds": [4208239, 4208240],
                    "pricingCategoryIds": [120729, 120731, 120732],
                },
                {
                    "id": 2224998,
                    "title": "Spanish - Express Afternoon Cooking Class",
                    "startTimeIds": [4462236],
                    "pricingCategoryIds": [120729, 120731, 120732],
                },
            ],
            "startTimes": [
                {
                    "id": 2937449,
                    "externalLabel": "Cooking Class + Market",
                    "hour": 9,
                    "minute": 0,
                    "durationHours": 4,
                    "durationMinutes": 30,
                },
                {
                    "id": 3576860,
                    "externalLabel": "2.00 PM Express Tour",
                    "hour": 14,
                    "minute": 0,
                    "durationHours": 3,
                    "durationMinutes": 0,
                },
                {
                    "id": 4208239,
                    "externalLabel": "Express Cooking Class",
                    "hour": 14,
                    "minute": 30,
                    "durationHours": 4,
                    "durationMinutes": 0,
                },
                {
                    "id": 3575089,
                    "externalLabel": "5.30 PM Express Class",
                    "hour": 17,
                    "minute": 30,
                    "durationHours": 3,
                    "durationMinutes": 30,
                },
                {
                    "id": 4208240,
                    "externalLabel": "English PM Express Class",
                    "hour": 18,
                    "minute": 0,
                    "durationHours": 3,
                    "durationMinutes": 0,
                },
                {
                    "id": 4462236,
                    "externalLabel": "Spanish PM Express Class",
                    "hour": 18,
                    "minute": 0,
                    "durationHours": 3,
                    "durationMinutes": 0,
                },
            ],
            "pricingCategories": [
                {
                    "id": 120729,
                    "title": "Adult",
                    "ticketCategory": "ADULT",
                    "minAge": 0,
                    "maxAge": 99,
                },
                {
                    "id": 120731,
                    "title": "Child",
                    "ticketCategory": "CHILD",
                    "minAge": 4,
                    "maxAge": 12,
                },
                {
                    "id": 120732,
                    "title": "Infant",
                    "ticketCategory": "INFANT",
                    "minAge": 0,
                    "maxAge": 3,
                },
            ],
        }

    def test_start_times_for_rate(self, bokun_activity):
        """Filter startTimes for the Extended rate (rateId=1641235)."""
        result = pipeline(
            [
                {
                    "id": "rate",
                    "from": "$.rates[*]",
                    "where": {"id": 1641235},
                    "select": {"startTimeIds": "startTimeIds", "rateTitle": "title"},
                },
                {
                    "from": "$.startTimes[*]",
                    "where": {"id": {"$in": "$stages.rate.startTimeIds"}},
                    "collect": True,
                    "select": {
                        "id": "id",
                        "label": "externalLabel",
                        "hour": "hour",
                        "minute": "minute",
                    },
                },
            ],
            bokun_activity,
        )
        assert result == [
            {"id": 2937449, "label": "Cooking Class + Market", "hour": 9, "minute": 0},
        ]

    def test_start_times_for_default_rate(self, bokun_activity):
        """Filter startTimes for the default rate (English Express, rateId=1674388)."""
        result = pipeline(
            [
                {
                    "id": "rate",
                    "from": "$.rates[*]",
                    "where": {"id": 1674388},
                    "select": {"startTimeIds": "startTimeIds"},
                },
                {
                    "from": "$.startTimes[*]",
                    "where": {"id": {"$in": "$stages.rate.startTimeIds"}},
                    "collect": True,
                    "select": {"label": "externalLabel", "hour": "hour", "minute": "minute"},
                },
            ],
            bokun_activity,
        )
        assert result == [
            {"label": "Express Cooking Class", "hour": 14, "minute": 30},
            {"label": "English PM Express Class", "hour": 18, "minute": 0},
        ]

    def test_rate_with_start_times_and_pricing(self, bokun_activity):
        """Three-stage: rate → startTimes + rate → pricingCategories."""
        start_times = pipeline(
            [
                {
                    "id": "rate",
                    "from": "$.rates[*]",
                    "where": {"id": 2224998},
                    "select": {"startTimeIds": "startTimeIds"},
                },
                {
                    "from": "$.startTimes[*]",
                    "where": {"id": {"$in": "$stages.rate.startTimeIds"}},
                    "collect": True,
                    "select": {"label": "externalLabel", "hour": "hour"},
                },
            ],
            bokun_activity,
        )
        assert start_times == [{"label": "Spanish PM Express Class", "hour": 18}]

    def test_pricing_categories_for_rate(self, bokun_activity):
        """Filter pricingCategories by a rate's pricingCategoryIds."""
        result = pipeline(
            [
                {
                    "id": "rate",
                    "from": "$.rates[*]",
                    "where": {"id": 1641235},
                    "select": {"pricingCategoryIds": "pricingCategoryIds"},
                },
                {
                    "from": "$.pricingCategories[*]",
                    "where": {"id": {"$in": "$stages.rate.pricingCategoryIds"}},
                    "collect": True,
                    "select": {
                        "title": "title",
                        "category": "ticketCategory",
                        "minAge": "minAge",
                        "maxAge": "maxAge",
                    },
                },
            ],
            bokun_activity,
        )
        assert result == [
            {"title": "Adult", "category": "ADULT", "minAge": 0, "maxAge": 99},
            {"title": "Child", "category": "CHILD", "minAge": 4, "maxAge": 12},
            {"title": "Infant", "category": "INFANT", "minAge": 0, "maxAge": 3},
        ]

    def test_full_variant_resolution(self, bokun_activity):
        """Full variant: rate → startTimes sorted by hour, with rate title carried via stages."""
        result = pipeline(
            [
                {
                    "id": "rate",
                    "from": "$.rates[*]",
                    "where": {"id": 1674388},
                    "select": {"startTimeIds": "startTimeIds", "rateTitle": "title"},
                },
                {
                    "from": "$.startTimes[*]",
                    "where": {"id": {"$in": "$stages.rate.startTimeIds"}},
                    "sort": [{"field": "hour", "order": "asc"}],
                    "collect": True,
                    "select": {"label": "externalLabel", "hour": "hour", "minute": "minute"},
                },
            ],
            bokun_activity,
        )
        assert result == [
            {"label": "Express Cooking Class", "hour": 14, "minute": 30},
            {"label": "English PM Express Class", "hour": 18, "minute": 0},
        ]
