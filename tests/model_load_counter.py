"""Conta objetos ORM efetivamente materializados durante um request."""

from collections import Counter

from sqlalchemy import event
from sqlalchemy.orm import Session


class ModelLoadCounter:
    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()

    def loaded(self, _session: Session, instance: object) -> None:
        self.counts[type(instance).__name__] += 1

    def __enter__(self) -> "ModelLoadCounter":
        event.listen(Session, "loaded_as_persistent", self.loaded)
        return self

    def __exit__(self, *_exc: object) -> None:
        event.remove(Session, "loaded_as_persistent", self.loaded)
