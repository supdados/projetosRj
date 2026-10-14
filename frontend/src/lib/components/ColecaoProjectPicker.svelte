<script lang="ts">
	/**
	 * Checklist multi-select de projetos para coleções: busca server-side em
	 * GET /api/projetos?q= (debounce) + lista com meta "área · N etapas".
	 * REUTILIZÁVEL: passo 2 do modal "Nova coleção" e "Adicionar projetos" da
	 * página interna. A seleção é CONTROLADA pelo pai (`selecionados` +
	 * `onchange`).
	 *
	 * A lista abre só com projetos Vigentes (o que costuma entrar numa coleção);
	 * o switch "Mostrar todos" pede `status: ''` e traz Finalizado/Suspenso, que
	 * ganham bolinha de status (cor + tooltip) na linha. O filtro é server-side
	 * como a busca: com `per_page` 100, filtrar no cliente deixaria vigentes fora
	 * da página.
	 * Selecionado que o filtro esconderia fica fixado no topo
	 * (`pinSelectedProjects`). A exclusão dos já-membros também é do servidor,
	 * via `colecaoId` (`excluir_colecao`), para não filtrar em cima de uma única
	 * página. `exclude` fica como reforço client-side (esconde na hora, sem
	 * esperar o refetch).
	 */
	import { onMount } from 'svelte';
	import { fetchProjects } from '$lib/api/projects';
	import type { Project } from '$lib/types/entities';
	import type { ProjectsListQuery } from '$lib/types/projects';
	import { projectStatusDotClass } from '$lib/utils/projectLabels';
	import { pinSelectedProjects } from '$lib/utils/pinnedPickerSelection';

	interface Props {
		/** Ids marcados (estado controlado pelo pai). */
		selecionados: number[];
		/** Coleção de destino: seus projetos saem da lista server-side. */
		colecaoId?: number;
		/** Ids ocultados da lista (já estão na coleção). */
		exclude?: number[];
		/** Recebe a lista COMPLETA de ids a cada toque. */
		onchange: (ids: number[]) => void;
		/** Total de projetos disponíveis (sem filtro de busca) — para "N de M". */
		ontotal?: (total: number) => void;
		/**
		 * Cresce até o fim do pai — que precisa ser uma coluna flex de altura
		 * definida — em vez do teto fixo de 15rem; a lista rola por dentro.
		 * Só a partir de `md`: empilhado no mobile o teto continua valendo,
		 * senão 100 projetos esticariam a página inteira.
		 */
		preencher?: boolean;
		/**
		 * Abre com "Mostrar todos" ligado — ex.: sugestão de IA, que pode
		 * pré-marcar projetos encerrados e precisa exibi-los para revisão.
		 */
		mostrarTodosInicial?: boolean;
	}

	let {
		selecionados,
		colecaoId,
		exclude = [],
		onchange,
		ontotal,
		preencher = false,
		mostrarTodosInicial = false
	}: Props = $props();

	const DEBOUNCE_MS = 300;
	const PER_PAGE = 100;

	let term = $state('');
	let mostrarTodos = $state(false);
	let projetos = $state<Project[]>([]);
	// Todo projeto já visto numa busca: base para fixar selecionados escondidos.
	const conhecidos = new Map<number, Project>();
	let carregando = $state(true);
	let erro = $state(false);
	let debounceTimer: ReturnType<typeof setTimeout> | null = null;
	let abortController: AbortController | null = null;
	// Token de geração: resposta atrasada de um termo anterior não pode vencer.
	let gen = 0;

	const selecionadosSet = $derived(new Set(selecionados));
	const excludeSet = $derived(new Set(exclude));
	const visiveis = $derived(projetos.filter((p) => !excludeSet.has(p.id)));
	const ehVigente = (projeto: Project): boolean => projeto.status === 'Vigente';
	const temOutrosStatus = $derived(visiveis.some((p) => !ehVigente(p)));

	async function buscar(q: string): Promise<void> {
		const minhaGen = ++gen;
		abortController?.abort();
		abortController = new AbortController();
		carregando = true;
		erro = false;
		try {
			const query: ProjectsListQuery = {
				status: mostrarTodos ? '' : 'Vigente',
				per_page: PER_PAGE
			};
			if (q) query.q = q;
			if (colecaoId !== undefined) query.excluir_colecao = colecaoId;
			const data = await fetchProjects(query, abortController.signal);
			if (minhaGen !== gen) return;
			for (const projeto of data.projetos) conhecidos.set(projeto.id, projeto);
			// Com busca ativa vale só o que casa com o termo (comportamento de busca).
			projetos = q ? data.projetos : pinSelectedProjects(data.projetos, selecionados, conhecidos);
			if (!q) ontotal?.(data.pagination.total);
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

	function definirMostrarTodos(valor: boolean): void {
		mostrarTodos = valor;
		// Busca pendente no debounce sai já, com o termo atual e o novo filtro.
		if (debounceTimer) clearTimeout(debounceTimer);
		debounceTimer = null;
		void buscar(term.trim());
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
		mostrarTodos = mostrarTodosInicial;
		void buscar('');
		return () => {
			if (debounceTimer) clearTimeout(debounceTimer);
			abortController?.abort();
		};
	});
</script>

<div class="flex flex-col gap-2 {preencher ? 'md:min-h-0 md:flex-1' : ''}">
	<div class="flex items-center gap-2">
		<div class="relative min-w-0 flex-1">
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
		<!-- Mesmo switch do "Só eu" do modal Nova coleção; o rótulo inteiro é clicável. -->
		<button
			type="button"
			role="switch"
			aria-checked={mostrarTodos}
			onclick={() => definirMostrarTodos(!mostrarTodos)}
			title="Inclui projetos finalizados e suspensos"
			class="inline-flex h-[var(--control-h-md)] shrink-0 items-center gap-2.5 rounded-control border border-border-subtle bg-surface px-3 text-sm font-medium transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-brand {mostrarTodos
				? 'text-text-primary'
				: 'text-text-secondary'}"
		>
			Mostrar todos
			<span
				class="grid h-5 w-9 shrink-0 items-center rounded-full transition-colors duration-fast {mostrarTodos
					? 'bg-brand'
					: 'bg-border-strong'}"
				aria-hidden="true"
			>
				<span
					class="h-3.5 w-3.5 rounded-full bg-surface-elevated shadow-sm transition-transform duration-fast {mostrarTodos
						? 'translate-x-[1.125rem]'
						: 'translate-x-[0.1875rem]'}"
				></span>
			</span>
		</button>
	</div>

	<div
		class="overflow-hidden rounded-control border border-border-subtle {preencher
			? 'md:flex md:min-h-0 md:flex-1 md:flex-col'
			: ''}"
	>
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
			<div class="flex flex-col items-center gap-2 px-3 py-4 text-center">
				<p class="text-sm text-text-muted">
					{#if term.trim()}
						Nenhum projeto{mostrarTodos ? '' : ' vigente'} encontrado para "{term.trim()}".
					{:else}
						Nenhum projeto{mostrarTodos ? '' : ' vigente'} disponível.
					{/if}
				</p>
				{#if !mostrarTodos}
					<!-- Atalho para o switch: o vazio pode ser só o filtro de status. -->
					<button
						type="button"
						onclick={() => definirMostrarTodos(true)}
						class="text-sm font-semibold text-brand hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
					>
						{term.trim() ? 'Buscar também nos finalizados e suspensos' : 'Mostrar todos'}
					</button>
				{/if}
			</div>
		{:else}
			<ul
				role="listbox"
				aria-multiselectable="true"
				aria-label="Projetos disponíveis"
				class="thin-scroll max-h-60 overflow-y-auto {preencher
					? 'md:max-h-none md:min-h-0 md:flex-1'
					: ''}"
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
							<!-- Bolinha só no que foge do padrão (vigente é o caso comum); a coluna
							     é reservada em toda linha quando a lista mistura status, para a
							     meta continuar alinhada à direita. Tooltip no padrão do Gantt, aberto
							     à ESQUERDA: acima, a rolagem da lista o cortaria na primeira linha. -->
							{#if temOutrosStatus}
								<span class="group/dot relative grid h-4 w-4 shrink-0 place-items-center">
									{#if !ehVigente(projeto)}
										<span
											class="h-2 w-2 rounded-full {projectStatusDotClass(projeto.status)}"
											aria-hidden="true"
										></span>
										<span class="sr-only">Status: {projeto.status}</span>
										<span
											class="pointer-events-none invisible absolute right-full top-1/2 z-20 mr-1.5 w-max -translate-y-1/2 rounded-md border border-border-subtle bg-surface-elevated px-2 py-1 text-xs font-medium text-text-primary opacity-0 shadow-popover transition-opacity duration-fast group-hover/dot:visible group-hover/dot:opacity-100"
											aria-hidden="true"
										>
											{projeto.status}
										</span>
									{/if}
								</span>
							{/if}
						</button>
					</li>
				{/each}
			</ul>
		{/if}
	</div>
</div>
