"""Contexto da execução, aborto de stage e o JSON compartilhado pelos stages.

O arquivo de ``--relatorio`` é o único estado que sobrevive entre execuções do
orquestrador (``migrar_producao_v5.py``): é dele que sai a LINHA DE BASE do
colapso (``role_map_pre`` / ``vinculos_pre``), que o portão ``verificar_role_map``
reexecuta para conferir ``user_orgao`` par a par. Por isso as travas de leitura
e a recusa de sobrescrever a base moram aqui, junto de quem escreve o arquivo.

Uso::

    ctx = Contexto(apply=True, relatorio=Path("instance/migracao.json"))
    registrar_stage(ctx.relatorio, "colapso", {"removidos": 102})
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from scripts.migrations.auditoria_role_map import desserializar_vinculos


class StageAbortado(RuntimeError):
    """Pré-condição ausente: o stage não pode rodar e a execução para."""


@dataclass(frozen=True)
class Contexto:
    apply: bool
    relatorio: Path


def ler_relatorio(caminho: Path) -> dict[str, object]:
    if not caminho.exists():
        return {}
    return json.loads(caminho.read_text(encoding="utf-8"))


def atualizar_relatorio(caminho: Path, novos: dict[str, object]) -> None:
    dados = ler_relatorio(caminho)
    dados.update(novos)
    dados["atualizado_em"] = datetime.now(timezone.utc).isoformat()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


def registrar_stage(caminho: Path, nome: str, dados: dict[str, object]) -> None:
    relatorio = ler_relatorio(caminho)
    stages = dict(relatorio.get("stages") or {})
    stages[nome] = dados
    atualizar_relatorio(caminho, {"stages": stages})


def exigir_role_map_pre(ctx: Contexto) -> dict:
    """Linha de base do colapso: precisa existir e ter vindo de um `--apply`."""
    relatorio = ler_relatorio(ctx.relatorio)
    role_map_pre = relatorio.get("role_map_pre")
    if not role_map_pre:
        raise StageAbortado(
            f"{ctx.relatorio} não tem `role_map_pre`: rode `--stage snapshot_role_map`"
            " ANTES do colapso, é ele que grava a linha de base da comparação."
        )
    if ctx.apply and not relatorio.get("role_map_pre_aplicado"):
        raise StageAbortado(
            f"o `role_map_pre` de {ctx.relatorio} veio de um ensaio dry-run e não vale"
            " como base do colapso real: rode `--stage snapshot_role_map --apply`."
        )
    return role_map_pre


def exigir_vinculos_pre(ctx: Contexto) -> dict[int, list[tuple[int, str]]]:
    """Base do recálculo do KEEP: precisa existir e trazer o papel de cada vínculo."""
    bruto = ler_relatorio(ctx.relatorio).get("vinculos_pre")
    if not bruto:
        raise StageAbortado(
            f"{ctx.relatorio} não tem `vinculos_pre`: é ele que o portão reexecuta "
            "para recalcular o KEEP. Rode `--stage snapshot_role_map --apply` ANTES "
            "do colapso."
        )
    try:
        return desserializar_vinculos(bruto)
    except (AttributeError, TypeError, ValueError) as exc:
        raise StageAbortado(
            f"`vinculos_pre` de {ctx.relatorio} está fora do formato "
            f"{{user_id: [[orgao_id, papel]]}}: {exc}"
        ) from exc


def recusar_sobrescrever_a_base(ctx: Contexto) -> None:
    """Regravar depois do colapso trocaria o estado PRÉ pelo PÓS em silêncio."""
    relatorio = ler_relatorio(ctx.relatorio)
    role_map_pre = relatorio.get("role_map_pre")
    if not (role_map_pre and relatorio.get("role_map_pre_aplicado")):
        return
    raise StageAbortado(
        f"{ctx.relatorio} já tem linha de base aplicada ({len(role_map_pre)} usuários,"
        f" {_total_de_vinculos(relatorio)} vínculos) e regravá-la aqui fotografaria o "
        "estado PÓS-colapso: o portão `verificar_role_map` passaria comparando o "
        "resultado com ele mesmo. Para RETOMAR, rode os stages seguintes sem "
        "`snapshot_role_map` (ex.: `--stage colapso --stage verificar_role_map`). "
        "Para refazer do zero, guarde uma cópia deste JSON e use `--relatorio "
        "outro.json`."
    )


def _total_de_vinculos(relatorio: dict[str, object]) -> int:
    bruto = relatorio.get("vinculos_pre")
    if not isinstance(bruto, dict):
        return 0
    return sum(len(itens) for itens in bruto.values())
