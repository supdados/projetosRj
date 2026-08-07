"""Parse e validação da resposta da IA de sugestão de coleções.

Validação em camadas: estrutural (tipos, limites — erro acumulado para o
retry com feedback) e semântica (id alucinado descartado em silêncio; coleção
com <2 ids válidos ou nome já usado cai inteira). Sem pydantic: o repo não o
tem como dependência.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace

from services.project_collections import (
    DESCRICAO_MAX_COLECAO,
    FAVORITOS_NOME,
    NOME_MAX_COLECAO,
)

_JSON_NO_TEXTO_RE = re.compile(r"\{.*\}", re.DOTALL)


class SugestoesInvalidas(ValueError):
    """Resposta estruturalmente inválida; ``erros`` alimenta o retry."""

    def __init__(self, erros: list[str]) -> None:
        super().__init__("; ".join(erros))
        self.erros = erros


MAX_PALAVRAS_CRITERIO = 8
# Teto duro: justificativa em loop degenerativo ("saúde, saúde, ...") estoura
# isto e vira erro estrutural que alimenta o retry com feedback.
JUSTIFICATIVA_MAX_SUGESTAO = 300


@dataclass(frozen=True)
class ColecaoSugerida:
    nome: str
    descricao: str | None
    justificativa: str
    project_ids: list[int]
    # Palavras objetivas declaradas pelo modelo; o backend verifica cada
    # project_id contra elas (anti-alucinação determinística). Não persiste.
    criterio_palavras: list[str]


def extrair_json(texto: str) -> dict[str, object] | None:
    """JSON da resposta: ``json.loads`` direto, senão o maior bloco ``{...}``,
    senão ``None`` (padrão ``_parse_json`` do chatbot devlab)."""
    direto = _dict_de_json(texto)
    if direto is not None:
        return direto
    trecho = _JSON_NO_TEXTO_RE.search(texto)
    if trecho is None:
        return None
    return _dict_de_json(trecho.group(0))


def _dict_de_json(texto: str) -> dict[str, object] | None:
    try:
        parsed = json.loads(texto)
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def validar_sugestoes(
    payload: dict[str, object] | None,
    *,
    ids_permitidos: set[int],
    nomes_indisponiveis: set[str],
) -> list[ColecaoSugerida]:
    """Sugestões válidas do payload; levanta ``SugestoesInvalidas`` se a
    estrutura falhar ou nenhuma sobreviver ao filtro semântico.

    Exemplo: ``validar_sugestoes(extrair_json(texto), ids_permitidos={3, 7},
    nomes_indisponiveis={"Favoritos"})``.
    """
    brutas = _lista_de_sugestoes(payload)
    reservados = {nome.casefold() for nome in (FAVORITOS_NOME, *nomes_indisponiveis)}
    erros: list[str] = []
    validas: list[ColecaoSugerida] = []
    for indice, bruta in enumerate(brutas):
        sugestao = _validar_estrutura(bruta, indice, erros)
        if sugestao is None:
            continue
        filtrada = _filtrar_semantica(sugestao, ids_permitidos, reservados)
        if filtrada is not None:
            validas.append(filtrada)
    return _resolver_validacao(validas, erros)


def _lista_de_sugestoes(payload: dict[str, object] | None) -> list[object]:
    if payload is None:
        raise SugestoesInvalidas(["resposta não é um objeto JSON válido"])
    brutas = payload.get("sugestoes")
    if not isinstance(brutas, list) or not brutas:
        raise SugestoesInvalidas(
            ['campo "sugestoes" ausente ou vazio; esperado lista de objetos']
        )
    return brutas


def _resolver_validacao(
    validas: list[ColecaoSugerida], erros: list[str]
) -> list[ColecaoSugerida]:
    if erros:
        raise SugestoesInvalidas(erros)
    if not validas:
        raise SugestoesInvalidas(
            ["nenhuma sugestão restou: ids fora da lista enviada ou nomes já usados"]
        )
    return validas


def _validar_estrutura(
    bruta: object, indice: int, erros: list[str]
) -> ColecaoSugerida | None:
    if not isinstance(bruta, dict):
        erros.append(
            f"sugestoes[{indice}]: esperado objeto, recebido {type(bruta).__name__}"
        )
        return None
    antes = len(erros)
    campos = _campos_da_sugestao(bruta, indice, erros)
    if len(erros) > antes:
        return None
    return campos


def _campos_da_sugestao(
    bruta: dict[str, object], indice: int, erros: list[str]
) -> ColecaoSugerida:
    nome = _texto(
        bruta.get("nome"), NOME_MAX_COLECAO, f"sugestoes[{indice}].nome", erros
    )
    descricao = _texto_opcional(
        bruta.get("descricao"),
        DESCRICAO_MAX_COLECAO,
        f"sugestoes[{indice}].descricao",
        erros,
    )
    justificativa = _texto(
        bruta.get("justificativa"),
        JUSTIFICATIVA_MAX_SUGESTAO,
        f"sugestoes[{indice}].justificativa",
        erros,
    )
    project_ids = _ids_de_projeto(
        bruta.get("project_ids"), f"sugestoes[{indice}].project_ids", erros
    )
    criterio = _palavras_criterio(
        bruta.get("criterio_palavras"), f"sugestoes[{indice}].criterio_palavras", erros
    )
    return ColecaoSugerida(
        nome=nome or "",
        descricao=descricao,
        justificativa=justificativa or "",
        project_ids=project_ids or [],
        criterio_palavras=criterio or [],
    )


def _palavras_criterio(valor: object, campo: str, erros: list[str]) -> list[str] | None:
    if not isinstance(valor, list) or not valor:
        erros.append(
            f"{campo}: obrigatório lista não vazia de palavras-chave, recebido {valor!r}"
        )
        return None
    limpas = [item.strip() for item in valor if isinstance(item, str) and item.strip()]
    if not limpas:
        erros.append(f"{campo}: nenhuma palavra-chave válida em {valor!r}")
        return None
    return limpas[:MAX_PALAVRAS_CRITERIO]


def _texto(
    valor: object, maximo: int | None, campo: str, erros: list[str]
) -> str | None:
    if not isinstance(valor, str) or not valor.strip():
        erros.append(f"{campo}: obrigatório texto não vazio, recebido {valor!r}")
        return None
    limpo = valor.strip()
    if maximo is not None and len(limpo) > maximo:
        erros.append(f"{campo}: {len(limpo)} caracteres; máximo {maximo}")
        return None
    return limpo


def _texto_opcional(
    valor: object, maximo: int, campo: str, erros: list[str]
) -> str | None:
    if valor is None:
        return None
    if not isinstance(valor, str):
        erros.append(f"{campo}: esperado texto ou null, recebido {valor!r}")
        return None
    limpo = valor.strip()
    if len(limpo) > maximo:
        erros.append(f"{campo}: {len(limpo)} caracteres; máximo {maximo}")
        return None
    return limpo or None


def _ids_de_projeto(valor: object, campo: str, erros: list[str]) -> list[int] | None:
    if not isinstance(valor, list) or not all(
        isinstance(item, int) and not isinstance(item, bool) for item in valor
    ):
        erros.append(f"{campo}: esperado lista de inteiros, recebido {valor!r}")
        return None
    unicos = list(dict.fromkeys(valor))
    if len(unicos) < 2:
        erros.append(f"{campo}: mínimo 2 projetos distintos, recebido {unicos!r}")
        return None
    return unicos


def _filtrar_semantica(
    sugestao: ColecaoSugerida, ids_permitidos: set[int], reservados: set[str]
) -> ColecaoSugerida | None:
    if sugestao.nome.casefold() in reservados:
        return None
    ids_validos = [pid for pid in sugestao.project_ids if pid in ids_permitidos]
    if len(ids_validos) < 2:
        return None
    if ids_validos == sugestao.project_ids:
        return sugestao
    return replace(sugestao, project_ids=ids_validos)
