from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, create_autospec

import pytest
from mypy_boto3_dynamodb.service_resource import Table

from samstack.resources.dynamodb import DynamoTable


@pytest.fixture
def mock_table() -> (
    MagicMock
):  # autospec of Table; typed as MagicMock for ty compatibility
    return create_autospec(Table, instance=True)


@pytest.fixture
def table(mock_table: MagicMock) -> DynamoTable:
    return DynamoTable(name="test-table", table=mock_table)


class TestDynamoTablePutItem:
    def test_put_item_calls_table(
        self, table: DynamoTable, mock_table: MagicMock
    ) -> None:
        item: dict[str, Any] = {"id": "abc", "value": 42}
        table.put_item(item)
        mock_table.put_item.assert_called_once_with(Item=item)


class TestDynamoTableGetItem:
    def test_get_item_returns_item(
        self, table: DynamoTable, mock_table: MagicMock
    ) -> None:
        expected: dict[str, Any] = {"id": "abc", "value": 42}
        mock_table.get_item.return_value = {"Item": expected}

        result = table.get_item({"id": "abc"})

        assert result == expected
        mock_table.get_item.assert_called_once_with(Key={"id": "abc"})

    def test_get_item_returns_none_when_missing(
        self, table: DynamoTable, mock_table: MagicMock
    ) -> None:
        mock_table.get_item.return_value = {}

        result = table.get_item({"id": "missing"})

        assert result is None


class TestDynamoTableDeleteItem:
    def test_delete_item_calls_table(
        self, table: DynamoTable, mock_table: MagicMock
    ) -> None:
        table.delete_item({"id": "abc"})
        mock_table.delete_item.assert_called_once_with(Key={"id": "abc"})


class TestDynamoTableQuery:
    def test_query_returns_items(
        self, table: DynamoTable, mock_table: MagicMock
    ) -> None:
        items: list[dict[str, Any]] = [{"id": "a"}, {"id": "b"}]
        mock_table.query.return_value = {"Items": items}

        result = table.query("id = :id", {":id": "a"})

        assert result == items
        mock_table.query.assert_called_once_with(
            KeyConditionExpression="id = :id",
            ExpressionAttributeValues={":id": "a"},
        )

    def test_query_forwards_kwargs(
        self, table: DynamoTable, mock_table: MagicMock
    ) -> None:
        mock_table.query.return_value = {"Items": []}

        table.query("pk = :pk", {":pk": "x"}, IndexName="gsi1")

        mock_table.query.assert_called_once_with(
            KeyConditionExpression="pk = :pk",
            ExpressionAttributeValues={":pk": "x"},
            IndexName="gsi1",
        )


class TestDynamoTableScan:
    def test_scan_returns_items(
        self, table: DynamoTable, mock_table: MagicMock
    ) -> None:
        items: list[dict[str, Any]] = [{"id": "x"}]
        mock_table.scan.return_value = {"Items": items}

        result = table.scan()

        assert result == items
        mock_table.scan.assert_called_once_with()

    def test_scan_forwards_kwargs(
        self, table: DynamoTable, mock_table: MagicMock
    ) -> None:
        mock_table.scan.return_value = {"Items": []}

        table.scan(FilterExpression="attr = :val")

        mock_table.scan.assert_called_once_with(FilterExpression="attr = :val")


class TestDynamoTableProperties:
    def test_name_property(self, table: DynamoTable) -> None:
        assert table.name == "test-table"

    def test_table_property(self, table: DynamoTable, mock_table: MagicMock) -> None:
        assert table.table is mock_table

    def test_client_property(self, table: DynamoTable, mock_table: MagicMock) -> None:
        mock_client = MagicMock()
        mock_table.meta.client = mock_client
        assert table.client is mock_client
