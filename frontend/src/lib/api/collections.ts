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
 *   GET    /api/colecoes/<id>/cronograma                     -> { projetos } (Gantt, etapas de workflow)
 *
 * Falhas chegam como `ApiClientError` (`client.ts`) com `code`/`status`:
 *   - 404 `not_found`  — coleção de outro usuário sem share, coleção inexistente
 *     OU projeto invisível ao ator: respondem o MESMO corpo (anti-enumeração,
 *     contrato S5);
 *   - 403 `forbidden`  — vê a coleção via share mas não tem papel para a ação
 *     (ex.: viewer tentando escrever, ou qualquer share tentando gerenciar
 *     compartilhamentos — isso é só do dono);
 *   - 422 `validation` — nome vazio/duplicado, ícone/cor fora da whitelist,
 *     limite de coleções/itens atingido, mutação em Favoritos, ou XOR/papel
 *     inválido no compartilhamento;
 *   - 401 já redireciona para /login dentro do `client.ts`.
 *
 * Cache SWR próprio (índice, página interna e cronograma): a tela reabre com o
 * último dado bom e revalida em silêncio. Toda escrita — incluindo
 * compartilhamento — invalida os TRÊS caches: o rollup (`projetos`/`etapas`/
 * `progresso_pct`) e o cronograma mudam quando um item entra ou sai de
 * qualquer coleção, e `compartilhada`/`papel`/`owner` do resumo mudam com
 * qualquer share. As mutações de coleção NÃO tocam o cache de `projects.ts`
 * (coleção não altera o projeto em si) — exceto o toggle de favorito, que
 * muda a estrela servida na Lista de Projetos.
 *
 * Exemplo:
 *   const colecoes = await fetchColecoes();
 *   await toggleFavorito(42);
 *   await criarShare(7, { orgao_id: 3, papel: 'viewer' });
 */

import { get, post, put, del } from './client';
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
	CollectionUpdatePayload,
	CollectionsListData,
	ToggleFavoritoData
} from '$lib/types/collections';

// O índice não tem filtro server-side: chave única para a lista inteira.
const INDEX_KEY = '';

const colecoesCache = createSwrCache<ColecaoResumo[]>();
const colecaoDetailCache = createSwrCache<CollectionDetailData>();
const colecaoCronogramaCache = createSwrCache<CollectionCronogramaData>();

/** Descarta índice + páginas internas + cronograma (rollup e share mudam em qualquer escrita). */
function invalidateColecoes(): void {
	colecoesCache.invalidate();
	colecaoDetailCache.invalidate();
	colecaoCronogramaCache.invalidate();
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

/** Coleções do usuário; Favoritos vem get-or-create do backend, sempre em 1º. */
export async function fetchColecoes(signal?: AbortSignal): Promise<ColecaoResumo[]> {
	const data = await get<CollectionsListData>('/api/colecoes', signal);
	colecoesCache.store(INDEX_KEY, data.colecoes);
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
	invalidateColecoes();
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

/** Remove o projeto da coleção (o projeto em si não é tocado). */
export async function removerProjeto(collectionId: number, projectId: number): Promise<void> {
	await del<unknown>(`/api/colecoes/${collectionId}/projetos/${projectId}`);
	invalidateColecoes();
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

/** Compartilhamentos da coleção (só o dono enxerga a rota; sem cache — tela de gestão). */
export async function fetchShares(
	collectionId: number,
	signal?: AbortSignal
): Promise<ColecaoShare[]> {
	const data = await get<CollectionSharesData>(
		`/api/colecoes/${collectionId}/compartilhamentos`,
		signal
	);
	return data.compartilhamentos;
}

/** Cria (ou faz upsert de papel no compartilhamento existente) para a mesma pessoa/área. */
export async function criarShare(
	collectionId: number,
	payload: ColecaoShareCreatePayload
): Promise<ColecaoShare> {
	const data = await post<CollectionShareMutationData>(
		`/api/colecoes/${collectionId}/compartilhamentos`,
		payload
	);
	invalidateColecoes();
	return data.compartilhamento;
}

/** Revoga um compartilhamento — acesso derivado do destinatário some na hora. */
export async function revogarShare(collectionId: number, shareId: number): Promise<void> {
	await del<unknown>(`/api/colecoes/${collectionId}/compartilhamentos/${shareId}`);
	invalidateColecoes();
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
