"""
Catalogo fixo de Indicadores ABEP.
"""

ABEP_INDICATOR_PAIRS = [
    ("1.1", "Estratégia de Governo Digital"),
    ("1.2", "Órgão Reitor"),
    ("1.3", "Órgão colegiado"),
    ("1.4", "Governança de dados"),
    ("1.5", "Competências digitais"),
    ("1.6", "Interoperabilidade"),
    ("1.7", "Portal Único"),
    ("1.8", "Assinatura digital"),
    ("1.9", "Pagamento digital"),
    ("1.10", "Unidade Cyber"),
    ("1.11", "CERT"),
    ("1.12", "Conectividade"),
    ("2.1", "Serviço digital - Rematricula"),
    ("2.2", "Serviço digital - Remédios alto $"),
    ("2.3", "Serviço digital - Telemedicina"),
    ("2.4", "Serviço digital - Prova de vida"),
    ("2.5", "Serviço digital - infrações trânsito"),
    ("2.6", "Serviço digital - consulta medica"),
    ("2.7", "Serviço digital - receita"),
    ("2.8", "Serviço digital - diploma"),
    ("2.9", "Serviço digital - alunos"),
    ("2.10", "Serviço digital - veículos"),
    ("2.11", "Serviço digital - CIN"),
    ("2.12", "Plataforma de saúde"),
    ("3.1", "Regula Portal"),
    ("3.2", "Regula princípios"),
    ("3.3", "Regula assinatura"),
    ("3.4", "Regulações variadas"),
    ("3.5", "Regula linguagem simples"),
    ("3.6", "Padrões e diretrizes para gestão de dados"),
    ("4.1", "Linguagem simples"),
    ("4.2", "Kit de participação nos serviços"),
    ("4.3", "Omnicanalidade"),
    ("4.4", "Acessibilidade digital"),
    ("4.5", "Métricas de uso do Portal"),
    ("4.6", "Alfabetização Digital"),
    ("4.7", "Avaliação de serviços"),
    ("4.8", "Participação Digital"),
    ("5.1", "Estratégia de IA"),
    ("5.2", "Soluções de IA"),
    ("5.3", "Compras Públicas de Inovação"),
    ("5.4", "Uso de APIs abertas"),
    ("5.5", "Laboratório de Inovação"),
    ("5.6", "Apoio municipal"),
]


def build_abep_indicator_label(code, title):
    return f"{code} - {title}"


def build_legacy_abep_indicator_label(code, title):
    return f"INDICADOR {code} - {title}"


ABEP_INDICADORES_OPTIONS = [
    {
        "code": code,
        "title": title,
        "value": build_abep_indicator_label(code, title),
        "label": build_abep_indicator_label(code, title),
    }
    for code, title in ABEP_INDICATOR_PAIRS
]

ABEP_INDICADORES_VALUES = set(item["value"] for item in ABEP_INDICADORES_OPTIONS)
ABEP_INDICADORES_LEGACY_ALIASES = {
    build_legacy_abep_indicator_label(code, title): build_abep_indicator_label(code, title)
    for code, title in ABEP_INDICATOR_PAIRS
}


def normalize_abep_indicator(value):
    if value is None:
        return None

    normalized = str(value).strip()
    if normalized == "":
        return None

    if normalized not in ABEP_INDICADORES_VALUES:
        if normalized in ABEP_INDICADORES_LEGACY_ALIASES:
            return ABEP_INDICADORES_LEGACY_ALIASES[normalized]
        raise ValueError("Indicador ABEP inválido.")

    return normalized
