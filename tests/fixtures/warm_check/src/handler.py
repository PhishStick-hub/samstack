from __future__ import annotations

import json
from uuid import uuid4

INSTANCE_ID = uuid4().hex


def handler(event: dict, context: object) -> dict:
    http_method = event.get("httpMethod", "")
    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "instance_id": INSTANCE_ID,
                "method": http_method or "INVOKE",
            }
        ),
    }
