"""Lightweight response wrappers."""

from typing import Any


def success_response(data: Any, message: str = "OK") -> dict:
    return {"success": True, "message": message, "data": data}


def error_response(code: str, message: str, details: list | None = None) -> dict:
    return {
        "success": False,
        "error": {"code": code, "message": message, "details": details or []},
    }
