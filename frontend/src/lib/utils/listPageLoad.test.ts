/** Exercita os loaders reais das três páginas sem iniciar navegador. */
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';
import { describe, expect, it, vi } from 'vitest';

type Query = Record<string, string | number | boolean | null | undefined>;
interface Listing {
	marker: string;
	filters: Record<string, string | null>;
	pagination: { page: number };
	filtro_periodo: string; search_query: string; selected_responsavel: string;
	selected_priority: string; selected_orgao: string | null;
}

function listing(marker: string): Listing {
	return { marker, filters: {}, pagination: { page: 1 }, filtro_periodo: 'atrasados',
		search_query: '', selected_responsavel: '', selected_priority: '', selected_orgao: null };
}

function pageLoader(route: string) {
	const source = readFileSync(new URL(`../../routes/(app)/${route}/+page.svelte`, import.meta.url), 'utf8');
	const script = source.slice(source.indexOf('>') + 1, source.indexOf('</script>'));
	const parsed = ts.createSourceFile('page.ts', script, ts.ScriptTarget.Latest, true);
	const load = parsed.statements.find((node) => ts.isFunctionDeclaration(node) && node.name?.text === 'load');
	if (!load) throw new Error('Loader ausente');
	const code = ts.transpileModule(load.getText(parsed), { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;
	const cache = new Map<string, Listing>();
	const peek = (query: Query) => cache.get(JSON.stringify(query)) ?? null;
	const state = {
		data: null as Listing | null, loadState: 'loading', errorMessage: '',
		inFlight: null as AbortController | null, AbortController, Error,
		ApiClientError: class TestApiError extends Error { code = ''; },
		search: '', orgao: null as string | null, page: 1, listPage: 1, project: '',
		periodo: 'atrasados', responsavel: '', prioridade: '', apenasOrgao: false,
		DEFAULT_STATUS: 'Vigente', status: 'Vigente', deliveryType: '', atraso: '', objetivo: '',
		colecao: '', specialProject: '', abepIndicator: '', favoritoOverrides: {}, focusDelta: 0,
		syncAbepLabelFromValue: vi.fn(), syncUrlFromFilters: vi.fn(), flash: { danger: vi.fn() },
		buildProjectsQuery: (): Query => ({ search: state.search, page: state.page }),
		buildActiveQuery: (): Query => ({ search: state.search, page: state.page }),
		peekProjects: peek, peekPendentes: peek, peekTarefas: peek,
		load: async (): Promise<void> => {},
		fetchProjects: vi.fn<(query: Query, signal?: AbortSignal) => Promise<Listing>>(),
		fetchPendentes: vi.fn<(query: Query, signal?: AbortSignal) => Promise<Listing>>(),
		fetchTarefas: vi.fn<(query: Query, signal?: AbortSignal) => Promise<Listing>>()
	};
	const fetch = route === 'projetos' ? state.fetchProjects : route === 'tarefas' ? state.fetchTarefas : state.fetchPendentes;
	fetch.mockImplementation(async (query) => {
		const result = listing(`resultado ${state.search}`);
		cache.set(JSON.stringify(query), result);
		return result;
	});
	runInNewContext(`${code}\nthis.load = load;`, state);
	return { state, fetch };
}

describe.each(['projetos', 'projetos/pendentes', 'tarefas'])('P2-12: %s', (route) => {
	it('filtro sem cache seguido de erro termina e permite retry', async () => {
		const { state, fetch } = pageLoader(route);
		await state.load();
		state.search = 'novo filtro';
		fetch.mockRejectedValueOnce(new Error('falha de rede'));
		await state.load();
		expect(state.loadState).toBe('error');
		expect(state.data).toBeNull();
		expect(state.errorMessage).toBe('falha de rede');
		await state.load();
		expect(state.loadState).toBe('ready');
		expect(state.data?.marker).toBe('resultado novo filtro');
	});

	it('falha da revalidação da mesma consulta mantém os dados em ready', async () => {
		const { state, fetch } = pageLoader(route);
		await state.load();
		const previous = state.data;
		fetch.mockRejectedValueOnce(new Error('falha de rede'));
		await state.load();
		expect(state.loadState).toBe('ready');
		expect(state.data).toBe(previous);
		expect(state.flash.danger).toHaveBeenCalled();
	});
});
