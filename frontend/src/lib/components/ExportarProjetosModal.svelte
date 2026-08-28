<script lang="ts">
	/**
	 * Modal de exportação de projetos em CSV (`GET /api/projetos/exportar`):
	 * escopo (lista filtrada × todos), conteúdo (só projetos × com etapas),
	 * seleção de colunas persistida em `localStorage` e download via blob +
	 * `<a download>` programático.
	 */
	import { tick, untrack } from 'svelte';
	import { slide } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';
	import { prefersReducedMotion } from 'svelte/motion';
	import { ApiClientError } from '$lib/api/client';
	import { exportarProjetosCsv, type ExportProjectsFile } from '$lib/api/projects';
	import { delayedPending } from '$lib/utils/delayedPending';
	import {
		EXPORT_COLUMNS,
		EXPORT_STAGE_COLUMNS,
		DEFAULT_SLUGS,
		DEFAULT_STAGE_SLUGS,
		loadStoredSlugs,
		loadStoredStageSlugs,
		saveStoredSlugs,
		saveStoredStageSlugs,
		type ExportColumn
	} from '$lib/utils/exportColumns';
	import type { ProjectsListQuery } from '$lib/types/projects';
	import Modal from '$lib/components/Modal.svelte';
	import Button from '$lib/components/Button.svelte';
	import StateBanner from '$lib/components/StateBanner.svelte';
	import ExportColumnPicker from '$lib/components/ExportColumnPicker.svelte';

	type EscopoExport = 'lista' | 'todos';
	type ConteudoExport = 'projetos' | 'etapas';
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
	let conteudo = $state<ConteudoExport>('projetos');
	let slugs = $state<string[]>([...DEFAULT_SLUGS]);
	let slugsEtapa = $state<string[]>([...DEFAULT_STAGE_SLUGS]);
	let fase = $state<FaseExport>('repouso');
	let falha = $state<boolean>(false);
	let falhaDetalhe = $state<string>('');
	let fecharTimer = $state<number | null>(null);
	let escopoEl = $state<HTMLFieldSetElement | null>(null);
	let montado = $state<boolean>(false);
	// Suprime o pop dos checks nas ações em lote (todas/limpar/padrão).
	let popPermitido = $state<boolean>(true);
	// Invalida continuações de um export antigo (modal fechado e reaberto).
	let sessaoExport = 0;

	const pendente = delayedPending({ showAfterMs: 150, minVisibleMs: 350 });

	const comEtapas = $derived(conteudo === 'etapas');
	const selecionadas = $derived(new Set(slugs));
	const selecionadasEtapa = $derived(new Set(slugsEtapa));
	const selecaoIncompleta = $derived(slugs.length === 0 || (comEtapas && slugsEtapa.length === 0));
	// No modo com etapas o total de linhas não é o de projetos — não prometer contagem.
	const rotuloRepouso = $derived(
		escopo === 'lista' && !comEtapas
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
			conteudo = 'projetos';
			slugs = ordenarPeloRegistro(EXPORT_COLUMNS, loadStoredSlugs());
			slugsEtapa = ordenarPeloRegistro(EXPORT_STAGE_COLUMNS, loadStoredStageSlugs());
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

	async function focarRadioSelecionado(): Promise<void> {
		await tick();
		escopoEl?.querySelector<HTMLInputElement>('input:checked')?.focus();
	}

	/** Mantém a seleção na ordem canônica do registry (= ordem das colunas no CSV). */
	function ordenarPeloRegistro(
		registro: readonly ExportColumn[],
		selecao: readonly string[]
	): string[] {
		const escolhidos = new Set(selecao);
		return registro.filter((c) => escolhidos.has(c.slug)).map((c) => c.slug);
	}

	function atualizarSlugs(proximos: string[]): void {
		slugs = proximos;
		saveStoredSlugs(proximos);
	}

	function atualizarSlugsEtapa(proximos: string[]): void {
		slugsEtapa = proximos;
		saveStoredStageSlugs(proximos);
	}

	function alternarColuna(slug: string): void {
		if (selecionadas.has(slug)) {
			atualizarSlugs(slugs.filter((s) => s !== slug));
			return;
		}
		atualizarSlugs(ordenarPeloRegistro(EXPORT_COLUMNS, [...slugs, slug]));
	}

	function alternarColunaEtapa(slug: string): void {
		if (selecionadasEtapa.has(slug)) {
			atualizarSlugsEtapa(slugsEtapa.filter((s) => s !== slug));
			return;
		}
		atualizarSlugsEtapa(ordenarPeloRegistro(EXPORT_STAGE_COLUMNS, [...slugsEtapa, slug]));
	}

	function aplicarEmLote(aplicar: (proximos: string[]) => void, proximos: string[]): void {
		popPermitido = false;
		aplicar(proximos);
		void tick().then(() => (popPermitido = true));
	}

	function selecionarTodas(): void {
		aplicarEmLote(atualizarSlugs, EXPORT_COLUMNS.map((c) => c.slug));
	}

	function limparColunas(): void {
		aplicarEmLote(atualizarSlugs, []);
	}

	function selecionarTodasEtapa(): void {
		aplicarEmLote(atualizarSlugsEtapa, EXPORT_STAGE_COLUMNS.map((c) => c.slug));
	}

	function limparColunasEtapa(): void {
		aplicarEmLote(atualizarSlugsEtapa, []);
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
			if (filtros.orgao != null) {
				params.set('orgao', String(filtros.orgao));
				if (filtros.apenas_orgao) params.set('apenas_orgao', '1');
			}
			if (filtros.colecao != null) params.set('colecao', String(filtros.colecao));
			if (filtros.excluir_colecao != null) {
				params.set('excluir_colecao', String(filtros.excluir_colecao));
			}
		}
		params.set('colunas', slugs.join(','));
		if (comEtapas) {
			params.set('com_etapas', '1');
			params.set('colunas_etapa', slugsEtapa.join(','));
		}
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
		if (fase !== 'repouso' || selecaoIncompleta) return;
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

{#snippet opcaoRadio(
	nome: string,
	valor: string,
	rotulo: string,
	ativo: boolean,
	escolher: () => void
)}
	<label
		class="inline-flex cursor-pointer items-center gap-2 rounded-sm focus-within:ring-2 focus-within:ring-brand focus-within:ring-offset-2"
	>
		<input
			type="radio"
			name={nome}
			value={valor}
			checked={ativo}
			onchange={escolher}
			class="sr-only"
		/>
		<span
			class="grid h-3.5 w-3.5 shrink-0 place-items-center rounded-full border {ativo
				? 'border-brand'
				: 'border-border-strong'}"
			aria-hidden="true"
		>
			<span
				class="export-dot h-2 w-2 rounded-full bg-brand"
				style:transform={ativo ? 'scale(1)' : 'scale(0)'}
			></span>
		</span>
		<span class="text-sm {ativo ? 'font-medium text-text-primary' : 'text-text-secondary'}">
			{rotulo}
		</span>
	</label>
{/snippet}

<Modal {open} labelId="exportar-projetos-title" maxWidth="max-w-2xl" onBackdrop={fechar} onEscape={fechar}>
		<div class="flex flex-col gap-4">
			<h2 id="exportar-projetos-title" class="font-heading text-xl font-bold text-text-primary">
				Exportar projetos
			</h2>

			{#if permitirEscopoLista}
				<fieldset bind:this={escopoEl} class="flex flex-col gap-1.5">
					<legend class="mb-1.5 text-2xs font-bold uppercase tracking-caps text-text-label">
						Escopo
					</legend>
					<div class="flex items-center gap-5">
						{@render opcaoRadio(
							'exportar-projetos-escopo',
							'lista',
							'Lista filtrada atual',
							escopo === 'lista',
							() => (escopo = 'lista')
						)}
						{@render opcaoRadio(
							'exportar-projetos-escopo',
							'todos',
							'Todos os projetos',
							escopo === 'todos',
							() => (escopo = 'todos')
						)}
					</div>
				</fieldset>
			{/if}

			<fieldset
				class="flex flex-col gap-1.5 {permitirEscopoLista
					? 'border-t border-border-hairline pt-4'
					: ''}"
			>
				<legend class="mb-1.5 text-2xs font-bold uppercase tracking-caps text-text-label">
					Conteúdo
				</legend>
				<div class="flex items-center gap-5">
					{@render opcaoRadio(
						'exportar-projetos-conteudo',
						'projetos',
						'Somente projetos',
						conteudo === 'projetos',
						() => (conteudo = 'projetos')
					)}
					{@render opcaoRadio(
						'exportar-projetos-conteudo',
						'etapas',
						'Projetos com etapas',
						conteudo === 'etapas',
						() => (conteudo = 'etapas')
					)}
				</div>
			</fieldset>

			<section class="flex flex-col gap-2 border-t border-border-hairline pt-4">
				<ExportColumnPicker
					titulo="Colunas"
					registro={EXPORT_COLUMNS}
					selecao={slugs}
					pop={montado && popPermitido}
					aviso={slugs.length === 0 ? 'Escolha ao menos uma coluna.' : ''}
					alternar={alternarColuna}
					todas={selecionarTodas}
					limpar={limparColunas}
				/>
			</section>

			{#if comEtapas}
				<section
					class="flex flex-col gap-2 border-t border-border-hairline pt-4"
					transition:slide={{ duration: prefersReducedMotion.current ? 0 : 200, easing: cubicOut }}
				>
					<ExportColumnPicker
						titulo="Colunas de etapa"
						registro={EXPORT_STAGE_COLUMNS}
						selecao={slugsEtapa}
						pop={montado && popPermitido}
						aviso={slugsEtapa.length === 0 ? 'Escolha ao menos uma coluna de etapa.' : ''}
						alternar={alternarColunaEtapa}
						todas={selecionarTodasEtapa}
						limpar={limparColunasEtapa}
					/>
					<p class="text-xs text-text-muted">
						Uma linha por etapa; colunas do projeto repetem por linha. Ref Projeto é incluída
						automaticamente.
					</p>
				</section>
			{/if}

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
					disabled={selecaoIncompleta}
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
