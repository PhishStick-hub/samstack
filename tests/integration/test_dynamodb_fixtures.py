"""Integration tests for DynamoDB resource fixtures against real LocalStack."""

from __future__ import annotations

from collections.abc import Callable


from samstack.resources.dynamodb import DynamoTable


class TestDynamoTableFactory:
    def test_factory_creates_real_table(
        self, dynamodb_table_factory: Callable[[str, dict[str, str]], DynamoTable]
    ) -> None:
        table = dynamodb_table_factory("users", {"id": "S"})
        table.put_item({"id": "u1", "name": "Alice"})
        result = table.get_item({"id": "u1"})
        assert result is not None
        assert result["name"] == "Alice"

    def test_factory_uuid_isolation(
        self, dynamodb_table_factory: Callable[[str, dict[str, str]], DynamoTable]
    ) -> None:
        t1 = dynamodb_table_factory("orders", {"id": "S"})
        t2 = dynamodb_table_factory("orders", {"id": "S"})
        assert t1.name != t2.name

    def test_factory_composite_key(
        self, dynamodb_table_factory: Callable[[str, dict[str, str]], DynamoTable]
    ) -> None:
        table = dynamodb_table_factory("events", {"pk": "S", "sk": "S"})
        table.put_item({"pk": "user#1", "sk": "event#1", "data": "x"})
        result = table.get_item({"pk": "user#1", "sk": "event#1"})
        assert result is not None
        assert result["data"] == "x"

    def test_factory_get_item_not_found_returns_none(
        self, dynamodb_table_factory: Callable[[str, dict[str, str]], DynamoTable]
    ) -> None:
        table = dynamodb_table_factory("lookup", {"id": "S"})
        result = table.get_item({"id": "nonexistent"})
        assert result is None

    def test_factory_scan(
        self, dynamodb_table_factory: Callable[[str, dict[str, str]], DynamoTable]
    ) -> None:
        table = dynamodb_table_factory("scan-test", {"id": "S"})
        table.put_item({"id": "a", "val": 1})
        table.put_item({"id": "b", "val": 2})
        items = table.scan()
        ids = {item["id"] for item in items}
        assert ids == {"a", "b"}

    def test_factory_delete_item(
        self, dynamodb_table_factory: Callable[[str, dict[str, str]], DynamoTable]
    ) -> None:
        table = dynamodb_table_factory("delete-test", {"id": "S"})
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
