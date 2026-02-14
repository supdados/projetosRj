"""
Catalogo canonico de Objetivos -> Resultados Esperados -> Indicadores.

Este modulo evita dependencia de seed manual no banco para renderizar os campos
de formulario e para validar os IDs recebidos.
"""

MAX_INDICADORES_POR_PROJETO = 4

# Estrutura hierarquica canonica.
GOAL_CATALOG = [
    {
        "id": 1,
        "descricao": "1- Fortalecer governanca digital colaborativa",
        "resultados": [
            {
                "id": 1,
                "descricao": "Gestao e governanca da politica de governo digital estadual qualificadas",
                "indicadores": [
                    {"id": 1, "descricao": "N de orgaos/entidades com pontos focais de governo digital indicados"},
                ],
            },
            {
                "id": 2,
                "descricao": "Colaboracao interfederativa promovida",
                "indicadores": [
                    {"id": 2, "descricao": "% de municipios no Programa RJ Digital"},
                    {"id": 3, "descricao": "% de orgaos e entidades com nivel de maturidade digital intermediario ou avancado"},
                ],
            },
            {
                "id": 3,
                "descricao": "Beneficios ambientais e economicos alcancados",
                "indicadores": [
                    {"id": 4, "descricao": "Valor financeiro economizado em razao da transformacao digital"},
                    {"id": 5, "descricao": "Quantidade de CO2 evitado em razao da transformacao digital"},
                ],
            },
        ],
    },
    {
        "id": 2,
        "descricao": "2- Melhorar qualidade dos servicos publicos",
        "resultados": [
            {
                "id": 4,
                "descricao": "Qualidade dos servicos publicos aprimorada",
                "indicadores": [
                    {"id": 6, "descricao": "Media da nota obtida na avaliacao da satisfacao do cidadao com os servicos"},
                    {"id": 7, "descricao": "Tempo medio de atendimento de demandas do cidadao"},
                ],
            },
        ],
    },
    {
        "id": 3,
        "descricao": "3- Implementar identidade e autenticacao unicas",
        "resultados": [
            {
                "id": 5,
                "descricao": "Identificacao e autenticacao unicas implementadas",
                "indicadores": [
                    {"id": 8, "descricao": "N de sistemas autenticados via Portal RJ Digital"},
                    {"id": 9, "descricao": "N de identificacoes unicas realizadas"},
                ],
            },
        ],
    },
    {
        "id": 4,
        "descricao": "4- Fortalecer seguranca e privacidade digital",
        "resultados": [
            {
                "id": 6,
                "descricao": "Seguranca da informacao e privacidade de dados fortalecidas",
                "indicadores": [
                    {"id": 10, "descricao": "% de orgaos e entidades com nivel de maturidade intermediario ou avancado em seguranca da informacao"},
                    {"id": 11, "descricao": "% de orgaos e entidades com nivel de maturidade intermediario ou avancado na implementacao da LGPD"},
                ],
            },
        ],
    },
    {
        "id": 5,
        "descricao": "5- Utilizar dados para decisoes publicas",
        "resultados": [
            {
                "id": 7,
                "descricao": "Compartilhamento e interoperabilidade de dados ampliados",
                "indicadores": [
                    {"id": 12, "descricao": "N de sistemas integrados recebendo dados de repositorio central de dados"},
                ],
            },
            {
                "id": 8,
                "descricao": "Produtos de dados e analises desenvolvidos",
                "indicadores": [
                    {"id": 13, "descricao": "% de orgaos e entidades com nivel de maturidade intermediario ou avancado em governanca de dados"},
                ],
            },
        ],
    },
    {
        "id": 6,
        "descricao": "6- Modernizar infraestrutura de governo digital",
        "resultados": [
            {
                "id": 9,
                "descricao": "Integracao tecnologica entre Estado e municipios fortalecida",
                "indicadores": [
                    {"id": 14, "descricao": "% de municipios com solucoes fornecidas pelo Estado"},
                ],
            },
        ],
    },
    {
        "id": 7,
        "descricao": "7- Fomentar inovacao em governo digital",
        "resultados": [
            {
                "id": 10,
                "descricao": "Ecossistema de inovacao em governo digital desenvolvido",
                "indicadores": [
                    {"id": 15, "descricao": "Indice de maturidade do ecossistema de inovacao"},
                ],
            },
        ],
    },
    {
        "id": 8,
        "descricao": "8- Otimizar processos organizacionais publicos",
        "resultados": [
            {
                "id": 11,
                "descricao": "Processos organizacionais otimizados",
                "indicadores": [
                    {"id": 16, "descricao": "Tempo medio dos processos (em dias)"},
                    {"id": 17, "descricao": "Custo medio dos processos (em reais)"},
                    {"id": 18, "descricao": "N de sistemas e servicos integrados ao sistema SEI"},
                    {"id": 19, "descricao": "% de municipios com tempo de abertura de empresas inferior a 15 horas"},
                ],
            },
        ],
    },
    {
        "id": 9,
        "descricao": "9- Ampliar transparencia e controle social",
        "resultados": [
            {
                "id": 12,
                "descricao": "Abertura e transparencia governamental ampliadas",
                "indicadores": [
                    {"id": 20, "descricao": "N de conjuntos de dados disponibilizados no Portal de Dados Abertos"},
                    {"id": 21, "descricao": "N de orgaos/entidades/municipios que disponibilizam dados no Portal de Dados Abertos"},
                ],
            },
            {
                "id": 13,
                "descricao": "Participacao e controle social fortalecidos",
                "indicadores": [
                    {"id": 22, "descricao": "N de manifestacoes do cidadao na Ouvidoria RJ"},
                ],
            },
        ],
    },
    {
        "id": 10,
        "descricao": "10- Capacitar servidores em governo digital",
        "resultados": [
            {
                "id": 14,
                "descricao": "Competencias em governo digital e inovacao desenvolvidas nos servidores",
                "indicadores": [
                    {"id": 23, "descricao": "N de servidores capacitados"},
                ],
            },
        ],
    },
    {
        "id": 11,
        "descricao": "11- Desenvolver cidadania digital no RJ",
        "resultados": [
            {
                "id": 15,
                "descricao": "Competencias digitais desenvolvidas nos cidadaos",
                "indicadores": [
                    {"id": 24, "descricao": "N de cidadaos capacitados"},
                ],
            },
            {
                "id": 16,
                "descricao": "Engajamento do cidadao com o Portal RJ Digital ampliado",
                "indicadores": [
                    {"id": 25, "descricao": "N de cidadaos acessando o Portal RJ Digital"},
                    {"id": 26, "descricao": "N de cidadaos demandando servicos no Portal RJ Digital"},
                ],
            },
        ],
    },
]


def get_objetivos_choices():
    return [{"id": objetivo["id"], "descricao": objetivo["descricao"]} for objetivo in GOAL_CATALOG]


def get_resultados_por_objetivo():
    return {
        objetivo["id"]: [{"id": resultado["id"], "descricao": resultado["descricao"]} for resultado in objetivo["resultados"]]
        for objetivo in GOAL_CATALOG
    }


def get_indicadores_por_resultado():
    mapping = {}
    for objetivo in GOAL_CATALOG:
        for resultado in objetivo["resultados"]:
            mapping[resultado["id"]] = [{"id": indicador["id"], "descricao": indicador["descricao"]} for indicador in resultado["indicadores"]]
    return mapping


RESULTADOS_POR_OBJETIVO = get_resultados_por_objetivo()
INDICADORES_POR_RESULTADO = get_indicadores_por_resultado()

RESULTADO_PARA_OBJETIVO = {
    resultado["id"]: objetivo["id"]
    for objetivo in GOAL_CATALOG
    for resultado in objetivo["resultados"]
}

INDICADOR_PARA_RESULTADO = {
    indicador["id"]: resultado["id"]
    for objetivo in GOAL_CATALOG
    for resultado in objetivo["resultados"]
    for indicador in resultado["indicadores"]
}

OBJETIVO_IDS = set(objetivo["id"] for objetivo in GOAL_CATALOG)
RESULTADO_IDS = set(RESULTADO_PARA_OBJETIVO.keys())
INDICADOR_IDS = set(INDICADOR_PARA_RESULTADO.keys())


def get_resultados_for_objetivo(objetivo_id):
    return list(RESULTADOS_POR_OBJETIVO.get(objetivo_id, []))


def get_indicadores_for_resultado(resultado_id):
    return list(INDICADORES_POR_RESULTADO.get(resultado_id, []))


def _parse_optional_int(value, field_name):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} invalido.") from exc


def normalize_goal_selection(objetivo_id, resultado_esperado_id, indicador_ids, max_indicadores=MAX_INDICADORES_POR_PROJETO):
    """
    Normaliza e valida selecao de objetivo/resultado/indicadores.

    Retorna:
        tuple(objetivo_id_normalizado, resultado_id_normalizado, lista_indicadores_normalizada)
    """
    objetivo_id = _parse_optional_int(objetivo_id, "Objetivo")
    resultado_esperado_id = _parse_optional_int(resultado_esperado_id, "Resultado esperado")

    if objetivo_id is not None and objetivo_id not in OBJETIVO_IDS:
        raise ValueError("Objetivo selecionado nao existe no catalogo.")

    if resultado_esperado_id is not None and resultado_esperado_id not in RESULTADO_IDS:
        raise ValueError("Resultado esperado selecionado nao existe no catalogo.")

    normalized_indicadores = []
    if indicador_ids is None:
        indicador_ids = []
    if not isinstance(indicador_ids, (list, tuple)):
        indicador_ids = [indicador_ids]

    for raw_indicador in indicador_ids:
        if raw_indicador in (None, ""):
            continue
        indicador_id = _parse_optional_int(raw_indicador, "Indicador")
        if indicador_id not in INDICADOR_IDS:
            raise ValueError("Indicador selecionado nao existe no catalogo.")
        if indicador_id not in normalized_indicadores:
            normalized_indicadores.append(indicador_id)

    if len(normalized_indicadores) > max_indicadores:
        raise ValueError(f"Voce pode selecionar no maximo {max_indicadores} indicadores.")

    if resultado_esperado_id is None and normalized_indicadores:
        resultados_dos_indicadores = {INDICADOR_PARA_RESULTADO[ind_id] for ind_id in normalized_indicadores}
        if len(resultados_dos_indicadores) > 1:
            raise ValueError("Os indicadores selecionados pertencem a resultados diferentes.")
        resultado_esperado_id = resultados_dos_indicadores.pop()

    if resultado_esperado_id is not None:
        objetivo_do_resultado = RESULTADO_PARA_OBJETIVO[resultado_esperado_id]
        if objetivo_id is None:
            objetivo_id = objetivo_do_resultado
        elif objetivo_id != objetivo_do_resultado:
            raise ValueError("O resultado esperado selecionado nao pertence ao objetivo informado.")

    if normalized_indicadores and resultado_esperado_id is None:
        raise ValueError("Selecione um resultado esperado para os indicadores.")

    for indicador_id in normalized_indicadores:
        if INDICADOR_PARA_RESULTADO[indicador_id] != resultado_esperado_id:
            raise ValueError("Um ou mais indicadores nao pertencem ao resultado esperado selecionado.")

    if resultado_esperado_id is None:
        normalized_indicadores = []

    return objetivo_id, resultado_esperado_id, normalized_indicadores


def sync_goal_catalog_to_db(commit=True):
    """
    Sincroniza catalogo canonico nas tabelas objetivo/resultado_esperado/indicador.

    - Mantem IDs fixos para compatibilidade entre ambientes.
    - Nao remove registros extras existentes.
    """
    from models import db, Objetivo, ResultadoEsperado, Indicador

    summary = {
        "objetivos_created": 0,
        "objetivos_updated": 0,
        "resultados_created": 0,
        "resultados_updated": 0,
        "indicadores_created": 0,
        "indicadores_updated": 0,
    }

    objetivos_by_id = {item.id: item for item in Objetivo.query.all()}
    for objetivo in GOAL_CATALOG:
        db_objetivo = objetivos_by_id.get(objetivo["id"])
        if db_objetivo is None:
            db.session.add(Objetivo(id=objetivo["id"], descricao=objetivo["descricao"]))
            summary["objetivos_created"] += 1
        elif db_objetivo.descricao != objetivo["descricao"]:
            db_objetivo.descricao = objetivo["descricao"]
            summary["objetivos_updated"] += 1

    db.session.flush()

    resultados_by_id = {item.id: item for item in ResultadoEsperado.query.all()}
    for objetivo in GOAL_CATALOG:
        objetivo_id = objetivo["id"]
        for resultado in objetivo["resultados"]:
            db_resultado = resultados_by_id.get(resultado["id"])
            if db_resultado is None:
                db.session.add(
                    ResultadoEsperado(
                        id=resultado["id"],
                        descricao=resultado["descricao"],
                        objetivo_id=objetivo_id,
                    )
                )
                summary["resultados_created"] += 1
            else:
                changed = False
                if db_resultado.descricao != resultado["descricao"]:
                    db_resultado.descricao = resultado["descricao"]
                    changed = True
                if db_resultado.objetivo_id != objetivo_id:
                    db_resultado.objetivo_id = objetivo_id
                    changed = True
                if changed:
                    summary["resultados_updated"] += 1

    db.session.flush()

    indicadores_by_id = {item.id: item for item in Indicador.query.all()}
    for objetivo in GOAL_CATALOG:
        for resultado in objetivo["resultados"]:
            resultado_id = resultado["id"]
            for indicador in resultado["indicadores"]:
                db_indicador = indicadores_by_id.get(indicador["id"])
                if db_indicador is None:
                    db.session.add(
                        Indicador(
                            id=indicador["id"],
                            descricao=indicador["descricao"],
                            resultado_esperado_id=resultado_id,
                        )
                    )
                    summary["indicadores_created"] += 1
                else:
                    changed = False
                    if db_indicador.descricao != indicador["descricao"]:
                        db_indicador.descricao = indicador["descricao"]
                        changed = True
                    if db_indicador.resultado_esperado_id != resultado_id:
                        db_indicador.resultado_esperado_id = resultado_id
                        changed = True
                    if changed:
                        summary["indicadores_updated"] += 1

    if commit:
        db.session.commit()

    return summary
