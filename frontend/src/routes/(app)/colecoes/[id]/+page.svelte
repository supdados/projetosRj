<script lang="ts">
	/**
	 * Página interna da coleção (tela 3c). URL: /colecoes/<id>.
	 *
	 * Consome `GET /api/colecoes/<id>/projetos` via `$lib/api/collections` (SWR)
	 * e compõe breadcrumb + header + linha de meta + 4 KPIs + tabela de projetos
	 * (filtros client-side: busca e Todos/Atrasados). Sem Gantt no MVP.
	 *
	 * Mutações: editar identidade (mesmo formulário do passo 1 do modal de
	 * criação), adicionar projetos (ColecaoProjectPicker num modal simples,
	 * POST idempotente por projeto) e remover projeto da coleção com
	 * confirmação. Erros 404 seguem o contrato anti-enumeração: coleção
	 * inexistente e coleção de outro usuário são indistinguíveis.
	 */
	import { onMount, tick } from 'svelte';
	import { page } from '$app/stores';
	import { base } from '$app/paths';
	import { goto } from '$app/navigation';
	import {
		adicionarProjeto,
		editarColecao,
		fetchColecaoProjetos,
		peekColecaoProjetos,
		removerProjeto
	} from '$lib/api/collections';
	import { ApiClientError } from '$lib/api/client';
	import type {
		CollectionColorId,
		CollectionDetailData,
		CollectionIconId,
		ProjetoColecaoRow
	} from '$lib/types/collections';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Button from '$lib/components/Button.svelte';
	import FilterChipGroup from '$lib/components/FilterChipGroup.svelte';
	import ColecaoIconTile from '$lib/components/ColecaoIconTile.svelte';
	import ColecaoProjectPicker from '$lib/components/ColecaoProjectPicker.svelte';
	import Modal from '$lib/components/Modal.svelte';
	import StateBanner from '$lib/components/StateBanner.svelte';
	import LoadErrorState from '$lib/components/LoadErrorState.svelte';
	import ColecaoDetalheSkeleton from '$lib/components/skeletons/ColecaoDetalheSkeleton.svelte';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import { COLLECTION_ICONS } from '$lib/icons/collectionIcons';
	import { confirmAction } from '$lib/stores/confirm';
	import { flash } from '$lib/stores/flash';
	import {
		accessErrorKind,
		accessErrorMessage,
		type AccessErrorKind
	} from '$lib/utils/accessErrorMessages';

	type LoadState = 'loading' | 'ready' | 'error';
	type FiltroLinhas = 'todos' | 'atrasados';

	/** 404 do contrato: nunca dizer se a coleção não existe ou se é de outro usuário. */
	const MSG_COLECAO_INACESSIVEL = 'Esta coleção não existe ou você não tem acesso.';

	const collectionId = $derived(Number($page.params.id));

	// SWR: reabre com o último dado bom deste id e revalida em silêncio.
	const initialData = peekColecaoProjetos(Number($page.params.id));
	let loadState = $state<LoadState>(initialData ? 'ready' : 'loading');
	let data = $state<CollectionDetailData | null>(initialData);
	let errorMessage = $state<string>('');
	let errorKind = $state<AccessErrorKind>('generic');

	let inFlight: AbortController | null = null;

	async function load(): Promise<void> {
		const cached = peekColecaoProjetos(collectionId);
		if (cached) {
			data = cached;
			loadState = 'ready';
		} else {
			loadState = 'loading';
		}
		errorMessage = '';
		inFlight?.abort();
		const controller = new AbortController();
		inFlight = controller;
		try {
			const next = await fetchColecaoProjetos(collectionId, controller.signal);
			if (controller.signal.aborted) return;
			data = next;
			loadState = 'ready';
		} catch (err) {
			if (controller.signal.aborted) return;
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			const message = accessErrorMessage(
				err,
				MSG_COLECAO_INACESSIVEL,
				'Falha ao carregar a coleção.'
			);
			if (data && accessErrorKind(err) === 'generic') {
				flash.danger(message);
				return;
			}
			data = null;
			errorMessage = message;
			errorKind = accessErrorKind(err);
			loadState = 'error';
		}
	}

	// Navegação client-side entre /colecoes/1 e /colecoes/2 reusa o componente:
	// o id muda sem remontar, então o recarregamento mora num efeito guardado.
	let idCarregado = -1;
	$effect(() => {
		const id = collectionId;
		if (id === idCarregado) return;
		idCarregado = id;
		const cached = peekColecaoProjetos(id);
		data = cached;
		loadState = cached ? 'ready' : 'loading';
		void load();
	});

	onMount(() => () => inFlight?.abort());

	// ── Derivados de meta/KPIs (tudo a partir dos rows + rollup) ─────────────
	const colecao = $derived(data?.colecao ?? null);
	const rows = $derived(data?.projetos ?? []);
	const isFavoritos = $derived(colecao?.tipo === 'favoritos');

	const tarefasTotal = $derived(rows.reduce((s, r) => s + r.tarefas_total, 0));
	const areasCount = $derived(
		new Set(rows.map((r) => r.orgao_sigla).filter((s): s is string => Boolean(s))).size
	);
	const prazoMaisDistante = $derived.by<string | null>(() => {
		let max: string | null = null;
		for (const r of rows) {
			if (r.data_fim && (!max || r.data_fim > max)) max = r.data_fim;
		}
		return max;
	});

	const CONCLUIDO_KEYS = new Set(['finalizado', 'finalizada', 'concluido', 'concluído']);
	const statusKey = (status: string): string => status.trim().toLowerCase();

	const atrasadosCount = $derived(rows.filter((r) => r.atrasado).length);
	const concluidosCount = $derived(rows.filter((r) => CONCLUIDO_KEYS.has(statusKey(r.status))).length);

	// ── Filtros client-side da tabela ────────────────────────────────────────
	let busca = $state('');
	let filtroLinhas = $state<FiltroLinhas>('todos');

	const FILTRO_OPTIONS = [
		{ id: 'todos', label: 'Todos' },
		{ id: 'atrasados', label: 'Atrasados' }
	];

	const COMBINING_MARKS = /[̀-ͯ]/g;
	const norm = (s: string): string =>
		s.normalize('NFD').replace(COMBINING_MARKS, '').toLowerCase();

	const linhasVisiveis = $derived.by<ProjetoColecaoRow[]>(() => {
		const termo = norm(busca.trim());
		return rows.filter((r) => {
			if (filtroLinhas === 'atrasados' && !r.atrasado) return false;
			if (!termo) return true;
			return (
				norm(r.nome).includes(termo) ||
				norm(r.orgao_sigla ?? '').includes(termo) ||
				String(r.id).includes(termo)
			);
		});
	});

	// ── Apresentação ─────────────────────────────────────────────────────────
	function formatDateBr(iso: string | null): string {
		if (!iso) return '';
		const parsed = new Date(iso);
		if (Number.isNaN(parsed.getTime())) return '';
		return parsed.toLocaleDateString('pt-BR', {
			day: '2-digit',
			month: '2-digit',
			year: 'numeric',
			timeZone: 'UTC'
		});
	}

	/** Família da pílula `.chip` conforme o status REAL (atraso é indicador à parte). */
	function statusChipClass(status: string): string {
		const key = statusKey(status);
		if (key === 'vigente' || key === 'em andamento') return 'chip--brand';
		if (CONCLUIDO_KEYS.has(key)) return 'chip--success';
		if (key === 'suspenso' || key === 'pausado') return 'chip--warning';
		if (key === 'cancelado' || key === 'cancelada') return 'chip--danger';
		return 'chip--neutral';
	}

	const pluralizar = (n: number, singular: string, plural: string): string =>
		`${n} ${n === 1 ? singular : plural}`;

	/** Linha inteira navega ao projeto; cliques em controles internos não. */
	function abrirProjeto(event: MouseEvent, projectId: number): void {
		const alvo = event.target as HTMLElement | null;
		if (alvo?.closest('a, button')) return;
		void goto(`${base}/projetos/${projectId}`);
	}

	// ── Adicionar projetos (picker num modal simples) ────────────────────────
	let pickerOpen = $state(false);
	let pickerSelecionados = $state<number[]>([]);
	let adding = $state(false);
	let pickerErro = $state<string | null>(null);

	const idsNaColecao = $derived(rows.map((r) => r.id));

	function abrirPicker(): void {
		pickerSelecionados = [];
		pickerErro = null;
		adding = false;
		pickerOpen = true;
	}

	function fecharPicker(): void {
		if (adding) return;
		pickerOpen = false;
	}

	async function adicionarSelecionados(): Promise<void> {
		if (adding || pickerSelecionados.length === 0) return;
		adding = true;
		pickerErro = null;
		const total = pickerSelecionados.length;
		let adicionados = 0;
		try {
			// Sequencial: POST idempotente por projeto (repetir um id é no-op).
			for (const projectId of pickerSelecionados) {
				await adicionarProjeto(collectionId, projectId);
				adicionados += 1;
			}
			adding = false;
			pickerOpen = false;
			flash.success(
				total === 1 ? '1 projeto adicionado à coleção.' : `${total} projetos adicionados à coleção.`
			);
			void load();
		} catch (err) {
			adding = false;
			const motivo =
				err instanceof ApiClientError ? err.message : 'Não foi possível adicionar os projetos.';
			pickerErro =
				adicionados > 0
					? `${motivo} ${adicionados} de ${total} projetos foram adicionados.`
					: motivo;
			// Falha no meio do lote: sem resync a tabela e os KPIs mentem até o F5.
			void load();
		}
	}

	// ── Remover projeto da coleção ───────────────────────────────────────────
	async function confirmarRemocao(row: ProjetoColecaoRow): Promise<void> {
		const ok = await confirmAction({
			title: `Remover "${row.nome}" da coleção?`,
			description: 'O projeto não é alterado — ele apenas deixa de aparecer nesta coleção.',
			confirmLabel: 'Remover da coleção',
			busyLabel: 'Removendo…',
			run: async () => {
				await removerProjeto(collectionId, row.id);
			}
		});
		if (!ok) return;
		flash.success(`Projeto removido da coleção.`);
		void load();
	}

	// ── Editar coleção (mesmo formulário do passo 1 do modal de criação) ─────
	const DESCRICAO_MAX = 200;

	const ICONE_OPTIONS: { id: CollectionIconId; label: string }[] = [
		{ id: 'camadas', label: 'Camadas' },
		{ id: 'servidores', label: 'Servidores' },
		{ id: 'pessoas', label: 'Pessoas' },
		{ id: 'documento', label: 'Documento' },
		{ id: 'estrela', label: 'Estrela' },
		{ id: 'rede', label: 'Rede' },
		{ id: 'capacitacao', label: 'Capacitação' },
		{ id: 'calendario', label: 'Calendário' }
	];

	// Mapas ESTÁTICOS por família: classe montada em runtime não compila.
	const COR_OPTIONS: {
		id: CollectionColorId;
		label: string;
		wash: string;
		dot: string;
		ativo: string;
	}[] = [
		{ id: 'primary', label: 'Azul', wash: 'bg-wash-brand', dot: 'bg-primary-600', ativo: 'border-primary-600' },
		{ id: 'success', label: 'Verde', wash: 'bg-wash-success', dot: 'bg-success-600', ativo: 'border-success-600' },
		{ id: 'warning', label: 'Âmbar', wash: 'bg-wash-warning', dot: 'bg-warning-600', ativo: 'border-warning-600' },
		{ id: 'attention', label: 'Laranja', wash: 'bg-wash-attention', dot: 'bg-attention-600', ativo: 'border-attention-600' },
		{ id: 'danger', label: 'Vermelho', wash: 'bg-wash-danger', dot: 'bg-danger-600', ativo: 'border-danger-600' },
		{ id: 'neutral', label: 'Cinza', wash: 'bg-wash-neutral', dot: 'bg-neutral-600', ativo: 'border-neutral-600' }
	];

	const ICONE_ATIVO_CLASS: Record<CollectionColorId, string> = {
		primary: 'border-primary-600 bg-wash-brand text-brand',
		success: 'border-success-600 bg-wash-success text-success',
		warning: 'border-warning-600 bg-wash-warning text-warning',
		attention: 'border-attention-600 bg-wash-attention text-attention',
		danger: 'border-danger-600 bg-wash-danger text-danger',
		neutral: 'border-neutral-600 bg-wash-neutral text-text-secondary'
	};

	let editOpen = $state(false);
	let editNome = $state('');
	let editDescricao = $state('');
	let editIcone = $state<CollectionIconId>('camadas');
	let editCor = $state<CollectionColorId>('primary');
	let editTriedSave = $state(false);
	let editSaving = $state(false);
	let editErro = $state<string | null>(null);
	let editNomeInputEl = $state<HTMLInputElement | null>(null);

	const editNomeInvalido = $derived(editTriedSave && !editNome.trim());

	function abrirEdicao(): void {
		if (!colecao) return;
		editNome = colecao.nome;
		editDescricao = colecao.descricao ?? '';
		editIcone = colecao.icone;
		editCor = colecao.cor;
		editTriedSave = false;
		editSaving = false;
		editErro = null;
		editOpen = true;
		void tick().then(() => editNomeInputEl?.focus());
	}

	function fecharEdicao(): void {
		if (editSaving) return;
		editOpen = false;
	}

	async function salvarEdicao(): Promise<void> {
		if (editSaving) return;
		editTriedSave = true;
		if (!editNome.trim()) {
			editNomeInputEl?.focus();
			return;
		}
		editSaving = true;
		editErro = null;
		try {
			const atualizada = await editarColecao(collectionId, {
				nome: editNome.trim(),
				descricao: editDescricao.trim() || null,
				icone: editIcone,
				cor: editCor
			});
			editSaving = false;
			editOpen = false;
			flash.success(`Coleção "${atualizada.nome}" atualizada.`);
			void load();
		} catch (err) {
			editSaving = false;
			editErro =
				err instanceof ApiClientError ? err.message : 'Não foi possível salvar a coleção.';
		}
	}

	const labelCls = 'text-xs font-medium text-text-secondary';
	const fieldCls =
		'h-[var(--control-h-md)] w-full rounded-control border bg-surface px-3.5 text-md text-text-primary placeholder:text-text-faint transition-colors duration-fast focus:outline-none';
	const thCls =
		'border-b border-border-subtle bg-surface-muted px-2.5 py-2 text-sm font-bold uppercase tracking-caps whitespace-nowrap';
	const tdCls = 'border-t border-border-subtle px-2.5 py-2.5 align-middle';
</script>

<svelte:head>
	<title>ProjetosRJ — {colecao ? colecao.nome : 'Coleção'}</title>
</svelte:head>

<section aria-labelledby="colecao-title" class="flex flex-col gap-4">
	{#if loadState === 'loading' && !data}
		<p role="status" aria-live="polite" class="sr-only">Carregando coleção…</p>
		<ColecaoDetalheSkeleton />
	{:else if loadState === 'error'}
		<LoadErrorState
			message={errorMessage}
			kind={errorKind}
			onRetry={() => load()}
			backHref={`${base}/colecoes`}
			backLabel="Voltar às coleções"
		/>
	{:else if colecao}
		<!-- Header-card: tile + nome + ações; linha de meta embutida. -->
		<div class="rounded-xl border border-border-subtle bg-surface shadow-sm">
			<PageHeader compact embedded class="min-h-[3.5rem]" labelId="colecao-title">
				{#snippet titleContent()}
					<span class="mr-2 inline-block align-middle">
						<ColecaoIconTile icone={colecao.icone} cor={colecao.cor} size={32} />
					</span>
					<span class="align-middle">{colecao.nome}</span>
					{#if isFavoritos}
						<span
							class="ml-2 rounded-sm border border-border-subtle bg-wash-neutral px-2 py-0.5 align-middle text-2xs font-medium text-text-secondary"
						>
							Padrão
						</span>
					{/if}
				{/snippet}
				{#snippet actions()}
					{#if !isFavoritos}
						<Button size="sm" variant="secondary" onclick={abrirEdicao}>Editar coleção</Button>
					{/if}
					<Button size="sm" onclick={abrirPicker}>
						{#snippet icon()}
							<i class="fas fa-plus" aria-hidden="true"></i>
						{/snippet}
						Adicionar projetos
					</Button>
				{/snippet}
			</PageHeader>
			<div
				class="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-border-subtle px-4 py-2.5 text-sm text-text-secondary"
			>
				<span>{pluralizar(colecao.etapas_total, 'etapa', 'etapas')}</span>
				<span class="text-text-faint" aria-hidden="true">|</span>
				<span>{pluralizar(tarefasTotal, 'tarefa', 'tarefas')}</span>
				<span class="text-text-faint" aria-hidden="true">|</span>
				<span>{pluralizar(areasCount, 'área responsável', 'áreas responsáveis')}</span>
				{#if prazoMaisDistante}
					<span class="text-text-faint" aria-hidden="true">|</span>
					<span>
						Prazo mais distante:
						<time datetime={prazoMaisDistante} class="font-mono text-text-primary">
							{formatDateBr(prazoMaisDistante)}
						</time>
					</span>
				{/if}
			</div>
		</div>

		<!-- KPIs: progresso geral destacado + projetos + atrasados + concluídos. -->
		<div class="grid grid-cols-2 gap-4 xl:grid-cols-[1.3fr_1fr_1fr_1fr]">
			<div
				class="flex items-center gap-4 rounded-lg border border-brand-soft bg-wash-brand p-4 shadow-sm"
			>
				<span class="shrink-0 font-heading text-4xl font-bold tracking-tight text-brand">
					{colecao.progresso_pct}%
				</span>
				<div class="min-w-0">
					<p class="m-0 text-md font-semibold text-brand">Progresso geral</p>
					<p class="m-0 text-sm text-text-secondary">
						{colecao.etapas_concluidas} de {colecao.etapas_total}
						{colecao.etapas_total === 1 ? 'etapa concluída' : 'etapas concluídas'}
					</p>
				</div>
			</div>
			<div
				class="flex items-center gap-4 rounded-lg border border-border-subtle bg-surface p-4 shadow-sm"
			>
				<span class="shrink-0 font-heading text-4xl font-bold tracking-tight text-text-primary">
					{colecao.projetos}
				</span>
				<div class="min-w-0">
					<p class="m-0 text-md font-medium text-text-primary">
						{colecao.projetos === 1 ? 'Projeto na coleção' : 'Projetos na coleção'}
					</p>
					<p class="m-0 text-sm text-text-muted">
						{pluralizar(colecao.etapas_total, 'etapa', 'etapas')} · {pluralizar(
							tarefasTotal,
							'tarefa',
							'tarefas'
						)}
					</p>
				</div>
			</div>
			<div
				class="flex items-center gap-4 rounded-lg border border-border-subtle bg-surface p-4 shadow-sm"
			>
				<span class="shrink-0 font-heading text-4xl font-bold tracking-tight text-danger">
					{atrasadosCount}
				</span>
				<div class="min-w-0">
					<p class="m-0 text-md font-medium text-text-primary">
						{atrasadosCount === 1 ? 'Atrasado' : 'Atrasados'}
					</p>
					<p class="m-0 text-sm text-text-muted">
						{atrasadosCount === 1 ? 'projeto com prazo vencido' : 'projetos com prazo vencido'}
					</p>
				</div>
			</div>
			<div
				class="flex items-center gap-4 rounded-lg border border-border-subtle bg-surface p-4 shadow-sm"
			>
				<span class="shrink-0 font-heading text-4xl font-bold tracking-tight text-success">
					{concluidosCount}
				</span>
				<div class="min-w-0">
					<p class="m-0 text-md font-medium text-text-primary">
						{concluidosCount === 1 ? 'Concluído' : 'Concluídos'}
					</p>
					<p class="m-0 text-sm text-text-muted">
						{concluidosCount === 1 ? 'projeto finalizado' : 'projetos finalizados'}
					</p>
				</div>
			</div>
		</div>

		<!-- Tabela de projetos da coleção (filtros client-side). -->
		<div class="overflow-hidden rounded-lg border border-border-subtle bg-surface shadow-sm">
			<div class="flex flex-wrap items-center gap-3 px-4 py-3">
				<h2 class="m-0 text-base font-bold text-text-primary">Projetos da coleção</h2>
				<div class="ml-auto flex flex-wrap items-center gap-2">
					<FilterChipGroup
						label="Filtrar projetos da coleção"
						options={FILTRO_OPTIONS}
						value={filtroLinhas}
						onchange={(id) => (filtroLinhas = id as FiltroLinhas)}
					/>
					<div class="relative w-52">
						<i
							class="fas fa-search pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-sm text-text-muted"
							aria-hidden="true"
						></i>
						<input
							id="colecaoProjetosSearch"
							type="search"
							autocomplete="off"
							bind:value={busca}
							aria-label="Buscar projeto na coleção"
							placeholder="Buscar projeto"
							class="h-9 w-full rounded-lg border border-border-subtle bg-surface pl-8 pr-2.5 text-md text-text-primary placeholder:text-text-muted transition-colors duration-fast focus:border-brand focus:outline-none"
						/>
					</div>
				</div>
			</div>

			{#if rows.length === 0}
				<!-- Coleção vazia: mensagem curta com CTA único. -->
				<div class="border-t border-border-subtle px-4 py-8 text-center">
					<div
						class="mx-auto mb-3 inline-flex h-14 w-14 items-center justify-center rounded-xl border border-brand-soft bg-wash-neutral text-xl text-brand"
					>
						<AppIcon id="projetos" size={28} />
					</div>
					<h3 class="m-0 font-heading text-xl font-bold text-text-primary">
						{isFavoritos ? 'Nenhum projeto favoritado ainda' : 'Nenhum projeto nesta coleção'}
					</h3>
					<p class="mb-3.5 mt-1.5 text-sm text-text-muted">
						{isFavoritos
							? 'Marque a estrela em qualquer projeto e ele entra aqui.'
							: 'Adicione projetos para acompanhar o andamento agrupado.'}
					</p>
					<Button size="sm" onclick={abrirPicker}>
						{#snippet icon()}
							<i class="fas fa-plus" aria-hidden="true"></i>
						{/snippet}
						Adicionar projetos
					</Button>
				</div>
			{:else if linhasVisiveis.length === 0}
				<p
					role="status"
					aria-live="polite"
					class="m-0 border-t border-border-subtle px-4 py-6 text-center text-sm text-text-muted"
				>
					{filtroLinhas === 'atrasados' && !busca.trim()
						? 'Nenhum projeto atrasado nesta coleção.'
						: 'Nenhum projeto corresponde aos filtros aplicados.'}
				</p>
			{:else}
				<div class="overflow-x-auto" aria-busy={loadState !== 'ready'}>
					<table class="m-0 w-full min-w-[1040px] border-separate border-spacing-0 text-sm">
						<caption class="sr-only">Projetos da coleção {colecao.nome}</caption>
						<thead>
							<tr class="text-left text-text-muted">
								<th scope="col" class="w-16 {thCls}">ID</th>
								<th scope="col" class="min-w-[220px] {thCls}">Projeto</th>
								<th scope="col" class={thCls}>Área responsável</th>
								<th scope="col" class="{thCls} text-center">Etapas</th>
								<th scope="col" class="{thCls} text-center">Tarefas</th>
								<th scope="col" class="min-w-[140px] {thCls}">Progresso</th>
								<th scope="col" class={thCls}>Início</th>
								<th scope="col" class={thCls}>Fim previsto</th>
								<th scope="col" class="{thCls} text-center">Status</th>
								<th scope="col" class="w-16 {thCls}">
									<span class="sr-only">Ações</span>
								</th>
							</tr>
						</thead>
						<tbody>
							{#each linhasVisiveis as row (row.id)}
								<!-- Clique na linha navega; o teclado usa o link do título. -->
								<!-- svelte-ignore a11y_click_events_have_key_events -->
								<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
								<tr
									onclick={(e) => abrirProjeto(e, row.id)}
									class="cursor-pointer transition-colors duration-fast hover:bg-surface-muted"
								>
									<td class="{tdCls} font-mono text-sm text-text-muted">{row.id}</td>
									<td class={tdCls}>
										<a
											href={`${base}/projetos/${row.id}`}
											class="text-md font-medium text-brand no-underline transition-colors duration-fast hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
										>
											{row.nome}
										</a>
									</td>
									<td class="{tdCls} text-text-secondary">
										{#if row.orgao_sigla}
											<span class="text-sm font-medium uppercase tracking-wide">
												{row.orgao_sigla}
											</span>
										{:else}
											<span class="italic text-text-muted">—</span>
										{/if}
									</td>
									<td class="{tdCls} whitespace-nowrap text-center font-mono text-sm text-text-secondary">
										{row.etapas_concluidas} / {row.etapas_total}
									</td>
									<td class="{tdCls} whitespace-nowrap text-center font-mono text-sm text-text-secondary">
										{row.tarefas_concluidas} / {row.tarefas_total}
									</td>
									<td class={tdCls}>
										<div class="flex items-center gap-2">
											<!-- Decorativa: o % é o texto ao lado. -->
											<div
												class="h-1.5 flex-1 overflow-hidden rounded-full bg-progress-track"
												aria-hidden="true"
											>
												<div
													class="h-full rounded-full bg-brand"
													style:width={`${row.progresso_pct}%`}
												></div>
											</div>
											<span class="shrink-0 font-mono text-xs text-text-secondary">
												{row.progresso_pct}%
											</span>
										</div>
									</td>
									<td class="{tdCls} whitespace-nowrap font-mono text-sm text-text-secondary">
										{#if row.data_inicio}
											<time datetime={row.data_inicio}>{formatDateBr(row.data_inicio)}</time>
										{:else}
											<span class="italic text-text-muted">—</span>
										{/if}
									</td>
									<td class="{tdCls} whitespace-nowrap font-mono text-sm text-text-secondary">
										{#if row.data_fim}
											<time datetime={row.data_fim}>{formatDateBr(row.data_fim)}</time>
										{:else}
											<span class="italic text-text-muted">—</span>
										{/if}
									</td>
									<td class="{tdCls} whitespace-nowrap text-center">
										<!-- Atrasado implica Vigente: mostrar só um chip. -->
										{#if row.atrasado}
											<span class="chip chip--danger">Atrasado</span>
										{:else}
											<span class="chip {statusChipClass(row.status)}">{row.status}</span>
										{/if}
									</td>
									<td class="{tdCls} text-center">
										<button
											type="button"
											onclick={() => void confirmarRemocao(row)}
											title="Remover da coleção"
											aria-label={`Remover ${row.nome} da coleção`}
											class="inline-flex h-8 w-8 items-center justify-center text-sm text-text-muted transition-colors duration-fast hover:text-danger focus:outline-none focus-visible:rounded-md focus-visible:ring-2 focus-visible:ring-danger"
										>
											<AppIcon id="exclusao" size={16} />
										</button>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		</div>
	{/if}
</section>

<!-- Adicionar projetos: picker reutilizável num modal simples. -->
{#if pickerOpen}
	<Modal labelId="colecao-add-projetos-title" maxWidth="max-w-[540px]" onBackdrop={fecharPicker}>
		<div class="flex max-h-[80vh] flex-col gap-4">
			<div class="flex items-center gap-3">
				<h2
					id="colecao-add-projetos-title"
					class="font-heading text-xl font-bold text-text-primary"
				>
					Adicionar projetos
				</h2>
				<button
					type="button"
					onclick={fecharPicker}
					disabled={adding}
					aria-label="Fechar"
					class="ml-auto grid h-8 w-8 place-items-center rounded-md text-icon-faint transition-colors duration-fast hover:bg-surface-muted hover:text-text-primary disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
				>
					<svg
						viewBox="0 0 20 20"
						class="h-4 w-4"
						fill="none"
						stroke="currentColor"
						stroke-width="1.6"
						aria-hidden="true"
					>
						<path d="m5 5 10 10M15 5 5 15" stroke-linecap="round" />
					</svg>
				</button>
			</div>

			<div class="thin-scroll flex min-h-0 flex-col gap-4 overflow-y-auto">
				<ColecaoProjectPicker
					selecionados={pickerSelecionados}
					colecaoId={collectionId}
					exclude={idsNaColecao}
					onchange={(ids) => (pickerSelecionados = ids)}
				/>
				{#if pickerErro}
					<StateBanner tone="danger" title={pickerErro} />
				{/if}
			</div>

			<footer class="flex justify-end gap-2 border-t border-border-hairline pt-4">
				<Button variant="secondary" onclick={fecharPicker} disabled={adding}>Cancelar</Button>
				<Button
					onclick={() => void adicionarSelecionados()}
					disabled={adding || pickerSelecionados.length === 0}
				>
					{adding
						? 'Adicionando…'
						: pickerSelecionados.length === 1
							? 'Adicionar 1 projeto'
							: `Adicionar ${pickerSelecionados.length} projetos`}
				</Button>
			</footer>
		</div>
	</Modal>
{/if}

<!-- Edição de identidade: mesmo formulário do passo 1 do modal de criação. -->
{#if editOpen && colecao}
	<Modal labelId="editar-colecao-title" maxWidth="max-w-[540px]" onBackdrop={fecharEdicao}>
		<form
			class="flex flex-col gap-4"
			onsubmit={(e) => {
				e.preventDefault();
				void salvarEdicao();
			}}
		>
			<div class="flex items-center gap-3">
				<h2 id="editar-colecao-title" class="font-heading text-xl font-bold text-text-primary">
					Editar coleção
				</h2>
				<button
					type="button"
					onclick={fecharEdicao}
					disabled={editSaving}
					aria-label="Fechar"
					class="ml-auto grid h-8 w-8 place-items-center rounded-md text-icon-faint transition-colors duration-fast hover:bg-surface-muted hover:text-text-primary disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
				>
					<svg
						viewBox="0 0 20 20"
						class="h-4 w-4"
						fill="none"
						stroke="currentColor"
						stroke-width="1.6"
						aria-hidden="true"
					>
						<path d="m5 5 10 10M15 5 5 15" stroke-linecap="round" />
					</svg>
				</button>
			</div>

			<div class="flex items-end gap-3">
				<ColecaoIconTile icone={editIcone} cor={editCor} size={52} />
				<div class="flex min-w-0 flex-1 flex-col gap-1.5">
					<label for="ec-nome" class={labelCls}>Nome da coleção</label>
					<input
						id="ec-nome"
						bind:this={editNomeInputEl}
						bind:value={editNome}
						type="text"
						aria-invalid={editNomeInvalido}
						placeholder="Ex.: Modernização Digital 2026"
						class="{fieldCls} {editNomeInvalido
							? 'border-danger'
							: 'border-border-strong focus:border-brand'}"
					/>
				</div>
			</div>
			{#if editNomeInvalido}
				<p class="text-xs text-danger">Informe o nome da coleção.</p>
			{/if}

			<div class="flex flex-col gap-1.5">
				<label for="ec-descricao" class={labelCls}>Descrição (opcional)</label>
				<input
					id="ec-descricao"
					bind:value={editDescricao}
					type="text"
					maxlength={DESCRICAO_MAX}
					placeholder="Para que serve esta coleção"
					class="{fieldCls} border-border-strong focus:border-brand"
				/>
			</div>

			<div class="flex flex-col gap-2">
				<span id="ec-icone-label" class={labelCls}>Ícone</span>
				<div role="group" aria-labelledby="ec-icone-label" class="grid grid-cols-8 gap-2">
					{#each ICONE_OPTIONS as opcao (opcao.id)}
						{@const ativo = editIcone === opcao.id}
						<button
							type="button"
							aria-pressed={ativo}
							aria-label={opcao.label}
							onclick={() => (editIcone = opcao.id)}
							class="grid aspect-square place-items-center rounded-md border transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-brand {ativo
								? ICONE_ATIVO_CLASS[editCor]
								: 'border-border-subtle text-text-secondary hover:bg-surface-muted'}"
						>
							<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
								{#each COLLECTION_ICONS[opcao.id] as p (p.d)}
									<path d={p.d} opacity={p.opacity} fill-rule={p.fillRule} />
								{/each}
							</svg>
						</button>
					{/each}
				</div>
			</div>

			<div class="flex flex-col gap-2">
				<span id="ec-cor-label" class={labelCls}>Cor</span>
				<div role="group" aria-labelledby="ec-cor-label" class="flex gap-2">
					{#each COR_OPTIONS as opcao (opcao.id)}
						{@const ativo = editCor === opcao.id}
						<button
							type="button"
							aria-pressed={ativo}
							aria-label={opcao.label}
							onclick={() => (editCor = opcao.id)}
							class="grid h-8 w-8 place-items-center rounded-md border-2 transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1 {opcao.wash} {ativo
								? opcao.ativo
								: 'border-transparent hover:border-border-subtle'}"
						>
							<span class="h-3.5 w-3.5 rounded-full {opcao.dot}" aria-hidden="true"></span>
						</button>
					{/each}
				</div>
			</div>

			{#if editErro}
				<StateBanner tone="danger" title={editErro} />
			{/if}

			<footer class="flex justify-end gap-2 border-t border-border-hairline pt-4">
				<Button variant="secondary" onclick={fecharEdicao} disabled={editSaving}>Cancelar</Button>
				<Button type="submit" disabled={editSaving}>
					{editSaving ? 'Salvando…' : 'Salvar alterações'}
				</Button>
			</footer>
		</form>
	</Modal>
{/if}
