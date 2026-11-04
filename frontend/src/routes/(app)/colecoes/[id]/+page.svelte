<script lang="ts">
	/**
	 * Página interna da coleção (tela 3c). URL: /colecoes/<id>.
	 *
	 * Consome `GET /api/colecoes/<id>/projetos` via `$lib/api/collections` (SWR)
	 * e compõe breadcrumb + header + linha de meta + 4 KPIs + tabela de projetos
	 * (filtros client-side: busca e Todos/Atrasados) + cronograma (Gantt, fetch
	 * próprio). Toda mutação que muda os ITENS (incluir, remover, aceitar,
	 * revogar/rebaixar no modal de compartilhar — a poda tira itens) recarrega
	 * as duas coisas (`recarregarTudo`).
	 *
	 * Mutações: renomear inline no título (caneta, padrão do ProjectHeader),
	 * trocar ícone/cor num popover ancorado ao tile (a descrição não é editável
	 * aqui), compartilhar (CompartilharColecaoModal), adicionar projetos
	 * (ColecaoAdicionarProjetosModal, POST idempotente por projeto) e remover
	 * projeto da coleção com confirmação. Erros 404 seguem o contrato
	 * anti-enumeração: coleção inexistente e coleção de outro usuário são
	 * indistinguíveis.
	 *
	 * Fase 2: a UI espelha o papel do ator vindo no payload — viewer só lê
	 * (nem adicionar nem remover projetos), editor inclui e remove SÓ o que
	 * incluiu (`pode_remover` por linha) e dono é o único que edita a
	 * identidade, compartilha e apaga. O gate real é do backend (403); aqui é só
	 * não oferecer o que vai falhar.
	 *
	 * Convite pendente, dois estados:
	 *   - SEM acesso: `.../projetos` dá o MESMO 404 de coleção inexistente; aí a
	 *     página tenta `GET .../convite` e, havendo convite para mim, mostra só
	 *     os metadados com Aceitar/Recusar (ColecaoConvitePendente);
	 *   - COM acesso (ex.: Leitor que recebeu share de área como Editor):
	 *     `.../projetos` dá 200 e a coleção abre normal, com um banner de
	 *     Aceitar/Recusar acima dos KPIs (ColecaoConviteExtraBanner, gatilho no
	 *     resumo do sino). Aceitar recarrega tudo (o papel sobe); recusar só
	 *     fecha o banner — o acesso atual continua.
	 * Quem já participa (não dono) ganha "Sair da coleção", com a contagem do
	 * que sai (os próprios itens e os órfãos, de quem já não é editor).
	 *
	 * Tabela e modal de adicionar moram em ColecaoProjetosTabela e
	 * ColecaoAdicionarProjetosModal (a página passava de 1000 linhas).
	 */
	import { onMount, tick } from 'svelte';
	import { page } from '$app/stores';
	import { base } from '$app/paths';
	import { goto } from '$app/navigation';
	import {
		editarColecao,
		fetchColecaoProjetos,
		fetchConvite,
		fetchCronograma,
		peekColecaoCronograma,
		peekColecaoProjetos,
		removerProjeto,
		sairDaColecao
	} from '$lib/api/collections';
	import { ApiClientError } from '$lib/api/client';
	import type {
		CollectionColorId,
		CollectionCronogramaData,
		CollectionDetailData,
		CollectionIconId,
		ConviteColecao,
		ProjetoColecaoRow
	} from '$lib/types/collections';
	import CollectionGantt from '$lib/components/CollectionGantt.svelte';
	import CompartilharColecaoModal from '$lib/components/CompartilharColecaoModal.svelte';
	import ColecaoAdicionarProjetosModal from '$lib/components/ColecaoAdicionarProjetosModal.svelte';
	import ColecaoConvitePendente from '$lib/components/ColecaoConvitePendente.svelte';
	import ColecaoConviteExtraBanner from '$lib/components/ColecaoConviteExtraBanner.svelte';
	import ColecaoProjetosTabela from '$lib/components/ColecaoProjetosTabela.svelte';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Button from '$lib/components/Button.svelte';
	import ColecaoIconTile from '$lib/components/ColecaoIconTile.svelte';
	import LoadErrorState from '$lib/components/LoadErrorState.svelte';
	import ColecaoDetalheSkeleton from '$lib/components/skeletons/ColecaoDetalheSkeleton.svelte';
	import Skeleton from '$lib/components/Skeleton.svelte';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import { COLLECTION_ICONS } from '$lib/icons/collectionIcons';
	import {
		COLECAO_COR_OPTIONS,
		COLECAO_ICONE_ATIVO_CLASS,
		COLECAO_ICONE_OPTIONS
	} from '$lib/icons/collectionIdentity';
	import { auth } from '$lib/stores/auth';
	import { confirmAction } from '$lib/stores/confirm';
	import { flash } from '$lib/stores/flash';
	import {
		accessErrorKind,
		accessErrorMessage,
		type AccessErrorKind
	} from '$lib/utils/accessErrorMessages';
	import { textoDeSaida } from '$lib/utils/colecaoShares';
	import type { DesfechoConvite } from '$lib/utils/conviteColecao';
	import type { ProjectsVisibilidadePicker } from '$lib/types/projects';
	import { formatIsoDateBR } from '$lib/utils/dateFormat';

	/** `convite` = sem acesso à coleção, mas com convite pendente para mim. */
	type LoadState = 'loading' | 'ready' | 'convite' | 'error';

	/** 404 do contrato: nunca dizer se a coleção não existe ou se é de outro usuário. */
	const MSG_COLECAO_INACESSIVEL = 'Esta coleção não existe ou você não tem acesso.';

	const collectionId = $derived(Number($page.params.id));

	// SWR: reabre com o último dado bom deste id e revalida em silêncio.
	const initialData = peekColecaoProjetos(Number($page.params.id));
	let loadState = $state<LoadState>(initialData ? 'ready' : 'loading');
	let data = $state<CollectionDetailData | null>(initialData);
	let errorMessage = $state<string>('');
	let errorKind = $state<AccessErrorKind>('generic');
	let convite = $state<ConviteColecao | null>(null);

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
			if (accessErrorKind(err) === 'not_found' && (await carregarConvite(controller))) return;
			if (controller.signal.aborted) return;
			errorMessage = message;
			errorKind = accessErrorKind(err);
			loadState = 'error';
		}
	}

	/**
	 * 404 em `.../projetos` pode ser convite pendente: o MESMO 404 anti-
	 * enumeração, então só `GET .../convite` desempata. `false` = sem convite
	 * (a página segue para o estado de erro de sempre).
	 */
	async function carregarConvite(controller: AbortController): Promise<boolean> {
		try {
			const pendente = await fetchConvite(collectionId, controller.signal);
			if (controller.signal.aborted) return true;
			convite = pendente;
			loadState = 'convite';
			return true;
		} catch {
			return false;
		}
	}

	/** Aceitou: a coleção abre normalmente; recusou ou sumiu: volta ao índice. */
	function onConviteRespondido(desfecho: DesfechoConvite): void {
		if (desfecho.tipo === 'aceito') {
			convite = null;
			void load();
			void loadCronograma();
			return;
		}
		if (desfecho.tipo === 'recusado' || desfecho.tipo === 'indisponivel') {
			void goto(`${base}/colecoes`);
		}
	}

	// ── Cronograma (Gantt): fetch próprio, mesmo padrão SWR da tabela ────────
	let cronoState = $state<LoadState>('loading');
	let cronoData = $state<CollectionCronogramaData | null>(null);
	let cronoInFlight: AbortController | null = null;

	async function loadCronograma(): Promise<void> {
		const cached = peekColecaoCronograma(collectionId);
		cronoData = cached;
		cronoState = cached ? 'ready' : 'loading';
		cronoInFlight?.abort();
		const controller = new AbortController();
		cronoInFlight = controller;
		try {
			const next = await fetchCronograma(collectionId, controller.signal);
			if (controller.signal.aborted) return;
			cronoData = next;
			cronoState = 'ready';
		} catch (err) {
			if (controller.signal.aborted) return;
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			if (cronoData) return;
			cronoState = 'error';
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
		convite = null;
		loadState = cached ? 'ready' : 'loading';
		void load();
		void loadCronograma();
	});

	onMount(() => () => {
		inFlight?.abort();
		cronoInFlight?.abort();
	});

	// ── Derivados de meta/KPIs (tudo a partir dos rows + rollup) ─────────────
	const colecao = $derived(data?.colecao ?? null);
	const rows = $derived(data?.projetos ?? []);
	const isFavoritos = $derived(colecao?.tipo === 'favoritos');

	// ── Papel do ator: o que a tela pode oferecer ───────────────────────────
	const isDono = $derived(colecao?.papel === 'dono');
	const podeMexerNosItens = $derived(colecao?.papel === 'dono' || colecao?.papel === 'editor');
	// Quem recebeu a coleção (custom) pode sair; o dono não sai, apaga.
	const podeSair = $derived(Boolean(colecao) && !isDono && !isFavoritos);
	const meuId = $derived($auth.user?.id ?? null);

	const PAPEL_LABEL: Record<string, string> = { viewer: 'leitor', editor: 'editor' };
	const procedencia = $derived(
		colecao && !isDono && colecao.owner
			? `Compartilhada por ${colecao.owner.nome} · você é ${PAPEL_LABEL[colecao.papel] ?? 'leitor'}`
			: ''
	);

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

	// ── Apresentação ─────────────────────────────────────────────────────────
	const pluralizar = (n: number, singular: string, plural: string): string =>
		`${n} ${n === 1 ? singular : plural}`;

	// ── Compartilhar (só dono; o modal cuida das concessões) ─────────────────
	let shareOpen = $state(false);

	// ── Adicionar projetos (picker num modal; dono × editor mudam a lista) ───
	let pickerOpen = $state(false);
	const idsNaColecao = $derived(rows.map((r) => r.id));
	// O que o backend aceita deste papel: editor só pela área; dono sem a
	// derivada de outra coleção; Favoritos (nunca compartilhada) aceita tudo.
	const pickerVisibilidade = $derived<ProjectsVisibilidadePicker | undefined>(
		isFavoritos ? undefined : isDono ? 'propria' : 'area'
	);

	function recarregarTudo(): void {
		void load();
		void loadCronograma();
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
		recarregarTudo();
	}

	// ── Sair da coleção (quem recebeu; os projetos que incluí saem junto) ────
	async function confirmarSaida(): Promise<void> {
		if (!data) return;
		const nome = data.colecao.nome;
		const texto = textoDeSaida(nome, data.itens_incluidos_por_mim ?? 0, data.itens_orfaos ?? 0);
		const ok = await confirmAction({
			...texto,
			tone: 'danger',
			busyLabel: 'Saindo…',
			run: async () => {
				try {
					await sairDaColecao(collectionId);
				} catch (err) {
					// 404 = o acesso já tinha caído (revogado no meio): o resultado é o mesmo.
					if (accessErrorKind(err) !== 'not_found') throw err;
				}
			}
		});
		if (!ok) return;
		flash.success(`Você saiu da coleção "${nome}".`);
		void goto(`${base}/colecoes`);
	}

	// ── Identidade (nome inline no título; ícone/cor no popover do tile) ─────
	const podeEditarIdentidade = $derived(isDono && !isFavoritos);

	// ── Nome inline no título (padrão ProjectHeader: caneta⇄check⇄spinner) ───
	let tituloEditando = $state(false);
	let tituloDraft = $state('');
	let tituloSaving = $state(false);
	// Valor otimista entre o commit e a resposta do PUT (sem piscar o nome antigo).
	let optNome = $state<string | null>(null);
	let tituloInputEl = $state<HTMLInputElement | null>(null);
	let tituloPenEl = $state<HTMLButtonElement | null>(null);

	const shownNome = $derived(optNome ?? colecao?.nome ?? '');

	async function entrarEdicaoTitulo(): Promise<void> {
		if (tituloSaving || !colecao) return;
		tituloDraft = shownNome;
		tituloEditando = true;
		await tick();
		tituloInputEl?.focus();
		const len = tituloInputEl?.value.length ?? 0;
		tituloInputEl?.setSelectionRange(len, len);
	}

	function cancelarEdicaoTitulo(): void {
		tituloEditando = false;
		void tick().then(() => tituloPenEl?.focus());
	}

	async function commitTitulo(): Promise<void> {
		if (!tituloEditando) return;
		tituloEditando = false;
		const novoNome = tituloDraft.trim();
		// Nome vazio ou igual = cancela silenciosamente (paridade ProjectHeader).
		if (!colecao || !novoNome || novoNome === colecao.nome) return;
		optNome = novoNome;
		tituloSaving = true;
		try {
			const atualizada = await editarColecao(collectionId, { nome: novoNome });
			if (data) data = { ...data, colecao: { ...data.colecao, nome: atualizada.nome } };
			flash.success('Nome da coleção atualizado.');
			void load();
		} catch (err) {
			flash.danger(
				err instanceof ApiClientError ? err.message : 'Não foi possível renomear a coleção.'
			);
		} finally {
			optNome = null;
			tituloSaving = false;
		}
	}

	function onTituloKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape') {
			event.preventDefault();
			cancelarEdicaoTitulo();
			return;
		}
		if (event.key === 'Enter') {
			event.preventDefault();
			void commitTitulo();
		}
	}

	// preventDefault segura o foco no input: o clique na caneta vira "salvar" (não blur).
	function onPenMousedown(event: MouseEvent): void {
		if (tituloEditando) event.preventDefault();
	}

	function onPenClick(): void {
		if (tituloEditando) void commitTitulo();
		else void entrarEdicaoTitulo();
	}

	// ── Popover de ícone/cor ancorado ao tile ────────────────────────────────
	let tileOpen = $state(false);
	let tileSaving = $state(false);
	let tileBtnEl = $state<HTMLButtonElement | null>(null);
	let tilePopEl = $state<HTMLDivElement | null>(null);

	function alternarTilePopover(): void {
		tileOpen = !tileOpen;
		if (tileOpen) void tick().then(() => tilePopEl?.focus());
	}

	function fecharTilePopover(): void {
		tileOpen = false;
		tileBtnEl?.focus();
	}

	$effect(() => {
		if (!tileOpen) return;
		const fecharSeFora = (event: PointerEvent): void => {
			const alvo = event.target as Node;
			if (tilePopEl?.contains(alvo) || tileBtnEl?.contains(alvo)) return;
			tileOpen = false;
		};
		const fecharComEsc = (event: KeyboardEvent): void => {
			if (event.key !== 'Escape') return;
			event.stopPropagation();
			fecharTilePopover();
		};
		window.addEventListener('pointerdown', fecharSeFora, true);
		window.addEventListener('keydown', fecharComEsc, true);
		return () => {
			window.removeEventListener('pointerdown', fecharSeFora, true);
			window.removeEventListener('keydown', fecharComEsc, true);
		};
	});

	async function aplicarIdentidade(parcial: {
		icone?: CollectionIconId;
		cor?: CollectionColorId;
	}): Promise<void> {
		if (tileSaving || !data) return;
		tileSaving = true;
		try {
			const atualizada = await editarColecao(collectionId, parcial);
			data = {
				...data,
				colecao: { ...data.colecao, icone: atualizada.icone, cor: atualizada.cor }
			};
			void load();
		} catch (err) {
			flash.danger(
				err instanceof ApiClientError ? err.message : 'Não foi possível atualizar a coleção.'
			);
		} finally {
			tileSaving = false;
		}
	}

	const labelCls = 'text-xs font-medium text-text-secondary';
</script>

<svelte:head>
	<title>ProjetosRJ — {colecao?.nome ?? convite?.nome ?? 'Coleção'}</title>
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
	{:else if loadState === 'convite' && convite}
		<ColecaoConvitePendente {convite} onRespondido={onConviteRespondido} />
	{:else if colecao}
		<!-- Header-card: tile + nome + ações; linha de meta embutida. -->
		<div class="relative rounded-xl border border-border-subtle bg-surface shadow-sm">
			<PageHeader compact embedded class="min-h-[3.5rem]" labelId="colecao-title">
				{#snippet titleContent()}
					<span class="group/titulo inline-flex max-w-full items-center gap-2 align-middle">
						{#if podeEditarIdentidade}
							<button
								type="button"
								bind:this={tileBtnEl}
								onclick={alternarTilePopover}
								aria-haspopup="dialog"
								aria-expanded={tileOpen}
								aria-label="Alterar ícone e cor da coleção"
								class="shrink-0 rounded-md transition-opacity duration-fast hover:opacity-80 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
							>
								<ColecaoIconTile icone={colecao.icone} cor={colecao.cor} size={32} />
							</button>
						{:else}
							<ColecaoIconTile icone={colecao.icone} cor={colecao.cor} size={32} />
						{/if}
						{#if tituloEditando}
							<input
								bind:this={tituloInputEl}
								bind:value={tituloDraft}
								type="text"
								aria-label="Nome da coleção"
								onkeydown={onTituloKeydown}
								onblur={() => void commitTitulo()}
								class="h-8 w-72 min-w-0 max-w-full rounded-md border border-brand bg-surface px-2 font-heading text-xl font-bold leading-tight text-brand focus:outline-none"
							/>
						{:else}
							<span class="min-w-0 truncate">{shownNome}</span>
						{/if}
						{#if isFavoritos}
							<span
								class="shrink-0 rounded-sm border border-border-subtle bg-wash-neutral px-2 py-0.5 text-2xs font-medium text-text-secondary"
							>
								Padrão
							</span>
						{/if}
						{#if podeEditarIdentidade}
							<button
								type="button"
								bind:this={tituloPenEl}
								disabled={tituloSaving}
								aria-label={tituloEditando ? 'Salvar nome da coleção' : 'Editar nome da coleção'}
								onmousedown={onPenMousedown}
								onclick={onPenClick}
								class="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-text-muted transition-opacity duration-fast hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-brand group-hover/titulo:opacity-100 group-focus-within/titulo:opacity-100 {tituloEditando ||
								tituloSaving
									? 'opacity-100'
									: 'opacity-0'}"
							>
								{#if tituloSaving}
									<i class="fas fa-spinner fa-spin text-xs" aria-hidden="true"></i>
								{:else if tituloEditando}
									<i class="fas fa-check text-xs" aria-hidden="true"></i>
								{:else}
									<AppIcon id="edicao" size={14} />
								{/if}
							</button>
						{/if}
					</span>
				{/snippet}
				{#snippet actions()}
					{#if podeSair}
						<Button size="sm" variant="ghost" onclick={() => void confirmarSaida()}>
							Sair da coleção
						</Button>
					{/if}
					{#if !isFavoritos && isDono}
						<Button size="sm" variant="secondary" onclick={() => (shareOpen = true)}>
							Compartilhar
						</Button>
					{/if}
					{#if podeMexerNosItens}
						<Button size="sm" onclick={() => (pickerOpen = true)}>
							{#snippet icon()}
								<i class="fas fa-plus" aria-hidden="true"></i>
							{/snippet}
							Adicionar projetos
						</Button>
					{/if}
				{/snippet}
			</PageHeader>
			{#if tileOpen}
				<!-- Overlay absoluto abaixo do tile: não altera a altura da barra. -->
				<div
					bind:this={tilePopEl}
					role="dialog"
					aria-label="Alterar ícone e cor da coleção"
					tabindex="-1"
					class="absolute left-4 top-[3.25rem] z-30 flex flex-col gap-3 rounded-lg border border-border-subtle bg-surface p-3 shadow-lg focus:outline-none"
				>
					<div class="flex flex-col gap-2">
						<span id="tile-icone-label" class={labelCls}>Ícone</span>
						<div role="group" aria-labelledby="tile-icone-label" class="grid grid-cols-4 gap-2">
							{#each COLECAO_ICONE_OPTIONS as opcao (opcao.id)}
								{@const ativo = colecao.icone === opcao.id}
								<button
									type="button"
									aria-pressed={ativo}
									aria-label={opcao.label}
									disabled={tileSaving}
									onclick={() => void aplicarIdentidade({ icone: opcao.id })}
									class="grid h-9 w-9 place-items-center rounded-md border transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-60 {ativo
										? COLECAO_ICONE_ATIVO_CLASS[colecao.cor]
										: 'border-border-subtle text-text-secondary hover:bg-surface-muted'}"
								>
									<svg
										width="18"
										height="18"
										viewBox="0 0 24 24"
										fill="currentColor"
										aria-hidden="true"
									>
										{#each COLLECTION_ICONS[opcao.id] as p (p.d)}
											<path d={p.d} opacity={p.opacity} fill-rule={p.fillRule} />
										{/each}
									</svg>
								</button>
							{/each}
						</div>
					</div>
					<div class="flex flex-col gap-2">
						<span id="tile-cor-label" class={labelCls}>Cor</span>
						<div role="group" aria-labelledby="tile-cor-label" class="flex gap-2">
							{#each COLECAO_COR_OPTIONS as opcao (opcao.id)}
								{@const ativo = colecao.cor === opcao.id}
								<button
									type="button"
									aria-pressed={ativo}
									aria-label={opcao.label}
									disabled={tileSaving}
									onclick={() => void aplicarIdentidade({ cor: opcao.id })}
									class="grid h-8 w-8 place-items-center rounded-md border-2 transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1 disabled:opacity-60 {opcao.wash} {ativo
										? opcao.ativo
										: 'border-transparent hover:border-border-subtle'}"
								>
									<span class="h-3.5 w-3.5 rounded-full {opcao.dot}" aria-hidden="true"></span>
								</button>
							{/each}
						</div>
					</div>
				</div>
			{/if}
			<div
				class="flex min-h-[calc(var(--control-h-md)+1.25rem)] flex-wrap items-center gap-x-3 gap-y-1 border-t border-border-subtle px-4 py-2.5 text-sm text-text-secondary"
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
							{formatIsoDateBR(prazoMaisDistante)}
						</time>
					</span>
				{/if}
				{#if procedencia}
					<span class="ml-auto text-xs text-text-muted">{procedencia}</span>
				{/if}
			</div>
		</div>

		{#if podeSair}
			<ColecaoConviteExtraBanner
				{collectionId}
				papelAtual={colecao.papel}
				onAceito={recarregarTudo}
			/>
		{/if}

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

		<!-- Tabela de projetos da coleção (filtros client-side, lixeira por linha). -->
		<ColecaoProjetosTabela
			{colecao}
			{rows}
			ocupado={loadState !== 'ready'}
			podeIncluir={podeMexerNosItens}
			{meuId}
			onAdicionar={() => (pickerOpen = true)}
			onRemover={(row) => void confirmarRemocao(row)}
		/>

		<!-- Cronograma das etapas (Gantt): fetch próprio, janela fixa de 7 meses. -->
		<div class="rounded-xl border border-border-subtle bg-surface shadow-sm">
			{#if cronoState === 'loading' && !cronoData}
				<div aria-hidden="true" class="flex flex-col gap-4 px-5 py-4">
					<div class="flex items-center gap-3">
						<Skeleton class="h-5 w-56 rounded" />
						<Skeleton class="ml-auto h-3.5 w-80 rounded" />
					</div>
					{#each { length: 3 } as _, i (i)}
						<div class="grid grid-cols-[280px_1fr] items-center gap-4">
							<Skeleton class="h-8 w-4/5 rounded" />
							<Skeleton class="h-3.5 w-full rounded" />
						</div>
					{/each}
				</div>
			{:else if cronoState === 'error'}
				<p class="m-0 px-5 py-6 text-center text-sm text-text-muted">
					Não foi possível carregar o cronograma das etapas.
				</p>
			{:else if cronoData}
				<CollectionGantt projetos={cronoData.projetos} />
			{/if}
		</div>
	{/if}
</section>

<!-- Compartilhar: gestão de acessos da coleção (só dono). -->
{#if shareOpen && colecao}
	<CompartilharColecaoModal
		{colecao}
		onClose={() => (shareOpen = false)}
		onChanged={recarregarTudo}
	/>
{/if}

<!-- Adicionar projetos: o picker lista só o que o backend aceita deste papel. -->
{#if pickerOpen}
	<ColecaoAdicionarProjetosModal
		{collectionId}
		{idsNaColecao}
		visibilidade={pickerVisibilidade}
		onClose={() => (pickerOpen = false)}
		onAdicionados={recarregarTudo}
	/>
{/if}
