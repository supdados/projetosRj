"""Testes do resolvedor de menções (`services/comment_mentions`).

O caso que motivou o módulo: "@Ana Luiza Ribeiro faca X coisas" destacava apenas
"@Ana", porque o render adivinhava o fim do nome no cliente.
"""

import unicodedata

from services.comment_mentions import (
    MentionCandidate,
    candidates_from_users,
    extract_mention_spans,
    normalize_comment_content,
)

ANA_COMPOSTA = MentionCandidate(user_id=7, name="Ana Luiza Ribeiro")
ANA_CURTA = MentionCandidate(user_id=9, name="Ana")
JOSE = MentionCandidate(user_id=3, name="José Hudson")


class FakeUser:
    """Substituto nomeado de `models.User` (sem ORM) para os candidatos."""

    def __init__(self, user_id, name):
        self.id = user_id
        self.name = name


def test_nome_composto_cobre_o_nome_inteiro():
    spans = extract_mention_spans("@Ana Luiza Ribeiro faca X coisas", [ANA_COMPOSTA])

    assert spans == [
        {
            "user_id": 7,
            "name": "Ana Luiza Ribeiro",
            "start": 0,
            "length": 18,
            "ambiguous": False,
        }
    ]
    texto = "@Ana Luiza Ribeiro faca X coisas"
    assert texto[0:18] == "@Ana Luiza Ribeiro"


def test_nome_mais_longo_vence_o_mais_curto():
    spans = extract_mention_spans("oi @Ana Luiza Ribeiro", [ANA_CURTA, ANA_COMPOSTA])

    assert [s["user_id"] for s in spans] == [7]
    assert spans[0]["length"] == 18


def test_nome_curto_ainda_casa_quando_e_o_unico_possivel():
    spans = extract_mention_spans("obrigado @Ana!", [ANA_CURTA, ANA_COMPOSTA])

    assert spans == [
        {"user_id": 9, "name": "Ana", "start": 9, "length": 4, "ambiguous": False}
    ]


def test_nao_casa_prefixo_no_meio_de_outra_palavra():
    assert extract_mention_spans("@Anabel passou aqui", [ANA_CURTA]) == []


def test_acentos_e_caixa_sao_ignorados_na_comparacao():
    spans = extract_mention_spans("valeu @jose hudson", [JOSE])

    assert len(spans) == 1
    assert spans[0]["name"] == "José Hudson"
    assert spans[0]["start"] == 6
    # O comprimento aponta para o trecho REAL digitado, não para o cadastro.
    assert "valeu @jose hudson"[6 : 6 + spans[0]["length"]] == "@jose hudson"


def test_varias_mencoes_no_mesmo_texto():
    spans = extract_mention_spans(
        "@Ana Luiza Ribeiro e @José Hudson revisam", [ANA_COMPOSTA, JOSE]
    )

    assert [s["user_id"] for s in spans] == [7, 3]
    assert [s["start"] for s in spans] == [0, 21]


def test_arroba_sem_candidato_nao_vira_mencao():
    assert extract_mention_spans("mande para fulano@example.com", [ANA_CURTA]) == []


def test_texto_vazio_ou_sem_candidatos():
    assert extract_mention_spans("", [ANA_CURTA]) == []
    assert extract_mention_spans("@Ana", []) == []


def test_candidatos_de_usuarios_descartam_nome_em_branco():
    candidatos = candidates_from_users(
        [FakeUser(1, "Ana"), FakeUser(2, "   "), FakeUser(None, "Sem id")]
    )

    assert candidatos == [MentionCandidate(user_id=1, name="Ana")]


# ---------------------------------------------------------------------------
# Regressões da revisão adversarial (offsets, fronteiras e homônimos)
# ---------------------------------------------------------------------------


def test_offsets_sao_em_unidades_utf16_como_no_javascript():
    """Emoji ocupa 2 unidades UTF-16 e 1 code point — o front fatia em UTF-16."""
    texto = "\U0001f600 @Ana oi"
    spans = extract_mention_spans(texto, [ANA_CURTA])

    assert spans[0]["start"] == 3  # 2 do emoji + 1 do espaço
    utf16 = texto.encode("utf-16-le")
    trecho = utf16[spans[0]["start"] * 2 : (spans[0]["start"] + spans[0]["length"]) * 2]
    assert trecho.decode("utf-16-le") == "@Ana"


def test_texto_nfd_e_normalizado_antes_de_medir():
    """macOS cola em NFD; o conteúdo gravado e os offsets usam a MESMA forma."""
    cru = unicodedata.normalize("NFD", "José disse @Ana sim")
    gravado = normalize_comment_content(cru)
    spans = extract_mention_spans(gravado, [ANA_CURTA])

    inicio = spans[0]["start"]
    assert gravado[inicio : inicio + spans[0]["length"]] == "@Ana"


def test_ponto_final_de_frase_nao_mata_a_mencao():
    spans = extract_mention_spans("obrigado @Ana.", [ANA_CURTA])

    assert [s["start"] for s in spans] == [9]
    assert spans[0]["length"] == 4


def test_ponto_interno_ainda_faz_parte_do_nome():
    ana_ponto = MentionCandidate(user_id=11, name="Ana.Silva")
    spans = extract_mention_spans("oi @Ana.Silva", [ANA_CURTA, ana_ponto])

    assert [s["user_id"] for s in spans] == [11]


def test_arroba_colado_em_palavra_nao_vira_mencao():
    """ "contato@ana" é endereço, não menção — exige fronteira ANTES do @."""
    assert extract_mention_spans("contato@ana", [ANA_CURTA]) == []
    assert extract_mention_spans("fulano@ana.com", [ANA_CURTA]) == []


def test_homonimos_marcam_a_mencao_como_ambigua():
    outra_ana = MentionCandidate(user_id=4, name="Ana")
    spans = extract_mention_spans("oi @Ana", [ANA_CURTA, outra_ana])

    assert len(spans) == 1
    assert spans[0]["ambiguous"] is True
    assert spans[0]["user_id"] == 4  # desempate determinístico pelo menor id


def test_mencao_unica_nao_e_ambigua():
    spans = extract_mention_spans("oi @Ana", [ANA_CURTA])

    assert spans[0]["ambiguous"] is False


# ---------------------------------------------------------------------------
# Regressão: pontuação colada ao FIM do nome não pode invalidar o match
# ---------------------------------------------------------------------------

MARIA = MentionCandidate(user_id=21, name="Maria Silva")


def test_hifen_apos_nome_completo_nao_desvia_para_homonima():
    """Regressão: "@Ana Luiza Ribeiro-favor" gravava a menção da "Ana" (id errado)."""
    spans = extract_mention_spans(
        "@Ana Luiza Ribeiro-favor revisar", [ANA_CURTA, ANA_COMPOSTA]
    )

    assert [s["user_id"] for s in spans] == [7]
    assert spans[0]["length"] == 18


def test_ponto_apos_nome_completo_nao_desvia_para_homonima():
    spans = extract_mention_spans(
        "@Ana Luiza Ribeiro.confere ai", [ANA_CURTA, ANA_COMPOSTA]
    )

    assert [s["user_id"] for s in spans] == [7]
    assert spans[0]["length"] == 18


def test_pontuacao_apos_nome_sem_homonimo_ainda_gera_mencao():
    """Regressão: sem homônimo o resultado era NENHUMA menção."""
    for texto in ("@Maria Silva-me confirma", "@Maria Silva.ok", "@Maria Silva's doc"):
        spans = extract_mention_spans(texto, [MARIA])

        assert [s["user_id"] for s in spans] == [21], texto
        assert texto[: spans[0]["length"]] == "@Maria Silva", texto


def test_nome_mais_longo_ainda_ganha_com_pontuacao_interna():
    """A pontuação só é aceita como fim do nome quando nenhum nome maior casa."""
    ana_hifen = MentionCandidate(user_id=13, name="Ana-Maria")
    spans = extract_mention_spans("oi @Ana-Maria agora", [ANA_CURTA, ana_hifen])

    assert [s["user_id"] for s in spans] == [13]


def test_letra_colada_ao_nome_continua_invalidando_o_match():
    """Guarda: só letra/dígito prolonga a palavra — "@Anabel" segue sem menção."""
    assert extract_mention_spans("@Anabel passou aqui", [ANA_CURTA]) == []
    assert extract_mention_spans("@Maria Silvarez veio", [MARIA]) == []
