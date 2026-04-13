"""Integration tests for DynamoDB resource fixtures against real LocalStack."""

from __future__ import annotations

from collections.abc import Callable


from samstack.resources.dynamodb import DynamoTable


class TestMakeDynamoTable:
    def test_creates_real_table(
        self, make_dynamodb_table: Callable[[str, dict[str, str]], DynamoTable]
    ) -> None:
        table = make_dynamodb_table("users", {"id": "S"})
        table.put_item({"id": "u1", "name": "Alice"})
        result = table.get_item({"id": "u1"})
        assert result is not None
        assert result["name"] == "Alice"

    def test_uuid_isolation(
        self, make_dynamodb_table: Callable[[str, dict[str, str]], DynamoTable]
    ) -> None:
        t1 = make_dynamodb_table("orders", {"id": "S"})
        t2 = make_dynamodb_table("orders", {"id": "S"})
        assert t1.name != t2.name

    def test_composite_key(
        self, make_dynamodb_table: Callable[[str, dict[str, str]], DynamoTable]
    ) -> None:
        table = make_dynamodb_table("events", {"pk": "S", "sk": "S"})
        table.put_item({"pk": "user#1", "sk": "event#1", "data": "x"})
        result = table.get_item({"pk": "user#1", "sk": "event#1"})
        assert result is not None
        assert result["data"] == "x"

    def test_get_item_not_found_returns_none(
        self, make_dynamodb_table: Callable[[str, dict[str, str]], DynamoTable]
    ) -> None:
        table = make_dynamodb_table("lookup", {"id": "S"})
        result = table.get_item({"id": "nonexistent"})
        assert result is None

    def test_scan(
        self, make_dynamodb_table: Callable[[str, dict[str, str]], DynamoTable]
    ) -> None:
        table = make_dynamodb_table("scan-test", {"id": "S"})
        table.put_item({"id": "a", "val": 1})
        table.put_item({"id": "b", "val": 2})
        items = table.scan()
        ids = {item["id"] for item in items}
        assert ids == {"a", "b"}

    def test_delete_item(
        self, make_dynamodb_table: Callable[[str, dict[str, str]], DynamoTable]
    ) -> None:
        table = make_dynamodb_table("delete-test", {"id": "S"})
        table.put_item({"id": "x"})
        table.delete_item({"id": "x"})
        assert table.get_item({"id": "x"}) is None


class TestDynamoTableFunctionScoped:
    def test_default_key_schema(self, dynamodb_table: DynamoTable) -> None:
        dynamodb_table.put_item({"id": "test-id", "value": "hello"})
        result = dynamodb_table.get_item({"id": "test-id"})
        assert result is not None
        assert result["value"] == "hello"

    def test_client_escape_hatch(self, dynamodb_table: DynamoTable) -> None:
        response = dynamodb_table.client.list_tables()
        assert dynamodb_table.name in response["TableNames"]
