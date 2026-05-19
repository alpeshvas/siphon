import pytest
from pydantic import ValidationError
from siphon.typed import ExtractSpec, FieldSpec, RequestSpec, process_spec


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


class TestFieldSpec:
    def test_minimal_field_spec(self):
        spec = FieldSpec(path="$.data.id")
        assert spec.path == "$.data.id"
        assert spec.where is None
        assert spec.select is None
        assert spec.collect is False

    def test_full_field_spec(self):
        spec = FieldSpec(
            path="$.data.items[*]",
            where={"status": "active"},
            select={"item_id": "id"},
            collect=True,
        )
        assert spec.path == "$.data.items[*]"
        assert spec.where == {"status": "active"}
        assert spec.select == {"item_id": "id"}
        assert spec.collect is True

    def test_reduce_defaults_to_none(self):
        spec = FieldSpec(path="$.data.items[*].price")
        assert spec.reduce is None

    def test_reduce_string_operator(self):
        spec = FieldSpec(path="$.data.items[*].price", reduce="min_int")
        assert spec.reduce == "min_int"

    def test_reduce_dict_form(self):
        spec = FieldSpec(
            path="$.tags[*].name",
            reduce={"op": "concat", "sep": " | "},
        )
        assert spec.reduce == {"op": "concat", "sep": " | "}

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            FieldSpec(path="$.data.id", unknown_field="value")


class TestExtractSpec:
    def test_with_string_paths(self):
        spec = ExtractSpec(extract={"id": "$.data.id", "name": "$.data.name"})
        assert spec.extract["id"] == "$.data.id"

    def test_with_field_spec(self):
        spec = ExtractSpec(
            extract={
                "items": FieldSpec(path="$.data.items[*]", collect=True),
            }
        )
        assert isinstance(spec.extract["items"], FieldSpec)

    def test_mixed_string_and_field_spec(self):
        spec = ExtractSpec(
            extract={
                "id": "$.data.id",
                "items": FieldSpec(path="$.data.items[*]", collect=True),
            }
        )
        assert spec.extract["id"] == "$.data.id"
        assert isinstance(spec.extract["items"], FieldSpec)

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            ExtractSpec(extract={"id": "$.data.id"}, unknown="value")


class TestRequestSpec:
    def test_creates_request_spec(self):
        spec = RequestSpec(path="/api/users")
        assert spec.path == "/api/users"

    def test_extract_spec_with_request(self):
        spec = ExtractSpec(
            extract={"id": "$.data.id"},
            request=RequestSpec(path="/api/data"),
        )
        assert spec.request.path == "/api/data"


class TestProcessSpec:
    def test_simple_path(self, sample_data):
        spec = ExtractSpec(extract={"id": "$.data.id"})
        assert process_spec(spec, sample_data) == {"id": "prod_123"}

    def test_with_field_spec(self, sample_data):
        spec = ExtractSpec(
            extract={
                "first": FieldSpec(path="$.data.items[*].name"),
            }
        )
        assert process_spec(spec, sample_data) == {"first": "Widget"}

    def test_with_where(self, sample_data):
        spec = ExtractSpec(
            extract={
                "inactive": FieldSpec(
                    path="$.data.items[*]",
                    where={"status": "inactive"},
                    select={"name": "name"},
                ),
            }
        )
        assert process_spec(spec, sample_data) == {"inactive": {"name": "Gadget"}}

    def test_with_collect(self, sample_data):
        spec = ExtractSpec(
            extract={
                "all_names": FieldSpec(
                    path="$.data.items[*].name",
                    collect=True,
                ),
            }
        )
        assert process_spec(spec, sample_data) == {"all_names": ["Widget", "Gadget", "Thing"]}

    def test_combined(self, sample_data):
        spec = ExtractSpec(
            extract={
                "id": "$.data.id",
                "first_active": FieldSpec(
                    path="$.data.items[*]",
                    where={"status": "active"},
                    select={"item_id": "id", "item_name": "name"},
                ),
                "all_active": FieldSpec(
                    path="$.data.items[*]",
                    where={"status": "active"},
                    select={"item_id": "id", "item_name": "name"},
                    collect=True,
                ),
            }
        )
        result = process_spec(spec, sample_data)
        assert result["id"] == "prod_123"
        assert result["first_active"] == {"item_id": 1, "item_name": "Widget"}
        assert result["all_active"] == [
            {"item_id": 1, "item_name": "Widget"},
            {"item_id": 3, "item_name": "Thing"},
        ]


class TestProcessSpecReduce:
    @pytest.fixture
    def scored_data(self):
        return {
            "items": [
                {"score": 42, "tag": "alpha", "created": "2026-03-15T10:00:00+00:00"},
                {"score": 7, "tag": "beta", "created": "2026-01-01T23:59:00+00:00"},
                {"score": 99, "tag": "alpha", "created": "2026-06-30T08:00:00+00:00"},
            ]
        }

    def test_reduce_sum(self, scored_data):
        spec = ExtractSpec(extract={"total": FieldSpec(path="$.items[*].score", reduce="sum")})
        assert process_spec(spec, scored_data) == {"total": 148}

    def test_reduce_max_int(self, scored_data):
        spec = ExtractSpec(extract={"top": FieldSpec(path="$.items[*].score", reduce="max_int")})
        assert process_spec(spec, scored_data) == {"top": 99}

    def test_reduce_min_date(self, scored_data):
        spec = ExtractSpec(
            extract={"oldest": FieldSpec(path="$.items[*].created", reduce="min_date")}
        )
        assert process_spec(spec, scored_data)["oldest"] == "2026-01-01T23:59:00+00:00"

    def test_reduce_distinct(self, scored_data):
        spec = ExtractSpec(extract={"tags": FieldSpec(path="$.items[*].tag", reduce="distinct")})
        assert process_spec(spec, scored_data) == {"tags": ["alpha", "beta"]}

    def test_reduce_concat_dict_form(self, scored_data):
        spec = ExtractSpec(
            extract={
                "tag_str": FieldSpec(
                    path="$.items[*].tag",
                    reduce={"op": "concat", "sep": " | "},
                )
            }
        )
        assert process_spec(spec, scored_data) == {"tag_str": "alpha | beta | alpha"}

    def test_reduce_count_empty(self):
        spec = ExtractSpec(extract={"n": FieldSpec(path="$.items[*].x", reduce="count")})
        assert process_spec(spec, {"items": []}) == {"n": 0}


class TestModelDump:
    def test_field_spec_dumps_correctly(self):
        spec = FieldSpec(
            path="$.data.items[*]",
            where={"status": "active"},
            collect=True,
        )
        dumped = spec.model_dump(exclude_none=True)
        assert dumped == {
            "path": "$.data.items[*]",
            "where": {"status": "active"},
            "collect": True,
        }
        assert "select" not in dumped

    def test_field_spec_dumps_reduce_string(self):
        spec = FieldSpec(path="$.items[*].price", reduce="sum")
        dumped = spec.model_dump(exclude_none=True)
        assert dumped == {"path": "$.items[*].price", "collect": False, "reduce": "sum"}

    def test_field_spec_dumps_reduce_dict(self):
        spec = FieldSpec(path="$.tags[*].name", reduce={"op": "concat", "sep": " | "})
        dumped = spec.model_dump(exclude_none=True)
        assert dumped["reduce"] == {"op": "concat", "sep": " | "}

    def test_field_spec_omits_reduce_when_none(self):
        spec = FieldSpec(path="$.data.id")
        dumped = spec.model_dump(exclude_none=True)
        assert "reduce" not in dumped

    def test_extract_spec_dumps_correctly(self):
        spec = ExtractSpec(
            extract={
                "id": "$.data.id",
                "items": FieldSpec(path="$.data.items[*]", collect=True),
            }
        )
        dumped = spec.model_dump(exclude_none=True)
        assert dumped["extract"]["id"] == "$.data.id"
        assert dumped["extract"]["items"]["path"] == "$.data.items[*]"


class TestFieldSpecCoalesce:
    def test_select_accepts_pipe_string(self):
        spec = FieldSpec(
            path="$.items[*]",
            select={"v": "a || b"},
            collect=True,
        )
        assert spec.select == {"v": "a || b"}

    def test_process_spec_coalesces(self):
        data = {"items": [{"a": None, "b": "fallback"}]}
        spec = ExtractSpec(
            extract={
                "out": FieldSpec(
                    path="$.items[*]",
                    select={"v": "a || b"},
                )
            }
        )
        assert process_spec(spec, data) == {"out": {"v": "fallback"}}

    def test_select_dump_preserves_pipe_string(self):
        spec = FieldSpec(path="$.items[*]", select={"v": "a || b"})
        dumped = spec.model_dump(exclude_none=True)
        assert dumped["select"] == {"v": "a || b"}
