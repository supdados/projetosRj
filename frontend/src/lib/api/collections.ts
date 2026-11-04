/**
 * Acesso tipado às "Coleções" (pastas pessoais de projetos), em
 * `routes/api/collections.py` — Fase 1 + Fase 2 do plano
 * (`docs/analise-pastas-personalizadas.md` §6):
 *
 *   GET    /api/colecoes                                   -> { colecoes }  (minhas, depois compartilhadas)
 *   POST   /api/colecoes                                   -> { colecao }   (criação atômica, `compartilhamentos?`)
 *   PUT    /api/colecoes/<id>                               -> { colecao }
 *   DELETE /api/colecoes/<id>                               -> ok
 *   GET    /api/colecoes/<id>/projetos                      -> { colecao, projetos }
 *   POST   /api/colecoes/<id>/projetos                      -> ok (idempotente no duplicado)
 *   DELETE /api/colecoes/<id>/projetos/<pid>                -> ok
 *   POST   /api/projetos/<id>/favorito                      -> { favorito } (toggle)
 *   GET    /api/colecoes/<id>/compartilhamentos              -> { compartilhamentos } (só dono)
 *   POST   /api/colecoes/<id>/compartilhamentos              -> { compartilhamento } (upsert de papel, só dono)
 *   DELETE /api/colecoes/<id>/compartilhamentos/<sid>        -> ok (só dono)
 *   POST   /api/colecoes/<id>/compartilhamentos/<sid>/reenviar -> { reconvidados, compartilhamento } (só dono)
 *   GET    /api/colecoes/<id>/cronograma                     -> { projetos } (Gantt, etapas de workflow)
 *   GET    /api/colecoes/convites                            -> { convites } (pendentes, só metadados)
 *   GET    /api/colecoes/<id>/convite                        -> { convite } (404 idêntico sem convite)
 *   POST   /api/colecoes/<id>/convite/aceitar                -> { status, colecao }
 *   POST   /api/colecoes/<id>/convite/recusar                -> { status }
 *   POST   /api/colecoes/<id>/sair                           -> { status, itens_removidos }
 *   GET    /api/colecoes/destinatarios?q=                    -> { usuarios } (busca de pessoas)
 *   GET    /api/colecoes/sugestoes                           -> lote em cache (nunca chama o modelo)
 *   POST   /api/colecoes/sugestoes                           -> gera e persiste o lote (IA; 503 = desligada)
 *   POST   /api/colecoes/sugestoes/<id>/descartar            -> ok (404 = já sumiu)
 *
 * Falhas chegam como `ApiClientError` (`client.ts`) com `code`/`status`:
 *   - 404 `not_found`  — coleção de outro usuário sem share, coleção inexistente
 *     OU projeto invisível ao ator: respondem o MESMO corpo (anti-enumeração,
 *     contrato S5);
 *   - 403 `forbidden`  — vê a coleção via share mas não tem papel para a ação
 *     (ex.: viewer tentando escrever, ou qualquer share tentando gerenciar
 *     compartilhamentos — isso é só do dono);
 *   - 422 `validation` — nome vazio/duplicado, ícone/cor fora da whitelist,
 *     limite de coleções atingido, mutação em Favoritos, ou XOR/papel
 *     inválido no compartilhamento;
 *   - 401 já redireciona para /login dentro do `client.ts`.
 *
 * Cache SWR próprio (índice, convites, página interna e cronograma): a tela
 * reabre com o último dado bom e revalida em silêncio. Toda escrita —
 * incluindo compartilhamento — invalida os caches de coleção: o rollup
 * (`projetos`/`etapas`/`progresso_pct`) e o cronograma mudam quando um item
 * entra ou sai de qualquer coleção, e `papel`/`destinatarios` do resumo mudam
 * com qualquer share.
 *
 * O cache de `projects.ts` também cai quando a escrita pode mudar QUAIS
 * projetos o ator enxerga: aceitar, sair, revogar ou rebaixar (a poda tira
 * itens), remover item e apagar a coleção (o dono deixa de derivar leitura dos
 * itens que editores incluíram) — e o toggle de favorito, que muda a estrela
 * servida na Lista de Projetos. Incluir projeto não muda a visibilidade de
 * quem inclui (ele já o vê pela própria área).
 *
 * Exemplo:
 *   const colecoes = await fetchColecoes();
 *   await toggleFavorito(42);
 *   await criarShare(7, { orgao_id: 3, papel: 'viewer' });
 */

import { get, post, put, del, ApiClientError } from './client';
import { createSwrCache } from './swrCache';
import { invalidateProjects } from './projects';
import type {
	AddProjectToCollectionPayload,
	ColecaoResumo,
	ColecaoShare,
	ColecaoShareCreatePayload,
	CollectionCreatePayload,
	CollectionCronogramaData,
	CollectionDetailData,
	CollectionMutationData,
	CollectionSharesData,
	CollectionShareMutationData,
	CollectionShareReenvioData,
	CollectionUpdatePayload,
	CollectionsListData,
	ConviteAceitoData,
	ConviteColecao,
	ConviteData,
	ConvitesListData,
	DestinatariosBuscaData,
	PessoaDestinavel,
	SaidaColecaoData,
	SugestoesResponse,
	ToggleFavoritoData
} from '$lib/types/collections';

// O índice não tem filtro server-side: chave única para a lista inteira.
const INDEX_KEY = '';

const colecoesCache = createSwrCache<ColecaoResumo[]>();
const convitesCache = createSwrCache<ConviteColecao[]>();
const colecaoDetailCache = createSwrCache<CollectionDetailData>();
const colecaoCronogramaCache = createSwrCache<CollectionCronogramaData>();

/**
 * Descarta índice + convites + páginas internas + cronograma (rollup e share
 * mudam em qualquer escrita). Exportado para quem soube de uma mudança por
 * fora (ex.: o sino viu um convite novo) re-buscar sem servir o stale.
 */
export function invalidateColecoes(): void {
	colecoesCache.invalidate();
	convitesCache.invalidate();
	colecaoDetailCache.invalidate();
	colecaoCronogramaCache.invalidate();
}

/** Escrita que muda QUAIS projetos o ator vê: derruba também a Lista de Projetos. */
function invalidateColecoesEProjetos(): void {
	invalidateColecoes();
	invalidateProjects();
}

/** O MESMO 404 anti-enumeração de "coleção/convite não está mais aqui". */
function ehNaoEncontrado(err: unknown): boolean {
	return err instanceof ApiClientError && (err.status === 404 || err.code === 'not_found');
}

/**
 * Resposta a convite / saída: derruba os caches no sucesso E no 404. O 404
 * ("não está mais disponível") quer dizer que o estado mudou por fora —
 * revogado, respondido em outra aba —, e servir o SWR antigo traria de volta
 * o convite morto ou o card de uma coleção que a pessoa já perdeu.
 */
async function invalidandoTambemNo404<T>(acao: () => Promise<T>): Promise<T> {
	try {
		const resultado = await acao();
		invalidateColecoesEProjetos();
		return resultado;
	} catch (err) {
		if (ehNaoEncontrado(err)) invalidateColecoesEProjetos();
		throw err;
	}
}

/** Último índice carregado, ou null (síncrono, 1º render). */
export function peekColecoes(): ColecaoResumo[] | null {
	return colecoesCache.peek(INDEX_KEY);
}

/** Última página interna carregada da coleção, ou null (síncrono, 1º render). */
export function peekColecaoProjetos(collectionId: number): CollectionDetailData | null {
	return colecaoDetailCache.peek(String(collectionId));
}

/** Último cronograma carregado da coleção, ou null (síncrono, 1º render). */
export function peekColecaoCronograma(collectionId: number): CollectionCronogramaData | null {
	return colecaoCronogramaCache.peek(String(collectionId));
}

// Flag do servidor (GET /api/colecoes); null = índice ainda não carregado.
let iaSugestoesDisponivel: boolean | null = null;

/** Sugestões por IA habilitadas no servidor, ou null antes do 1º índice. */
export function peekIaSugestoesDisponivel(): boolean | null {
	return iaSugestoesDisponivel;
}

/** Coleções do usuário; Favoritos vem get-or-create do backend, sempre em 1º. */
export async function fetchColecoes(signal?: AbortSignal): Promise<ColecaoResumo[]> {
	const data = await get<CollectionsListData>('/api/colecoes', signal);
	colecoesCache.store(INDEX_KEY, data.colecoes);
	iaSugestoesDisponivel = data.ia_disponivel;
	return data.colecoes;
}

/**
 * Cria a coleção com identidade e itens de UMA vez (os 2 passos do modal viram
 * 1 chamada). `project_ids` omitido = coleção vazia; `compartilhamentos`
 * omitido = coleção nasce "Só eu".
 */
export async function criarColecao(payload: CollectionCreatePayload): Promise<ColecaoResumo> {
	const data = await post<CollectionMutationData>('/api/colecoes', payload);
	invalidateColecoes();
	return data.colecao;
}

/** Edita nome/descrição/ícone/cor; 422 `validation` quando a coleção é Favoritos. */
export async function editarColecao(
	collectionId: number,
	payload: CollectionUpdatePayload
): Promise<ColecaoResumo> {
	const data = await put<CollectionMutationData>(`/api/colecoes/${collectionId}`, payload);
	invalidateColecoes();
	return data.colecao;
}

/** Apaga a coleção (projetos ficam intactos); 422 `validation` em Favoritos. */
export async function apagarColecao(collectionId: number): Promise<void> {
	await del<unknown>(`/api/colecoes/${collectionId}`);
	invalidateColecoesEProjetos();
}

/** Coleção + linhas de projeto visíveis ao ator (página interna). */
export async function fetchColecaoProjetos(
	collectionId: number,
	signal?: AbortSignal
): Promise<CollectionDetailData> {
	const data = await get<CollectionDetailData>(`/api/colecoes/${collectionId}/projetos`, signal);
	colecaoDetailCache.store(String(collectionId), data);
	return data;
}

/** Adiciona um projeto à coleção; repetir o mesmo id é no-op no backend. */
export async function adicionarProjeto(collectionId: number, projectId: number): Promise<void> {
	const payload: AddProjectToCollectionPayload = { project_id: projectId };
	await post<unknown>(`/api/colecoes/${collectionId}/projetos`, payload);
	invalidateColecoes();
}

/**
 * Remove o projeto da coleção (o projeto em si não é tocado). Editor só remove o
 * que incluiu (403 `forbidden` no resto); a linha traz `pode_remover` pronto.
 */
export async function removerProjeto(collectionId: number, projectId: number): Promise<void> {
	await del<unknown>(`/api/colecoes/${collectionId}/projetos/${projectId}`);
	invalidateColecoesEProjetos();
}

/**
 * Alterna a estrela do projeto e devolve o estado NOVO — o cliente nunca
 * precisa saber o id da coleção Favoritos.
 */
export async function toggleFavorito(projectId: number): Promise<boolean> {
	const data = await post<ToggleFavoritoData>(`/api/projetos/${projectId}/favorito`);
	invalidateColecoes();
	// A estrela vem no payload da Lista de Projetos: sem isso ela volta errada.
	invalidateProjects();
	return data.favorito;
}

/**
 * Compartilhamentos da coleção (só o dono enxerga a rota; sem cache — tela de
 * gestão) + `itens_orfaos`: itens de quem já não é editor, que saem em
 * QUALQUER próxima poda. Backend sem o campo conta 0.
 *
 * Exemplo:
 *   const { compartilhamentos, itens_orfaos } = await fetchShares(7);
 */
export async function fetchShares(
	collectionId: number,
	signal?: AbortSignal
): Promise<Required<CollectionSharesData>> {
	const data = await get<CollectionSharesData>(
		`/api/colecoes/${collectionId}/compartilhamentos`,
		signal
	);
	return { compartilhamentos: data.compartilhamentos, itens_orfaos: data.itens_orfaos ?? 0 };
}

/**
 * Convida (share novo nasce PENDENTE e notifica) ou faz upsert do papel no
 * compartilhamento existente da mesma pessoa/área — sem nova notificação.
 * Rebaixar editor→leitor tira da coleção os projetos que o destinatário incluiu.
 */
export async function criarShare(
	collectionId: number,
	payload: ColecaoShareCreatePayload
): Promise<ColecaoShare> {
	const data = await post<CollectionShareMutationData>(
		`/api/colecoes/${collectionId}/compartilhamentos`,
		payload
	);
	invalidateColecoesEProjetos();
	return data.compartilhamento;
}

/**
 * Revoga um compartilhamento: o acesso derivado do destinatário some na hora e
 * os projetos que ele incluiu saem da coleção (`itens_incluidos` do share).
 */
export async function revogarShare(collectionId: number, shareId: number): Promise<void> {
	await del<unknown>(`/api/colecoes/${collectionId}/compartilhamentos/${shareId}`);
	invalidateColecoesEProjetos();
}

/**
 * Reconvida quem recusou ou saiu daquele compartilhamento (só o dono) e devolve
 * o share já com o status novo. 422 `validation` quando não há ninguém a
 * reconvidar.
 *
 * Exemplo:
 *   const { compartilhamento } = await reenviarShare(7, share.id);
 */
export async function reenviarShare(
	collectionId: number,
	shareId: number
): Promise<CollectionShareReenvioData> {
	const data = await post<CollectionShareReenvioData>(
		`/api/colecoes/${collectionId}/compartilhamentos/${shareId}/reenviar`
	);
	invalidateColecoes();
	return data;
}

/** Último lote de convites pendentes carregado, ou null (síncrono, 1º render). */
export function peekConvites(): ConviteColecao[] | null {
	return convitesCache.peek(INDEX_KEY);
}

/** Convites PENDENTES do usuário logado (só metadados), mais recentes primeiro. */
export async function fetchConvites(signal?: AbortSignal): Promise<ConviteColecao[]> {
	const data = await get<ConvitesListData>('/api/colecoes/convites', signal);
	convitesCache.store(INDEX_KEY, data.convites);
	return data.convites;
}

/**
 * Convite pendente DESTA coleção para mim — fallback da página interna quando
 * `.../projetos` responde 404. Sem convite, o MESMO 404 de coleção inexistente.
 */
export async function fetchConvite(
	collectionId: number,
	signal?: AbortSignal
): Promise<ConviteColecao> {
	const data = await get<ConviteData>(`/api/colecoes/${collectionId}/convite`, signal);
	return data.convite;
}

/**
 * Aceita o convite (todos os shares pendentes da coleção que me alcançam) e
 * devolve o card já com o papel novo. Duplo clique ou convite revogado no meio
 * → 404 `not_found` (que também derruba os caches).
 */
export async function aceitarConvite(collectionId: number): Promise<ColecaoResumo> {
	const data = await invalidandoTambemNo404(() =>
		post<ConviteAceitoData>(`/api/colecoes/${collectionId}/convite/aceitar`)
	);
	return data.colecao;
}

/** Recusa o convite; o dono é avisado e só ele pode reenviar. Sem convite → 404. */
export async function recusarConvite(collectionId: number): Promise<void> {
	await invalidandoTambemNo404(() =>
		post<unknown>(`/api/colecoes/${collectionId}/convite/recusar`)
	);
}

/**
 * Sai da coleção (quem aceitou ou tinha acesso legado) e devolve quantos
 * projetos incluídos por mim saíram junto. Dono ou pendente → 404.
 */
export async function sairDaColecao(collectionId: number): Promise<number> {
	const data = await invalidandoTambemNo404(() =>
		post<SaidaColecaoData>(`/api/colecoes/${collectionId}/sair`)
	);
	return data.itens_removidos;
}

/**
 * Pessoas para compartilhar, por NOME (aberta a qualquer logado; até 20, sem
 * o próprio usuário nem inativos). Termo com menos de 2 caracteres nem sai
 * para a rede.
 *
 * Exemplo:
 *   const pessoas = await buscarDestinatarios('mar', controller.signal);
 */
export async function buscarDestinatarios(
	q: string,
	signal?: AbortSignal
): Promise<PessoaDestinavel[]> {
	const termo = q.trim();
	if (termo.length < 2) return [];
	const data = await get<DestinatariosBuscaData>(
		`/api/colecoes/destinatarios?q=${encodeURIComponent(termo)}`,
		signal
	);
	return data.usuarios;
}

/**
 * Lote de sugestões em cache (`docs/plano-ia-fase2-cache-sugestoes.md` §3.3):
 * resposta instantânea, NUNCA chama o modelo. Sem lote pendente vem
 * `sugestoes: []` com `gerado_em: null` — a UI mostra o CTA de gerar em vez de
 * disparar o POST sozinha.
 *
 * Exemplo:
 *   const { sugestoes, desatualizado } = await getSugestoes(controller.signal);
 */
export async function getSugestoes(signal?: AbortSignal): Promise<SugestoesResponse> {
	return get<SugestoesResponse>('/api/colecoes/sugestoes', signal);
}

/**
 * Gera um lote NOVO com o modelo e o persiste, substituindo o pendente
 * (`docs/plano-ia-fase2-cache-sugestoes.md` §3.3). Operação cara (~1min,
 * cobrada por chamada): só rodar em clique explícito. Nenhuma coleção é criada
 * — o aceite passa por `criarColecao` com `sugestao_id`, que revalida tudo.
 *
 * Falhas úteis à UI: 503 `sugestoes_indisponiveis` (feature desligada — use
 * `isSugestoesIndisponivel` e esconda a entrada) e 502 (falha do modelo, vale
 * "Tentar novamente").
 *
 * Exemplo:
 *   const { sugestoes, projetos } = await sugerirColecoes(controller.signal);
 */
export async function sugerirColecoes(signal?: AbortSignal): Promise<SugestoesResponse> {
	return post<SugestoesResponse>('/api/colecoes/sugestoes', undefined, signal);
}

/**
 * Descarta a sugestão de vez: o agrupamento não volta em gerações futuras.
 * 404 significa que a linha já sumiu (outra aba regenerou) — quem chama trata
 * como sucesso e some com o cartão.
 */
export async function descartarSugestao(sugestaoId: number): Promise<void> {
	await post<unknown>(`/api/colecoes/sugestoes/${sugestaoId}/descartar`);
}

/** Sugestões desligadas no servidor (sem credencial de IA) — a UI some com o botão. */
export function isSugestoesIndisponivel(err: unknown): boolean {
	if (!(err instanceof ApiClientError)) return false;
	return err.status === 503 || err.code === 'sugestoes_indisponiveis';
}

/** Cronograma (Gantt) das etapas de workflow dos projetos da coleção. */
export async function fetchCronograma(
	collectionId: number,
	signal?: AbortSignal
): Promise<CollectionCronogramaData> {
	const data = await get<CollectionCronogramaData>(
		`/api/colecoes/${collectionId}/cronograma`,
		signal
	);
	colecaoCronogramaCache.store(String(collectionId), data);
	return data;
}
