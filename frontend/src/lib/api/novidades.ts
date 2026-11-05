/**
 * Cliente das Novidades (`routes/api/novidades.py`), no envelope canônico.
 *
 *   GET  /api/novidades                                  -> { novidades }
 *   POST /api/novidades/<slug>/vista        {concluida}  -> { slug, concluida }
 *   GET  /api/admin/novidades                            -> { novidades, usuarios_ativos }
 *   PUT  /api/admin/novidades/<slug>        {ativa}      -> { novidade }
 *   POST /api/admin/novidades/<slug>/mostrar-de-novo     -> { removidas }
 *
 * Ex.: `await marcarNovidadeVista('colecoes-2026-11', true)`.
 */
import { get, getQuiet, post, put } from '$lib/api/client';
import type { NovidadeResumo, NovidadesAdminData } from '$lib/types/novidades';

const BASE = '/api/novidades';
const BASE_ADMIN = '/api/admin/novidades';

/**
 * Novidades ativas de quem está logado. Silenciosa (`getQuiet`): falhar aqui
 * não pode virar toast de erro em toda tela — sem resposta, sem modal.
 */
export async function fetchNovidades(signal?: AbortSignal): Promise<NovidadeResumo[]> {
	const data = await getQuiet<{ novidades: NovidadeResumo[] }>(BASE, signal);
	return data.novidades;
}

export async function marcarNovidadeVista(slug: string, concluida: boolean): Promise<void> {
	await post<unknown>(`${BASE}/${encodeURIComponent(slug)}/vista`, {
		concluida
	});
}

export function fetchNovidadesAdmin(signal?: AbortSignal): Promise<NovidadesAdminData> {
	return get<NovidadesAdminData>(BASE_ADMIN, signal);
}

export async function definirNovidadeAtiva(slug: string, ativa: boolean): Promise<void> {
	await put<unknown>(`${BASE_ADMIN}/${encodeURIComponent(slug)}`, { ativa });
}

/** Apaga as vistas: a novidade volta a abrir sozinha para todos. Devolve quantas saíram. */
export async function mostrarNovidadeDeNovo(slug: string): Promise<number> {
	const data = await post<{ removidas: number }>(
		`${BASE_ADMIN}/${encodeURIComponent(slug)}/mostrar-de-novo`
	);
	return data.removidas;
}
