/**
 * Estado das Novidades na sessão: a lista que o backend devolveu e qual está
 * aberta. O `NovidadesHost` carrega depois do login e decide o que abrir
 * (`lib/novidades/selecao.ts`); o botão do topo só lê.
 *
 * Fechar marca como vista de forma OTIMISTA (o ponto do botão some na hora) e
 * só então avisa o servidor; se a chamada falhar, a novidade volta no próximo
 * login — melhor que travar a pessoa num modal que não fecha.
 *
 * Ex.: `await novidades.carregar(); novidades.abrir('colecoes-2026-11');`
 */
import { get, writable, type Readable } from 'svelte/store';
import { fetchNovidades, marcarNovidadeVista } from '$lib/api/novidades';
import { comoVista } from '$lib/novidades/selecao';
import type { NovidadeResumo } from '$lib/types/novidades';

export interface NovidadeAberta {
	slug: string;
	/** Pré-visualização do admin: fechar não conta como vista. */
	previa: boolean;
}

export interface EstadoNovidades {
	itens: NovidadeResumo[];
	aberta: NovidadeAberta | null;
	carregada: boolean;
}

export interface NovidadesStore extends Readable<EstadoNovidades> {
	/** Busca as ativas; falha vira lista vazia (sem modal, sem toast de erro). */
	carregar: () => Promise<NovidadeResumo[]>;
	abrir: (slug: string, previa?: boolean) => void;
	/** Fecha a aberta; fora da prévia, conta como vista (`concluida` = chegou ao fim). */
	fechar: (concluida: boolean) => Promise<void>;
	/** Logout/troca de usuário: esquece tudo. */
	limpar: () => void;
}

const INICIAL: EstadoNovidades = { itens: [], aberta: null, carregada: false };

export function createNovidadesStore(
	buscar: typeof fetchNovidades = fetchNovidades,
	marcar: typeof marcarNovidadeVista = marcarNovidadeVista
): NovidadesStore {
	const store = writable<EstadoNovidades>(INICIAL);

	async function carregar(): Promise<NovidadeResumo[]> {
		let itens: NovidadeResumo[] = [];
		try {
			itens = await buscar();
		} catch {
			// Sem resposta = sem novidade nesta sessão; nunca um erro na cara da pessoa.
			itens = [];
		}
		store.update((estado) => ({ ...estado, itens, carregada: true }));
		return itens;
	}

	function abrir(slug: string, previa = false): void {
		store.update((estado) => ({ ...estado, aberta: { slug, previa } }));
	}

	async function fechar(concluida: boolean): Promise<void> {
		const aberta = get(store).aberta;
		if (!aberta) return;
		store.update((estado) => ({
			...estado,
			aberta: null,
			itens: aberta.previa ? estado.itens : comoVista(estado.itens, aberta.slug)
		}));
		if (aberta.previa) return;
		try {
			await marcar(aberta.slug, concluida);
		} catch {
			// Otimista: a falha só faz a novidade reaparecer no próximo login.
		}
	}

	function limpar(): void {
		store.set(INICIAL);
	}

	return { subscribe: store.subscribe, carregar, abrir, fechar, limpar };
}

export const novidades = createNovidadesStore();
