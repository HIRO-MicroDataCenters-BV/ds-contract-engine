"""Cursor encoding for paged endpoints.

A cursor is a storage position — (registered_at, jti) for contracts — packed
into a string a client can hand back without understanding it.

Opaque for evolution, not for secrecy. It is base64 of JSON, and anyone can
decode it. What opacity buys is freedom: clients cannot construct cursors, so
the sort key can change later without breaking them. Tampering with one is
harmless — it moves the starting point, but every filter still applies, so it
cannot reveal a row the same filters would not.
"""

import base64
import binascii
import json

from app.core.repository import ContractPosition


class InvalidCursor(ValueError):
    """A cursor that did not come from this service, or has been damaged."""


def encode_cursor(position: ContractPosition) -> str:
    registered_at, jti = position
    raw = json.dumps([registered_at, jti], separators=(",", ":")).encode()
    # urlsafe and unpadded: it travels in a query string, where "+", "/" and
    # "=" would each need escaping.
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> ContractPosition:
    """The position a cursor encodes. Raises InvalidCursor on anything else.

    Strict on purpose. A malformed cursor must become a 400 at the edge; let
    it through and it becomes a type error deep in a query, and a 500.
    """
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded.encode()))
    except (binascii.Error, UnicodeDecodeError, ValueError) as e:
        raise InvalidCursor("cursor is not valid") from e

    if not isinstance(value, list) or len(value) != 2:
        raise InvalidCursor("cursor is not valid")

    registered_at, jti = value
    # `type(...) is int`, not isinstance: bool is a subclass of int in
    # Python, and [true, "x"] must not decode as position (1, "x").
    if type(registered_at) is not int or not isinstance(jti, str) or not jti:
        raise InvalidCursor("cursor is not valid")

    return registered_at, jti
