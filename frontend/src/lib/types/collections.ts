/**
 * Tipos de "Coleções" (pastas pessoais de projetos), `routes/api/collections.py`.
 *
 * Espelham `ColecaoResumo`/`ProjetoColecaoRow` do contrato fixo (ver
 * `docs/analise-pastas-personalizadas.md` §5/§6 e `docs/parecer-design-colecoes.md`)
 * — Fase 1 (coleções pessoais + Favoritos) + Fase 2 (compartilhamento com
 * concessão de acesso e cronograma) + convite com aceite e curadoria (o share
 * novo nasce pendente; editor inclui e remove só o que incluiu). O envelope
 * `{ok, data}` é desempacotado por `client.ts`; os tipos abaixo descrevem
 * apenas `data`.
 *
 * `icone`/`cor` são whitelists fechadas validadas no backend (`@validates`);
 * o cliente NUNCA envia hex cru — `cor` é NOME de família da régua de cor
 * (`docs/guia-de-estilo-visual.md` §2), com dark mode grátis.
 */

/** Ids do registry `collectionIcons.ts` — únicos ícones aceitos pelo backend. */
export type CollectionIconId =
	| 'camadas'
	| 'servidores'
	| 'pessoas'
	| 'documento'
	| 'estrela'
	| 'rede'
	| 'capacitacao'
	| 'calendario'
	| 'dados'
	| 'indicadores'
	| 'seguranca'
	| 'orgao';

/** Famílias de cor da régua aceitas para coleção (nunca hex; dark desloca sozinho). */
export type CollectionColorId = 'primary' | 'success' | 'warning' | 'attention' | 'danger' | 'neutral';

/** Tipo de coleção: `favoritos` é a coleção de sistema (1 por usuário, get-or-create). */
export type ColecaoTipo = 'custom' | 'favoritos';

/** Papel do ator NESTA coleção: dono sempre; viewer/editor só via compartilhamento. */
export type PapelColecao = 'dono' | 'viewer' | 'editor';

/** Papel concedível num compartilhamento (dono nunca é papel de share — é implícito). */
export type PapelCompartilhamento = 'viewer' | 'editor';

/** Alvo mínimo `{id, nome}` — usuário destinatário de um compartilhamento ou dono de coleção alheia. */
export interface ColecaoShareUsuario {
	id: number;
	nome: string;
}

/** Alvo mínimo `{id, nome, sigla}` — órgão destinatário de um compartilhamento. */
export interface ColecaoShareOrgao {
	id: number;
	nome: string;
	sigla: string;
}

/**
 * Compartilhamento de uma coleção com uma pessoa OU um órgão (exatamente um
 * dos dois — `user_id`/`orgao_id` são XOR; `user`/`orgao` espelham o mesmo
 * XOR já resolvido para exibição, sem 2ª chamada).
 */
export interface ColecaoShare {
	id: number;
	user_id: number | null;
	orgao_id: number | null;
	papel: PapelCompartilhamento;
	/** ISO 8601. */
	created_at: string;
	user: ColecaoShareUsuario | null;
	orgao: ColecaoShareOrgao | null;
	/** `false` = share anterior ao aceite (legado): vale sem resposta do destinatário. */
	exige_aceite: boolean;
	/** Situação do convite — SÓ em share de pessoa (`null` em share de órgão). */
	status: StatusConvite | null;
	/** Agregado por pessoa lotada — SÓ em share de órgão (`null` em share de pessoa). */
	resumo: ResumoShareOrgao | null;
	/**
	 * Projetos que SAEM da coleção se este share for revogado (incluídos por
	 * quem perde o papel). Não conta os órfãos (`CollectionSharesData.itens_orfaos`).
	 */
	itens_incluidos: number;
}

/**
 * Situação do convite de UMA pessoa num share (`GET .../compartilhamentos`).
 * `legado` = share anterior ao aceite, vale sem resposta; `pendente` ainda não
 * concede nada; `recusado`/`saiu` só voltam por "Reenviar" do dono.
 */
export type StatusConvite = 'pendente' | 'aceito' | 'recusado' | 'saiu' | 'legado';

/** Contagem das pessoas lotadas no órgão de um share de área (`aceitos` inclui legado). */
export interface ResumoShareOrgao {
	membros: number;
	aceitos: number;
	pendentes: number;
	recusados: number;
	sairam: number;
}

/**
 * Resumo de uma coleção com rollup agregado (`collection_rollups`), usado no
 * índice (`GET /api/colecoes`) e devolvido pelas mutações de coleção.
 *
 * `progresso_pct` = % de etapas concluídas (arredondado), NUNCA mistura com
 * tarefas. Favoritos: `tipo === 'favoritos'`, não renomeável/deletável.
 *
 * `papel` é o papel do ATOR nesta coleção (nunca `'dono'` para coleções
 * compartilhadas comigo); `owner` é `null` quando `papel === 'dono'` (é eu
 * mesmo) e preenchido para coleções compartilhadas comigo/minha área.
 */
export interface ColecaoResumo {
	id: number;
	nome: string;
	descricao: string | null;
	icone: CollectionIconId;
	cor: CollectionColorId;
	tipo: ColecaoTipo;
	/** Contagem de projetos VISÍVEIS ao ator (`COUNT(DISTINCT project_id)`). */
	projetos: number;
	etapas_total: number;
	etapas_concluidas: number;
	/** Começou (pela data), não concluída e no prazo — `services/atraso.py`. */
	etapas_em_andamento: number;
	/** Não concluída com fim vencido (mesmo critério do projeto "atrasado"). */
	etapas_atrasadas: number;
	progresso_pct: number;
	/** Áreas dos projetos visíveis, mais projetos primeiro (pílula "N áreas" da capa). */
	areas: AreaColecao[];
	/** ISO 8601. */
	created_at: string;
	/** ISO 8601, `null` em linha legada; bumpado à mão nas mutações de item. */
	updated_at: string | null;
	papel: PapelColecao;
	/** Tem ≥ 1 share de qualquer status (sempre `true` para quem participa). */
	compartilhada: boolean;
	owner: ColecaoShareUsuario | null;
}

/** Uma área da coleção: sigla do órgão dos projetos (`null` = projeto sem órgão). */
export interface AreaColecao {
	sigla: string | null;
	projetos: number;
}

/**
 * Linha de projeto na página interna de uma coleção
 * (`GET /api/colecoes/<id>/projetos`), serializada por
 * `serialize_project_collection_row` (molde: `serialize_pending_project_row`).
 *
 * `status` é o rótulo de status de fluxo já resolvido no backend (pílula da
 * tabela); `atrasado` é um indicador booleano ORTOGONAL ao status — nunca um
 * 5º valor de status (`docs/guia-de-estilo-visual.md` §2, regra "Status de
 * fluxo").
 */
export interface ProjetoColecaoRow {
	id: number;
	nome: string;
	orgao_sigla: string | null;
	etapas_concluidas: number;
	etapas_total: number;
	tarefas_concluidas: number;
	tarefas_total: number;
	progresso_pct: number;
	/** ISO YYYY-MM-DD; `null` = sem data definida. */
	data_inicio: string | null;
	/** ISO YYYY-MM-DD; `null` = sem data definida. */
	data_fim: string | null;
	status: string;
	atrasado: boolean;
	/** Quem incluiu o projeto; `null` = item anterior à autoria (conta como do dono). */
	adicionado_por: ColecaoIncluidor | null;
	/** Decidido no servidor: dono remove tudo, editor só o que incluiu, leitor nada. */
	pode_remover: boolean;
}

/** Autor da inclusão de um item — `{id, name}` (sic: `name`, não `nome`, como no backend). */
export interface ColecaoIncluidor {
	id: number;
	name: string;
}

/** Carga de GET /api/colecoes (já desempacotada). Favoritos sempre presente e primeiro. */
export interface CollectionsListData {
	colecoes: ColecaoResumo[];
	/** Sugestões por IA habilitadas no servidor (credenciais watsonx presentes). */
	ia_disponivel: boolean;
}

/** Carga de GET /api/colecoes/<id>/projetos (já desempacotada). */
export interface CollectionDetailData {
	colecao: ColecaoResumo;
	projetos: ProjetoColecaoRow[];
	/** Projetos incluídos pelo ator que saem junto se ele sair (0 para o dono). */
	itens_incluidos_por_mim: number;
	/** Órfãos que também saem se ele sair — ver `CollectionSharesData.itens_orfaos`. */
	itens_orfaos?: number;
}

/** Estado da barra no Gantt: backend decide, cliente só pinta. */
export type BarraEtapa = 'concluida' | 'execucao' | 'vencida' | 'prevista';

/**
 * Etapa de workflow no cronograma (`GET /api/colecoes/<id>/cronograma`).
 * Etapas de reunião (`google_meeting`) e sem data ficam fora do array — a
 * 2ª conta em `CronogramaProjeto.sem_data`.
 */
export interface CronogramaEtapa {
	id: number;
	nome: string;
	/** ISO YYYY-MM-DD; `null` só teoricamente — etapa sem data não entra no array. */
	data_inicio: string | null;
	data_fim: string | null;
	barra: BarraEtapa;
}

/** Linha de projeto no Gantt da coleção. */
export interface CronogramaProjeto {
	id: number;
	nome: string;
	orgao_sigla: string | null;
	/** Quantas etapas de workflow ficaram fora de `etapas` por falta de data. */
	sem_data: number;
	etapas: CronogramaEtapa[];
}

/** Carga de GET /api/colecoes/<id>/cronograma (já desempacotada). */
export interface CollectionCronogramaData {
	projetos: CronogramaProjeto[];
}

/** Carga de POST/PUT /api/colecoes[/<id>] (já desempacotada). */
export interface CollectionMutationData {
	colecao: ColecaoResumo;
}

/**
 * Corpo de POST /api/colecoes/<id>/compartilhamentos (e item do array
 * `compartilhamentos` na criação). `user_id`/`orgao_id` são XOR — o cliente
 * envia SÓ um dos dois, nunca os dois nem nenhum.
 */
export type ColecaoShareCreatePayload =
	| { user_id: number; orgao_id?: never; papel: PapelCompartilhamento }
	| { user_id?: never; orgao_id: number; papel: PapelCompartilhamento };

/**
 * Corpo de POST /api/colecoes — criação ATÔMICA (fluxo de 2 passos do modal
 * = 1 chamada só). `project_ids` omitido/vazio = coleção criada sem itens.
 * `compartilhamentos` omitido/vazio = coleção nasce "Só eu" (default).
 */
export interface CollectionCreatePayload {
	nome: string;
	descricao?: string | null;
	icone: CollectionIconId;
	cor: CollectionColorId;
	project_ids?: number[];
	compartilhamentos?: ColecaoShareCreatePayload[];
	/**
	 * Sugestão de IA que originou a coleção — o backend marca aquela linha como
	 * aceita (bookkeeping best-effort: id inválido nunca derruba a criação).
	 */
	sugestao_id?: number;
}

/** Corpo de PUT /api/colecoes/<id> — 422 no backend se a coleção for Favoritos. */
export interface CollectionUpdatePayload {
	nome?: string;
	descricao?: string | null;
	icone?: CollectionIconId;
	cor?: CollectionColorId;
}

/** Corpo de POST /api/colecoes/<id>/projetos. */
export interface AddProjectToCollectionPayload {
	project_id: number;
}

/** Carga de POST /api/projetos/<id>/favorito (já desempacotada) — toggle. */
export interface ToggleFavoritoData {
	favorito: boolean;
}

/**
 * Coleção PROPOSTA por IA (`GET`/`POST /api/colecoes/sugestoes`) — a linha
 * existe no banco (lote pendente), mas NENHUMA coleção foi criada: é rascunho
 * que o usuário aceita pelo fluxo normal de criação
 * (`docs/plano-ia-fase2-cache-sugestoes.md` §3).
 *
 * `id` é a linha persistida — vai no descarte e no `sugestao_id` do aceite.
 * `justificativa` é obrigatória e fica SEMPRE visível na UI (transparência de
 * origem por IA). `project_ids` já vem validado contra os projetos visíveis ao
 * ator (mín. 2; ids alucinados caem no backend). `icone`/`cor` não são pedidos
 * ao modelo — o usuário escolhe no aceite.
 */
export interface ColecaoSugerida {
	id: number;
	nome: string;
	descricao: string | null;
	justificativa: string;
	project_ids: number[];
}

/** Projeto analisado pela IA — resolve título dos chips sem busca extra. */
export interface ProjetoAnalisado {
	id: number;
	titulo: string;
}

/**
 * Carga de GET/POST /api/colecoes/sugestoes (já desempacotada) — o MESMO shape
 * nos dois verbos: o GET serve o lote em cache (nunca chama o modelo) e o POST
 * gera um lote novo.
 *
 * `gerado_em`/`lote_id` são `null` quando não há lote pendente (`sugestoes`
 * vazio): a UI mostra o CTA "Gerar sugestões" e NÃO dispara o POST sozinha.
 * `desatualizado` = a carteira de projetos mudou desde a geração — banner
 * não-bloqueante, as sugestões antigas continuam válidas para aceite.
 */
export interface SugestoesResponse {
	sugestoes: ColecaoSugerida[];
	projetos: ProjetoAnalisado[];
	/** ISO 8601 (UTC, sufixo `Z`); `null` = nenhum lote em cache. */
	gerado_em: string | null;
	lote_id: string | null;
	desatualizado: boolean;
}

/** Carga de GET /api/colecoes/<id>/compartilhamentos (já desempacotada; só dono). */
export interface CollectionSharesData {
	compartilhamentos: ColecaoShare[];
	/**
	 * Itens ÓRFÃOS: incluídos por quem (não dono) já não tem papel editor
	 * efetivo — desativado, mudou de área. Saem em QUALQUER próxima poda
	 * (revogar, sair, recusar, rebaixar), seja qual for o share mexido, e por
	 * isso NÃO entram no `itens_incluidos` de nenhum share (sem dupla contagem).
	 * Opcional: backend anterior ao campo conta 0.
	 */
	itens_orfaos?: number;
}

/** Carga de POST /api/colecoes/<id>/compartilhamentos (já desempacotada; upsert de papel). */
export interface CollectionShareMutationData {
	compartilhamento: ColecaoShare;
}

/** Carga de POST /api/colecoes/<id>/compartilhamentos/<sid>/reenviar (só dono). */
export interface CollectionShareReenvioData {
	/** Pessoas que voltaram a ficar pendentes (recusaram ou saíram antes). */
	reconvidados: number;
	compartilhamento: ColecaoShare;
}

/**
 * Convite PENDENTE de coleção (`GET /api/colecoes/convites` e `.../convite`):
 * só metadados — nenhum projeto, contagem ou cronograma antes do aceite.
 * `id` é o da COLEÇÃO (aceite/recusa resolvem por coleção × usuário logado);
 * pessoa + área na mesma coleção viram UM convite com o papel mais alto.
 */
export interface ConviteColecao {
	id: number;
	nome: string;
	descricao: string | null;
	icone: CollectionIconId;
	cor: CollectionColorId;
	/** Dono vivo; `null` só em drift. */
	owner: ColecaoShareUsuario | null;
	papel: PapelCompartilhamento;
	/** ISO 8601 (UTC). */
	convidado_em: string | null;
}

/** Carga de GET /api/colecoes/convites (já desempacotada), mais recentes primeiro. */
export interface ConvitesListData {
	convites: ConviteColecao[];
}

/** Carga de GET /api/colecoes/<id>/convite (404 idêntico sem convite para mim). */
export interface ConviteData {
	convite: ConviteColecao;
}

/** Carga de POST /api/colecoes/<id>/convite/aceitar: card já com o papel novo. */
export interface ConviteAceitoData {
	status: 'aceito';
	colecao: ColecaoResumo;
}

/** Carga de POST /api/colecoes/<id>/sair. */
export interface SaidaColecaoData {
	status: 'saiu';
	/** Projetos incluídos pelo ator que saíram junto. */
	itens_removidos: number;
}

/**
 * Pessoa encontrada pela busca do compartilhamento (`GET /api/colecoes/destinatarios`).
 * Sem `username` de propósito: pode ser o CPF, e a busca é aberta a qualquer logado.
 */
export interface PessoaDestinavel {
	id: number;
	name: string;
	orgao_sigla: string | null;
}

/** Carga de GET /api/colecoes/destinatarios?q= (já desempacotada). */
export interface DestinatariosBuscaData {
	usuarios: PessoaDestinavel[];
}
