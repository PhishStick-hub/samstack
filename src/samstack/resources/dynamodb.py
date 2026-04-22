from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mypy_boto3_dynamodb import DynamoDBClient
    from mypy_boto3_dynamodb.service_resource import Table


class DynamoTable:
    """
    Thin wrapper around a DynamoDB table resource for use in pytest fixtures.

    Uses the high-level boto3 resource API so item values are plain Python
    types (str, int, list, dict) — not the low-level ``{"S": "val"}`` format.

    The underlying boto3 resource is exposed via the ``table`` property, and
    the low-level DynamoDB client is available via the ``client`` property.
    """

    def __init__(self, name: str, table: Table) -> None:
        self._name = name
        self._table = table

    @property
    def name(self) -> str:
        return self._name

    @property
    def table(self) -> Table:
        """The underlying boto3 DynamoDB Table resource."""
        return self._table

    @property
    def client(self) -> DynamoDBClient:
        """The underlying low-level DynamoDB client for advanced operations."""
        client: DynamoDBClient = self._table.meta.client
        return client

    def put_item(self, item: dict[str, Any]) -> None:
        """Write an item to the table using plain Python values."""
        self._table.put_item(Item=item)

    def get_item(self, key: dict[str, Any]) -> dict[str, Any] | None:
        """Fetch an item by key. Returns None if the item does not exist."""
        resp = self._table.get_item(Key=key)
        return resp.get("Item")

    def delete_item(self, key: dict[str, Any]) -> None:
        """Delete an item by key."""
        self._table.delete_item(Key=key)

    def query(
        self,
        key_condition: str,
        values: dict[str, Any],
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """
        Query items by key condition expression. Paginates through all matching items.

        Args:
            key_condition: KeyConditionExpression string, e.g. ``"pk = :pk"``
            values: ExpressionAttributeValues dict, e.g. ``{":pk": "val"}``
            **kwargs: Extra args forwarded to boto3 (e.g. ``IndexName``)
        """
        items: list[dict[str, Any]] = []
        resp = self._table.query(
            KeyConditionExpression=key_condition,
            ExpressionAttributeValues=values,
            **kwargs,
        )
        items.extend(resp["Items"])
        while "LastEvaluatedKey" in resp:
            resp = self._table.query(
                KeyConditionExpression=key_condition,
                ExpressionAttributeValues=values,
                ExclusiveStartKey=resp["LastEvaluatedKey"],
                **kwargs,
            )
            items.extend(resp["Items"])
        return items

    def scan(self, **kwargs: Any) -> list[dict[str, Any]]:
        """Scan all items (paginates through all pages), with optional filter kwargs forwarded to boto3."""
        items: list[dict[str, Any]] = []
        resp = self._table.scan(**kwargs)
        items.extend(resp["Items"])
        while "LastEvaluatedKey" in resp:
            resp = self._table.scan(
                ExclusiveStartKey=resp["LastEvaluatedKey"], **kwargs
            )
            items.extend(resp["Items"])
        return items
