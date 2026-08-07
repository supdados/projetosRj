<script lang="ts">
	/**
	 * Checklist multi-select de projetos para coleções: busca server-side em
	 * GET /api/projetos?q= (debounce) + lista com meta "área · N etapas".
	 * REUTILIZÁVEL: passo 2 do modal "Nova coleção" e "Adicionar projetos" da
	 * página interna. A seleção é CONTROLADA pelo pai (`selecionados` +
	 * `onchange`).
	 *
	 * A lista pede `status: ''` (todos os status — sem isso o backend defaulta
	 * "Vigente" e projetos Finalizado/Suspenso ficariam inadicionáveis) e delega
	 * a exclusão dos já-membros ao servidor via `colecaoId` (`excluir_colecao`),
	 * para não filtrar em cima de uma única página. `exclude` fica como reforço
	 * client-side (esconde na hora, sem esperar o refetch).
	 */
	import { onMount } from 'svelte';
	import { fetchProjects } from '$lib/api/projects';
	import type { Project } from '$lib/types/entities';
	import type { ProjectsListQuery } from '$lib/types/projects';

	interface Props {
		/** Ids marcados (estado controlado pelo pai). */
		selecionados: number[];
		/** Coleção de destino: seus projetos saem da lista server-side. */
		colecaoId?: number;
		/** Ids ocultados da lista (já estão na coleção). */
		exclude?: number[];
		/** Recebe a lista COMPLETA de ids a cada toque. */
		onchange: (ids: number[]) => void;
	}

	let { selecionados, colecaoId, exclude = [], onchange }: Props = $props();

	const DEBOUNCE_MS = 300;
	const PER_PAGE = 100;

	let term = $state('');
	let projetos = $state<Project[]>([]);
	let carregando = $state(true);
	let erro = $state(false);
	let debounceTimer: ReturnType<typeof setTimeout> | null = null;
	let abortController: AbortController | null = null;
	// Token de geração: resposta atrasada de um termo anterior não pode vencer.
	let gen = 0;

	const selecionadosSet = $derived(new Set(selecionados));
	const excludeSet = $derived(new Set(exclude));
	const visiveis = $derived(projetos.filter((p) => !excludeSet.has(p.id)));

	async function buscar(q: string): Promise<void> {
		const minhaGen = ++gen;
		abortController?.abort();
		abortController = new AbortController();
		carregando = true;
		erro = false;
		try {
			const query: ProjectsListQuery = { status: '', per_page: PER_PAGE };
			if (q) query.q = q;
			if (colecaoId !== undefined) query.excluir_colecao = colecaoId;
			const data = await fetchProjects(query, abortController.signal);
			if (minhaGen !== gen) return;
			projetos = data.projetos;
			carregando = false;
		} catch (err) {
			if (minhaGen !== gen) return;
			if (err instanceof DOMException && err.name === 'AbortError') return;
			erro = true;
			carregando = false;
		}
	}

	function onTermInput(): void {
		if (debounceTimer) clearTimeout(debounceTimer);
		debounceTimer = setTimeout(() => {
			debounceTimer = null;
			void buscar(term.trim());
		}, DEBOUNCE_MS);
	}

	function toggle(projectId: number): void {
		const proximos = selecionadosSet.has(projectId)
			? selecionados.filter((id) => id !== projectId)
			: [...selecionados, projectId];
		onchange(proximos);
	}

	function metaProjeto(projeto: Project): string {
		const area = projeto.orgao_sigla ?? projeto.orgao;
		const total = projeto.total_workflow_etapas;
		const etapas = `${total} ${total === 1 ? 'etapa' : 'etapas'}`;
		return area ? `${area} · ${etapas}` : etapas;
	}

	onMount(() => {
		void buscar('');
		return () => {
			if (debounceTimer) clearTimeout(debounceTimer);
			abortController?.abort();
		};
	});
</script>

<div class="flex flex-col gap-2">
	<div class="relative">
		<i
			class="fas fa-search pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-text-muted"
			aria-hidden="true"
		></i>
		<input
			type="search"
			bind:value={term}
			oninput={onTermInput}
			placeholder="Buscar por nome ou área"
			aria-label="Buscar projeto por nome ou área"
			autocomplete="off"
			class="h-[var(--control-h-md)] w-full rounded-control border border-border-strong bg-surface pl-9 pr-3 text-md text-text-primary placeholder:text-text-faint transition-colors duration-fast focus:border-brand focus:outline-none"
		/>
	</div>

	<div class="overflow-hidden rounded-control border border-border-subtle">
		{#if carregando}
			<p class="px-3 py-4 text-center text-sm text-text-muted" aria-live="polite">
				Carregando projetos…
			</p>
		{:else if erro}
			<div class="flex flex-col items-center gap-2 px-3 py-4 text-center">
				<p class="text-sm text-danger">Não foi possível carregar os projetos.</p>
				<button
					type="button"
					onclick={() => void buscar(term.trim())}
					class="text-sm font-semibold text-brand hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
				>
					Tentar novamente
				</button>
			</div>
		{:else if visiveis.length === 0}
			<p class="px-3 py-4 text-center text-sm text-text-muted">
				{term.trim()
					? `Nenhum projeto encontrado para "${term.trim()}".`
					: 'Nenhum projeto disponível.'}
			</p>
		{:else}
			<ul
				role="listbox"
				aria-multiselectable="true"
				aria-label="Projetos disponíveis"
				class="thin-scroll max-h-60 overflow-y-auto"
			>
				{#each visiveis as projeto (projeto.id)}
					{@const marcado = selecionadosSet.has(projeto.id)}
					<li
						role="option"
						aria-selected={marcado}
						class="border-b border-border-hairline last:border-b-0"
					>
						<button
							type="button"
							onclick={() => toggle(projeto.id)}
							class="flex w-full items-center gap-2.5 px-3 py-2.5 text-left transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand {marcado
								? 'bg-wash-brand'
								: 'hover:bg-surface-muted'}"
						>
							<span
								class="grid h-4 w-4 shrink-0 place-items-center rounded border transition-colors duration-fast {marcado
									? 'border-brand bg-brand'
									: 'border-border-strong bg-surface'}"
								aria-hidden="true"
							>
								{#if marcado}
									<svg
										width="10"
										height="10"
										viewBox="0 0 24 24"
										fill="none"
										stroke="currentColor"
										stroke-width="3.5"
										stroke-linecap="round"
										stroke-linejoin="round"
										class="text-on-brand"
									>
										<path d="M5 13l4.5 4.5L19 7" />
									</svg>
								{/if}
							</span>
							<span class="min-w-0 flex-1 truncate text-sm text-text-primary">{projeto.titulo}</span>
							<span class="shrink-0 pl-3 text-xs text-text-muted">{metaProjeto(projeto)}</span>
						</button>
					</li>
				{/each}
			</ul>
		{/if}
	</div>
</div>
