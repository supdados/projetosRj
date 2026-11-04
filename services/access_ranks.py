"""Taxonomia de papéis de acesso a projeto e seus ranks numéricos.

Módulo-folha (só constantes): ``services.authorization`` e
``services.collection_access`` dependem destes valores, e o segundo é
importado pelo primeiro — morar aqui evita o ciclo de import. Os nomes
continuam reexportados por ``services.authorization`` (contrato antigo).

Exemplo: ``PAPEL_RANK[PAPEL_EDITOR] == 20``.
"""

from __future__ import annotations

PAPEL_LEITOR = "leitor"
PAPEL_EDITOR = "editor"
PAPEL_GESTOR = "gestor"

PAPEL_RANK: dict[str, int] = {
    PAPEL_LEITOR: 10,
    PAPEL_EDITOR: 20,
    PAPEL_GESTOR: 30,
}

# Piso do admin global: vence qualquer papel local, nunca é rebaixado.
ADMIN_RANK: int = 100
