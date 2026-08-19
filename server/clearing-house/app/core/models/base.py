"""Shared declarative base and the one engine-specific column type.

The storage engine is expected to move from SQLite to PostgreSQL without a
rewrite, so every type used in this package is chosen to behave identically
on both:

1. No date/time columns. Times are plain integers, seconds since the Unix
   epoch. SQLite has no date type; PostgreSQL has several, with timezone
   rules. Integers mean the same thing in both.

2. No JSON columns. PostgreSQL's JSONB reorders keys; SQLite has nothing
   equivalent.

3. No database-enforced value lists (enums). PostgreSQL needs a migration to
   add a value; SQLite has no enums at all. Such constraints live in Python,
   next to the column they apply to.

4. Auto-numbering needs a per-engine hint — see AUTO_PK.
"""

from sqlalchemy import BigInteger, Integer
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for every model in this package.

    Alembic reads Base.metadata to work out what to create — which only
    contains the tables whose modules have actually been imported. See
    app/core/models/__init__.py.
    """


# The one type that cannot be written once and work everywhere.
#
# SQLite only auto-assigns a value for a column declared exactly INTEGER; a
# BIGINT primary key is treated as an ordinary NOT NULL column and every
# insert fails with "NOT NULL constraint failed". PostgreSQL, meanwhile,
# wants BIGINT for a counter expected to run for years.
#
# Renders as:  sqlite -> INTEGER      postgresql -> BIGSERIAL
AUTO_PK = BigInteger().with_variant(Integer, "sqlite")
