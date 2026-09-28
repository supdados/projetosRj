"""Mede requests reais com SQLite sintético, sem subir servidor.

Use --phase before e depois --phase after com o MESMO --directory. O segundo
run reutiliza os bancos e compara o JSON completo. Nunca abre o banco configurado
no ambiente; não sobrescreve bancos existentes nem toca arquivos de anexos.
"""

from __future__ import annotations

import argparse
from collections import Counter
import gc
import json
import os
from pathlib import Path
import statistics
import sys
import time
import tracemalloc
from typing import TypedDict
from unittest.mock import patch

os.environ["SKIP_STARTUP_DB_INIT"] = "true"
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flask import Flask
from sqlalchemy import event
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app import create_app
from models import db
from scripts.benchmarks.review_read_fixtures import REFERENCE_DAY, seed_read_workload

ENDPOINTS = (
    "/api/projetos?status=Vigente&per_page=40",
    "/api/dashboard",
    "/api/tarefas/board",
    "/api/projetos-pendentes?periodo=21dias&page=1",
    "/api/busca?q=Etapa%20medi%C3%A7%C3%A3o&types=stages&page=1&per_page=40",
    "/api/colecoes",
)


class ReadMetrics(TypedDict):
    median_ms: float
    peak_mib: float
    selects: int
    physical_rows: int
    max_rows_per_select: int
    objects: dict[str, int]
    same_json: bool


class RequestProbe:
    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple[object, ...] | dict[str, object]]] = []
        self.objects: Counter[str] = Counter()

    def sql(self, _conn, _cursor, statement, parameters, _context, _many) -> None:
        if statement.lstrip().upper().startswith(("SELECT", "WITH")):
            self.statements.append((statement, parameters))

    def loaded(self, _session: Session, instance: object) -> None:
        self.objects[type(instance).__name__] += 1


def benchmark_app(path: Path) -> Flask:
    """App com banco explícito de fixture e integrações externas desligadas."""
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "benchmark-only",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{path}",
            "SQLALCHEMY_ENGINE_OPTIONS": {"poolclass": NullPool},
            "SKIP_STARTUP_DB_INIT": True,
            "WTF_CSRF_ENABLED": False,
            "GOVBR_OIDC_ENABLED": False,
            "PROXYFIX_ENABLED": False,
            "CHATBOT_ENABLED": False,
            "SIORG_API_KEY": "",
            "CONVITES_HABILITADOS": False,
        }
    )


def request_json(app: Flask, endpoint: str) -> dict[str, object]:
    """Novo cliente/contexto e sessão ORM fria em cada request."""
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = 1
            session["login_at"] = time.time()
        response = client.get(endpoint)
        if response.status_code != 200:
            raise RuntimeError(
                f"{endpoint}: esperado 200, recebido {response.status_code}: {response.get_json()}"
            )
        return response.get_json()


def profile_request(app: Flask, endpoint: str) -> tuple[ReadMetrics, dict[str, object]]:
    """Latência sem tracing; objetos, memória e linhas SQL em execução separada."""
    request_json(app, endpoint)  # Compila SQL/cache de código, mantendo a sessão fria.
    elapsed: list[float] = []
    for _ in range(5):
        started = time.perf_counter()
        request_json(app, endpoint)
        elapsed.append((time.perf_counter() - started) * 1000)
    probe = RequestProbe()
    with app.app_context():
        engine = db.engine
    event.listen(engine, "before_cursor_execute", probe.sql)
    event.listen(Session, "loaded_as_persistent", probe.loaded)
    gc.collect()
    tracemalloc.start()
    try:
        payload = request_json(app, endpoint)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
        event.remove(engine, "before_cursor_execute", probe.sql)
        event.remove(Session, "loaded_as_persistent", probe.loaded)
    # SQLite rowcount não informa SELECT; reexecuta as leituras fora da medição.
    with engine.connect() as connection:
        row_counts = [
            len(connection.exec_driver_sql(sql, params).fetchall())
            for sql, params in probe.statements
        ]
    return {
        "median_ms": round(statistics.median(elapsed), 2),
        "peak_mib": round(peak / 1048576, 2),
        "selects": len(probe.statements),
        "physical_rows": sum(row_counts),
        "max_rows_per_select": max(row_counts, default=0),
        "objects": dict(probe.objects),
        "same_json": True,
    }, payload


def run_phase(directory: Path, phase: str) -> None:
    """Executa as duas cargas e grava evidências para comparação antes/depois."""
    marker = directory / "fixture.json"
    if phase == "after" and not marker.is_file():
        raise ValueError(
            f"Fixture ausente em {directory}; execute --phase before primeiro."
        )
    directory.mkdir(parents=True, exist_ok=True)
    metrics: dict[str, dict[str, ReadMetrics]] = {}
    for size in (30, 120):
        db_path = directory / f"fixture-{size}.sqlite"
        if phase == "before" and db_path.exists():
            raise ValueError(
                f"Banco já existe: {db_path}; use um diretório de fixture novo."
            )
        if phase == "after" and not db_path.is_file():
            raise ValueError(f"Banco de fixture ausente: {db_path}.")
        app = benchmark_app(db_path)
        if phase == "before":
            with app.app_context():
                db.create_all()
                seed_read_workload(size)
        metrics[str(size)] = {}
        for index, endpoint in enumerate(ENDPOINTS):
            result, payload = profile_request(app, endpoint)
            baseline = directory / f"payload-{size}-{index}.json"
            if phase == "before":
                baseline.write_text(
                    json.dumps(payload, ensure_ascii=False, sort_keys=True)
                )
            else:
                result["same_json"] = payload == json.loads(baseline.read_text())
                (directory / f"after-payload-{size}-{index}.json").write_text(
                    json.dumps(payload, ensure_ascii=False, sort_keys=True)
                )
            metrics[str(size)][endpoint] = result
            print(
                json.dumps({"size": size, "endpoint": endpoint, **result}), flush=True
            )
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
    marker.write_text(
        json.dumps({"sizes": [30, 120], "reference_day": str(REFERENCE_DAY)})
    )
    (directory / f"{phase}.json").write_text(json.dumps(metrics, indent=2))
    changed = [
        (size, endpoint)
        for size, rows in metrics.items()
        for endpoint, result in rows.items()
        if not result["same_json"]
    ]
    if changed:
        raise AssertionError(
            f"JSON mudou em {changed}; compare os payloads gravados em {directory}."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--phase", choices=("before", "after"), required=True)
    args = parser.parse_args()
    with patch("services.atraso.hoje_utc", return_value=REFERENCE_DAY), patch(
        "routes.projects.views.hoje_utc", return_value=REFERENCE_DAY
    ):
        run_phase(args.directory.resolve(), args.phase)


if __name__ == "__main__":
    main()
