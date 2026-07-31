from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

ModelT = TypeVar("ModelT")


class BaseRepository(Generic[ModelT]):
    def __init__(self, db: Session, model: type[ModelT]):
        self.db = db
        self.model = model

    def get(self, object_id: int | str) -> ModelT | None:
        return self.db.get(self.model, object_id)

    def add(self, obj: ModelT) -> ModelT:
        self.db.add(obj)
        self.db.flush()
        return obj

    def delete(self, obj: ModelT) -> None:
        self.db.delete(obj)
        self.db.flush()

    def all(self, limit: int = 200) -> list[ModelT]:
        return list(self.db.scalars(select(self.model).limit(limit)).all())
