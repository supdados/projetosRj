<script lang="ts">
	/**
	 * Modal de exportação de projetos em CSV (`GET /api/projetos/exportar`):
	 * escopo (lista filtrada × todos), seleção de colunas persistida em
	 * `localStorage` e download via blob + `<a download>` programático.
	 */
	import { tick, untrack } from 'svelte';
	import { fade, slide } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';
	import { prefersReducedMotion } from 'svelte/motion';
	import { ApiClientError } from '$lib/api/client';
	import { exportarProjetosCsv, type ExportProjectsFile } from '$lib/api/projects';
	import { delayedPending } from '$lib/utils/delayedPending';
	import {
		EXPORT_COLUMNS,
		DEFAULT_SLUGS,
		loadStoredSlugs,
		saveStoredSlugs
	} from '$lib/utils/exportColumns';
	import type { ProjectsListQuery } from '$lib/types/projects';
	import Modal from '$lib/components/Modal.svelte';
	import Button from '$lib/components/Button.svelte';
	import StateBanner from '$lib/components/StateBanner.svelte';

	type EscopoExport = 'lista' | 'todos';
	type FaseExport = 'repouso' | 'gerando' | 'pronto';

	interface Props {
		open: boolean;
		filtros?: ProjectsListQuery;
		totalFiltrado?: number;
		hasFiltrosAtivos?: boolean;
		/** `false` esconde o escopo e exporta sempre todos os projetos. */
		permitirEscopoLista?: boolean;
		onClose: () => void;
	}

	let {
		open,
		filtros = {},
		totalFiltrado = 0,
		hasFiltrosAtivos = false,
		permitirEscopoLista = true,
		onClose
	}: Props = $props();

	let escopo = $state<EscopoExport>('todos');
	let slugs = $state<string[]>([...DEFAULT_SLUGS]);
	let fase = $state<FaseExport>('repouso');
	let falha = $state<boolean>(false);
	let falhaDetalhe = $state<string>('');
	let fecharTimer = $state<number | null>(null);
	let radioListaEl = $state<HTMLInputElement | null>(null);
	let radioTodosEl = $state<HTMLInputElement | null>(null);
	let montado = $state<boolean>(false);
	// Suprime o pop dos checks nas ações em lote (todas/limpar/padrão).
	let popPermitido = $state<boolean>(true);
	// Invalida continuações de um export antigo (modal fechado e reaberto).
	let sessaoExport = 0;

	const pendente = delayedPending({ showAfterMs: 150, minVisibleMs: 350 });

	const selecionadas = $derived(new Set(slugs));
	const rotuloRepouso = $derived(
		escopo === 'lista'
			? `Exportar ${totalFiltrado} ${totalFiltrado === 1 ? 'projeto' : 'projetos'}`
			: 'Exportar CSV'
	);
	const spanVisivel = $derived<FaseExport>(
		fase === 'pronto' ? 'pronto' : fase === 'gerando' && $pendente ? 'gerando' : 'repouso'
	);
	const rotuloEstado = $derived(
		spanVisivel === 'gerando' ? 'Gerando…' : spanVisivel === 'pronto' ? 'Pronto' : rotuloRepouso
	);

	// untrack: uma revalidação de `hasFiltrosAtivos` com o modal aberto não pode
	// resetar a seleção de colunas nem derrubar um export em voo.
	$effect(() => {
		if (!open) return;
		return untrack(() => {
			escopo = permitirEscopoLista && hasFiltrosAtivos ? 'lista' : 'todos';
			slugs = ordenarPeloRegistro(loadStoredSlugs());
			fase = 'repouso';
			falha = false;
			falhaDetalhe = '';
			montado = false;
			const quadro = requestAnimationFrame(() => (montado = true));
			if (permitirEscopoLista) void focarRadioSelecionado();
			return () => {
				sessaoExport += 1;
				cancelAnimationFrame(quadro);
				montado = false;
				pendente.reset();
				if (fecharTimer !== null) {
					clearTimeout(fecharTimer);
					fecharTimer = null;
				}
			};
		});
	});

	/** Lido via `untrack` de propósito: aplicar a classe reativamente faria a seleção já
	 * persistida dar pop na abertura — o pop só deve responder a um clique do usuário. */
	const classePop = (nome: string): string =>
		untrack(() => (montado && popPermitido ? nome : ''));

	async function focarRadioSelecionado(): Promise<void> {
		await tick();
		(escopo === 'lista' ? radioListaEl : radioTodosEl)?.focus();
	}

	/** Mantém a seleção na ordem canônica do registry (= ordem das colunas no CSV). */
	function ordenarPeloRegistro(selecao: readonly string[]): string[] {
		const escolhidos = new Set(selecao);
		return EXPORT_COLUMNS.filter((c) => escolhidos.has(c.slug)).map((c) => c.slug);
	}

	function atualizarSlugs(proximos: string[]): void {
		slugs = proximos;
		saveStoredSlugs(proximos);
	}

	function alternarColuna(slug: string): void {
		if (selecionadas.has(slug)) {
			atualizarSlugs(slugs.filter((s) => s !== slug));
			return;
		}
		atualizarSlugs(ordenarPeloRegistro([...slugs, slug]));
	}

	function aplicarEmLote(proximos: string[]): void {
		popPermitido = false;
		atualizarSlugs(proximos);
		void tick().then(() => (popPermitido = true));
	}

	function selecionarTodas(): void {
		aplicarEmLote(EXPORT_COLUMNS.map((c) => c.slug));
	}

	function limparColunas(): void {
		aplicarEmLote([]);
	}

	function montarParams(): URLSearchParams {
		const params = new URLSearchParams();
		if (escopo === 'lista') {
			if (filtros.status) params.set('status', filtros.status);
			if (filtros.prioridade) params.set('prioridade', filtros.prioridade);
			if (filtros.atraso) params.set('atraso', filtros.atraso);
			if (filtros.special_project) params.set('special_project', filtros.special_project);
			if (filtros.delivery_type) params.set('delivery_type', filtros.delivery_type);
			if (filtros.abep_indicator) params.set('abep_indicator', filtros.abep_indicator);
			if (filtros.objetivo) params.set('objetivo', filtros.objetivo);
			if (filtros.q) params.set('q', filtros.q);
			if (filtros.orgao != null) params.set('orgao', String(filtros.orgao));
			if (filtros.colecao != null) params.set('colecao', String(filtros.colecao));
			if (filtros.excluir_colecao != null) {
				params.set('excluir_colecao', String(filtros.excluir_colecao));
			}
		}
		params.set('colunas', slugs.join(','));
		return params;
	}

	function dispararDownload(arquivo: ExportProjectsFile): void {
		const url = URL.createObjectURL(arquivo.blob);
		const link = document.createElement('a');
		link.href = url;
		link.download = arquivo.filename;
		document.body.appendChild(link);
		link.click();
		link.remove();
		URL.revokeObjectURL(url);
	}

	/** Espera o spinner cumprir os 350ms mínimos antes de trocar para "Pronto". */
	function aguardarPendenteSumir(): Promise<void> {
		return new Promise((resolve) => {
			let liberar: () => void = () => {};
			liberar = pendente.subscribe((visivel) => {
				if (visivel) return;
				queueMicrotask(() => liberar());
				resolve();
			});
		});
	}

	async function exportar(): Promise<void> {
		if (fase !== 'repouso' || slugs.length === 0) return;
		const sessao = ++sessaoExport;
		falha = false;
		falhaDetalhe = '';
		fase = 'gerando';
		pendente.start();
		try {
			const arquivo = await exportarProjetosCsv(montarParams());
			pendente.stop();
			await aguardarPendenteSumir();
			if (sessao !== sessaoExport || !open) return;
			fase = 'pronto';
			dispararDownload(arquivo);
			fecharTimer = window.setTimeout(() => onClose(), 900);
		} catch (err) {
			pendente.stop();
			await aguardarPendenteSumir();
			if (sessao !== sessaoExport || !open) return;
			fase = 'repouso';
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			falhaDetalhe = err instanceof ApiClientError ? err.message : '';
			falha = true;
		}
	}

	function fechar(): void {
		onClose();
	}
</script>

<Modal {open} labelId="exportar-projetos-title" maxWidth="max-w-2xl" onBackdrop={fechar} onEscape={fechar}>
		<div class="flex flex-col gap-4">
			<h2 id="exportar-projetos-title" class="font-heading text-xl font-bold text-text-primary">
				Exportar projetos
			</h2>

			{#if permitirEscopoLista}
				<fieldset class="flex flex-col gap-1.5">
					<legend class="mb-1.5 text-2xs font-bold uppercase tracking-caps text-text-label">
						Escopo
					</legend>
					<div class="flex items-center gap-5">
						<label
							class="inline-flex cursor-pointer items-center gap-2 rounded-sm focus-within:ring-2 focus-within:ring-brand focus-within:ring-offset-2"
						>
							<input
								bind:this={radioListaEl}
								type="radio"
								name="exportar-projetos-escopo"
								value="lista"
								checked={escopo === 'lista'}
								onchange={() => (escopo = 'lista')}
								class="sr-only"
							/>
							<span
								class="grid h-3.5 w-3.5 shrink-0 place-items-center rounded-full border {escopo === 'lista'
									? 'border-brand'
									: 'border-border-strong'}"
								aria-hidden="true"
							>
								<span
									class="export-dot h-2 w-2 rounded-full bg-brand"
									style:transform={escopo === 'lista' ? 'scale(1)' : 'scale(0)'}
								></span>
							</span>
							<span
								class="text-sm {escopo === 'lista'
									? 'font-medium text-text-primary'
									: 'text-text-secondary'}"
							>
								Lista filtrada atual
							</span>
						</label>
						<label
							class="inline-flex cursor-pointer items-center gap-2 rounded-sm focus-within:ring-2 focus-within:ring-brand focus-within:ring-offset-2"
						>
							<input
								bind:this={radioTodosEl}
								type="radio"
								name="exportar-projetos-escopo"
								value="todos"
								checked={escopo === 'todos'}
								onchange={() => (escopo = 'todos')}
								class="sr-only"
							/>
							<span
								class="grid h-3.5 w-3.5 shrink-0 place-items-center rounded-full border {escopo === 'todos'
									? 'border-brand'
									: 'border-border-strong'}"
								aria-hidden="true"
							>
								<span
									class="export-dot h-2 w-2 rounded-full bg-brand"
									style:transform={escopo === 'todos' ? 'scale(1)' : 'scale(0)'}
								></span>
							</span>
							<span
								class="text-sm {escopo === 'todos'
									? 'font-medium text-text-primary'
									: 'text-text-secondary'}"
							>
								Todos os projetos
							</span>
						</label>
					</div>
				</fieldset>
			{/if}

			<section
				class="flex flex-col gap-2 {permitirEscopoLista
					? 'border-t border-border-hairline pt-4'
					: ''}"
			>
				<div class="flex items-baseline justify-between">
					<span class="text-2xs font-bold uppercase tracking-caps text-text-label">Colunas</span>
					<span class="font-mono text-xs tabular-nums text-text-muted" aria-live="polite">
						<span aria-hidden="true">{slugs.length} de {EXPORT_COLUMNS.length}</span>
						<span class="sr-only">
							{slugs.length} de {EXPORT_COLUMNS.length} colunas selecionadas
						</span>
					</span>
				</div>
				<div class="flex items-center gap-2">
					<button
						type="button"
						onclick={selecionarTodas}
						class="rounded-sm text-xs text-brand hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
					>
						Selecionar todas
					</button>
					<span class="text-xs text-text-faint" aria-hidden="true">·</span>
					<button
						type="button"
						onclick={limparColunas}
						class="rounded-sm text-xs text-brand hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
					>
						Limpar
					</button>
				</div>
				<div class="grid grid-cols-3 gap-1.5">
					{#each EXPORT_COLUMNS as coluna (coluna.slug)}
						{@const ativa = selecionadas.has(coluna.slug)}
						<button
							type="button"
							aria-pressed={ativa}
							onclick={() => alternarColuna(coluna.slug)}
							class="inline-flex h-8 items-center gap-1.5 rounded-sm border px-2.5 text-xs font-medium transition-ui active:scale-[0.97] focus:outline-none focus-visible:ring-2 focus-visible:ring-brand {ativa
								? 'border-brand-soft bg-wash-brand text-brand'
								: 'border-border-subtle bg-surface text-text-secondary hover:border-brand hover:text-brand'}"
						>
							<span class="grid h-2.5 w-2.5 shrink-0 place-items-center" aria-hidden="true">
								{#if ativa}
									<svg
										class={classePop('export-check-pop')}
										width="10"
										height="10"
										viewBox="0 0 10 10"
										fill="none"
										out:fade={{ duration: prefersReducedMotion.current ? 0 : 100 }}
									>
										<path
											d="M1.5 5.5 4 8l4.5-6"
											stroke="currentColor"
											stroke-width="1.8"
											stroke-linecap="round"
											stroke-linejoin="round"
										/>
									</svg>
								{/if}
							</span>
							<span class="truncate">{coluna.label}</span>
						</button>
					{/each}
				</div>
				<p class="min-h-4 text-xs text-text-muted" aria-live="polite">
					{slugs.length === 0 ? 'Escolha ao menos uma coluna.' : ''}
				</p>
			</section>

			{#if falha}
				<div transition:slide={{ duration: prefersReducedMotion.current ? 0 : 200, easing: cubicOut }}>
					<StateBanner
						tone="danger"
						title="Não foi possível gerar o arquivo. Tente novamente."
						description={falhaDetalhe || undefined}
					/>
				</div>
			{/if}

			<div class="flex justify-end gap-2">
				<Button variant="secondary" onclick={fechar}>Cancelar</Button>
				<button
					type="button"
					onclick={() => void exportar()}
					disabled={slugs.length === 0}
					aria-disabled={fase !== 'repouso'}
					aria-busy={fase === 'gerando'}
					class="export-submit inline-flex h-9 min-w-[11.5rem] items-center justify-center rounded-md bg-brand px-4 text-sm font-semibold text-on-brand shadow-sm hover:bg-brand-hover hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1 disabled:cursor-not-allowed {fase === 'repouso' ? 'disabled:opacity-50' : ''}"
				>
					<span class="sr-only" aria-live="polite">{rotuloEstado}</span>
					<span class="grid" aria-hidden="true">
						<span
							class="inline-flex items-center justify-center gap-2 transition-opacity duration-fast [grid-area:1/1] {spanVisivel === 'repouso'
								? 'opacity-100'
								: 'opacity-0'}"
						>
							{rotuloRepouso}
						</span>
						<span
							class="inline-flex items-center justify-center gap-2 transition-opacity duration-fast [grid-area:1/1] {spanVisivel === 'gerando'
								? 'opacity-100'
								: 'opacity-0'}"
						>
							<i class="fas fa-spinner {$pendente ? 'fa-spin' : ''}" style="--fa-animation-duration: 0.8s"></i>
							Gerando…
						</span>
						<span
							class="inline-flex items-center justify-center gap-2 transition-opacity duration-fast [grid-area:1/1] {spanVisivel === 'pronto'
								? 'opacity-100'
								: 'opacity-0'}"
						>
							{#if fase === 'pronto'}
								<svg class="export-pronto-pop" width="14" height="14" viewBox="0 0 14 14" fill="none">
									<path
										d="M2.5 7.5 6 11l5.5-8"
										stroke="currentColor"
										stroke-width="2"
										stroke-linecap="round"
										stroke-linejoin="round"
									/>
								</svg>
							{/if}
							Pronto
						</span>
					</span>
				</button>
			</div>
		</div>
</Modal>

<style>
	.export-dot {
		transition: transform 150ms cubic-bezier(0.4, 0, 0.2, 1);
	}
	.export-check-pop {
		animation: export-check-pop 200ms cubic-bezier(0.34, 1.56, 0.64, 1) both;
	}
	@keyframes export-check-pop {
		from {
			transform: scale(0.6);
			opacity: 0;
		}
		to {
			transform: scale(1);
			opacity: 1;
		}
	}
	.export-pronto-pop {
		animation: export-pronto-pop 260ms cubic-bezier(0.34, 1.56, 0.64, 1) both;
	}
	@keyframes export-pronto-pop {
		from {
			transform: scale(0.5);
		}
		to {
			transform: scale(1);
		}
	}
	.export-submit {
		transition:
			background-color 150ms cubic-bezier(0.4, 0, 0.2, 1),
			border-color 150ms cubic-bezier(0.4, 0, 0.2, 1),
			opacity 150ms cubic-bezier(0.4, 0, 0.2, 1),
			box-shadow 150ms cubic-bezier(0.4, 0, 0.2, 1),
			transform 90ms cubic-bezier(0.4, 0, 0.2, 1);
	}
	.export-submit:active:not(:disabled) {
		transform: scale(0.98);
	}
	@media (prefers-reduced-motion: reduce) {
		.export-check-pop,
		.export-pronto-pop {
			animation-duration: 0ms;
		}
		.export-dot,
		.export-submit {
			transition-duration: 0ms;
		}
		.export-submit:active:not(:disabled) {
			transform: none;
		}
	}
</style>
