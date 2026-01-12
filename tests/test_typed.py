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
