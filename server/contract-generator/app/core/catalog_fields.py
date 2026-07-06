"""Loader for the catalog-field schema.

The schema (YAML) defines which catalog item attributes the Generator
embeds in the vc.credentialSubject.catalogItem[] entries of a contract.
It is loaded once at startup. Change the YAML (or its ConfigMap) and
restart pods to apply a new schema.

Tokens issued before a schema change are unaffected — Validators don't
care about fields they don't recognise.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class FieldDef(BaseModel):
    """Single field entry in the catalog-field schema."""

    name: str = Field(..., min_length=1, description="Name of the field in the token")
    source: str = Field(
        ..., min_length=1, description="Field name in the incoming request item"
    )
    required: bool = True


class CatalogFieldSchema(BaseModel):
    """The complete set of catalog fields the Generator emits per item."""

    fields: list[FieldDef] = Field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> "CatalogFieldSchema":
        """Load and validate the schema from a YAML file."""
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        schema = cls.model_validate(data)
        if not schema.fields:
            raise ValueError(
                f"catalog field schema at {path} contains no fields — "
                "at least one is required"
            )
        return schema

    def project(self, item: dict[str, Any]) -> dict[str, Any]:
        """Build the catalogItem entry for one item according to the schema.

        Raises KeyError if a required field is missing from `item`.
        Optional fields that are absent are simply omitted from the result.
        """
        out: dict[str, Any] = {}
        for field in self.fields:
            if field.source in item and item[field.source] is not None:
                out[field.name] = item[field.source]
            elif field.required:
                raise KeyError(
                    f"required field {field.source!r} missing from catalog item"
                )
        return out

    @property
    def required_source_fields(self) -> list[str]:
        """Names of all required source fields — used for request validation."""
        return [f.source for f in self.fields if f.required]
