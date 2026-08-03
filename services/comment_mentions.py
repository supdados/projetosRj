"""Resolução de menções (``@Fulano``) em comentários de tarefa.

O texto puro é ambíguo: em ``"@Ana Luiza Ribeiro faca X"`` não há como saber, só
olhando a string, onde o nome termina. Por isso a menção é resolvida no momento
da ESCRITA, contra a lista real de pessoas com acesso ao projeto, e gravada como
dado estruturado (``task_comment.mentions``) — o render só pinta os intervalos
recebidos, sem adivinhar nada.

``start``/``length`` são contados em UNIDADES UTF-16, não em code points: quem
consome é o JavaScript, e lá ``String.slice`` opera em UTF-16. Sem isso, um
emoji antes da menção (2 unidades, 1 code point) deslocaria o realce.

Exemplo de uso::

    spans = extract_mention_spans(
        "obrigado @Ana Luiza Ribeiro e @Ana",
        [MentionCandidate(user_id=7, name="Ana Luiza Ribeiro"),
         MentionCandidate(user_id=9, name="Ana")],
    )
    # [{'user_id': 7, 'name': 'Ana Luiza Ribeiro', 'start': 9, 'length': 18},
    #  {'user_id': 9, 'name': 'Ana', 'start': 30, 'length': 4}]
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

MENTION_SIGIL = "@"


@dataclass(frozen=True)
class MentionCandidate:
    """Pessoa mencionável: o ``user_id`` é o que torna a menção estável."""

    user_id: int
    name: str


def _fold_char(char: str) -> str:
    """Versão comparável de UM caractere, sempre com 1 caractere de saída.

    Manter o comprimento é requisito: os deslocamentos calculados sobre o texto
    dobrado precisam valer no texto original. Casos que expandiriam (``ß`` →
    ``ss``) ficam com o caractere em minúscula simples.
    """
    stripped = "".join(
        c for c in unicodedata.normalize("NFD", char) if not unicodedata.combining(c)
    )
    folded = (stripped or char).casefold()
    return folded if len(folded) == 1 else char.lower()


def _fold(value: str) -> str:
    """Minúsculas sem acento, preservando o comprimento (ver ``_fold_char``)."""
    return "".join(
        _fold_char(char) for char in unicodedata.normalize("NFC", value or "")
    )


def _extends_into_word(folded_text: str, position: int) -> bool:
    """O nome casado é só o começo de uma palavra maior ("@Ana" em "@Anabel")?

    Só letra/dígito COLADO prolonga a palavra. Pontuação (``-``, ``.``, ``'``)
    não desqualifica o match: em "@Maria Silva-me confirma" o hífen é do texto,
    não do nome. Nomes que de fato contêm pontuação ("Ana.Silva") continuam
    ganhando porque :func:`_match_at` testa os candidatos do mais longo ao mais
    curto — quando um nome casa, nenhum nome maior casava naquela posição.
    """
    return position < len(folded_text) and folded_text[position].isalnum()


def _candidates_by_length(
    candidates: Iterable[MentionCandidate],
) -> list[tuple[str, MentionCandidate]]:
    """Pares (nome dobrado, candidato) do mais longo para o mais curto.

    A ordem é o que garante que "Ana Luiza Ribeiro" ganhe de "Ana" quando as duas
    pessoas existem; o desempate por ``user_id`` mantém o resultado determinístico.
    """
    pairs = [
        (_fold(c.name.strip()), c)
        for c in candidates
        if c is not None and (c.name or "").strip()
    ]
    return sorted(pairs, key=lambda pair: (-len(pair[0]), pair[1].user_id))


def _count_by_folded_name(
    ordered: Sequence[tuple[str, MentionCandidate]],
) -> dict[str, int]:
    """Quantas pessoas respondem por cada nome — homônimos viram ``ambiguous``."""
    counts: dict[str, int] = {}
    for folded_name, _ in ordered:
        counts[folded_name] = counts.get(folded_name, 0) + 1
    return counts


def _match_at(
    folded_text: str, position: int, ordered: Sequence[tuple[str, MentionCandidate]]
) -> tuple[str, MentionCandidate] | None:
    """Maior nome que casa logo após o ``@`` em ``position``, ou ``None``.

    ``ordered`` vem do mais longo para o mais curto, então o primeiro nome que
    casa inteiro já é o melhor possível.
    """
    for folded_name, candidate in ordered:
        if not folded_text.startswith(folded_name, position):
            continue
        if _extends_into_word(folded_text, position + len(folded_name)):
            continue
        return folded_name, candidate
    return None


def normalize_comment_content(content: str) -> str:
    """Forma canônica NFC do texto — o que DEVE ser gravado no banco.

    Os deslocamentos são calculados sobre esta forma; gravar o texto cru (macOS
    cola em NFD) deslocaria o realce a cada acento anterior à menção.
    """
    return unicodedata.normalize("NFC", content or "")


def _utf16_length(value: str) -> int:
    """Comprimento em unidades UTF-16 (fora do BMP conta 2, como no JavaScript)."""
    return sum(2 if ord(char) > 0xFFFF else 1 for char in value)


def _is_sigil_boundary(text: str, at: int) -> bool:
    """O ``@`` inicia uma menção? Não, se estiver colado a letra/dígito.

    Evita que o trecho após o arroba de um e-mail ("contato@ana") vire menção.
    """
    return at == 0 or not text[at - 1].isalnum()


def extract_mention_spans(
    content: str, candidates: Iterable[MentionCandidate]
) -> list[dict[str, Any]]:
    """Intervalos de menção de ``content``, resolvidos contra ``candidates``.

    Args:
        content: Texto do comentário JÁ normalizado por
            :func:`normalize_comment_content` (é o que fica gravado).
        candidates: Pessoas mencionáveis (quem tem acesso ao projeto da tarefa).

    Returns:
        Lista JSON-safe ordenada por ``start``, cada item com ``user_id``,
        ``name`` (como cadastrado, não como digitado), ``start``/``length`` em
        UNIDADES UTF-16 (incluindo o ``@``) e ``ambiguous`` quando mais de uma
        pessoa responde pelo mesmo nome. Vazia quando nada casa: um ``@`` solto
        continua sendo texto comum.
    """
    text = normalize_comment_content(content)
    ordered = _candidates_by_length(candidates)
    if not text or not ordered:
        return []

    homonyms = _count_by_folded_name(ordered)
    folded = _fold(text)
    spans: list[dict[str, Any]] = []
    index = 0
    utf16_start = 0  # deslocamento UTF-16 do trecho já percorrido
    while True:
        at = text.find(MENTION_SIGIL, index)
        if at == -1:
            break
        utf16_start += _utf16_length(text[index:at])
        match = (
            _match_at(folded, at + 1, ordered) if _is_sigil_boundary(text, at) else None
        )
        if match is None:
            index = at + 1
            utf16_start += 1
            continue
        folded_name, candidate = match
        length = 1 + len(folded_name)
        spans.append(
            {
                "user_id": candidate.user_id,
                "name": candidate.name.strip(),
                "start": utf16_start,
                "length": _utf16_length(text[at : at + length]),
                "ambiguous": homonyms[folded_name] > 1,
            }
        )
        utf16_start += _utf16_length(text[at : at + length])
        index = at + length
    return spans


def candidates_from_users(users: Iterable[Any]) -> list[MentionCandidate]:
    """Converte ``User`` (ou qualquer objeto com ``id``/``name``) em candidatos."""
    result: list[MentionCandidate] = []
    for user in users or []:
        user_id = getattr(user, "id", None)
        name = getattr(user, "name", None)
        if user_id is None or not (name or "").strip():
            continue
        result.append(MentionCandidate(user_id=int(user_id), name=name.strip()))
    return result
