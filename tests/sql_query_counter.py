"""Contador de statements SQL compartilhado pelos testes de custo de query."""

from sqlalchemy import event


class SqlQueryCounter:
    """Conta statements executados no engine — guarda-corpo do N+1."""

    def __init__(self, engine) -> None:
        self.engine = engine
        self.total = 0

    def _on_execute(self, *_args) -> None:
        self.total += 1

    def __enter__(self) -> "SqlQueryCounter":
        event.listen(self.engine, "before_cursor_execute", self._on_execute)
        return self

    def __exit__(self, *_exc) -> None:
        event.remove(self.engine, "before_cursor_execute", self._on_execute)
