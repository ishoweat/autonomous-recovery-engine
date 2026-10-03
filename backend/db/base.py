from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""

    __abstract__ = True

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"
