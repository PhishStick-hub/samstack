"""Mock Lambda support for samstack.

Two public surfaces:

1. :func:`spy_handler` — import inside a Lambda container to turn it into a
   call-recording mock::

       from samstack.mock import spy_handler as handler

2. :class:`LambdaMock` + :func:`make_lambda_mock` — pytest fixture and
   companion wrapper used from the test side to inspect captured calls and
   queue canned responses.
"""

from __future__ import annotations

from samstack.mock.fixture import LambdaMock, make_lambda_mock
from samstack.mock.handler import spy_handler
from samstack.mock.types import Call, CallList

__all__ = [
    "Call",
    "CallList",
    "LambdaMock",
    "make_lambda_mock",
    "spy_handler",
]
