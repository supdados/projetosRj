<script lang="ts">
	/**
	 * Índice de Coleções (tela 3a). Consome `GET /api/colecoes` via
	 * `$lib/api/collections` (SWR) e renderiza o grid de ColecaoCard —
	 * Favoritos sempre primeiro — com busca e ordenação client-side (o teto é
	 * 20 coleções por usuário; não há filtro server-side).
	 *
	 * Mutações: criar via NovaColecaoModal (2 passos, POST atômico), editar
	 * identidade num modal próprio (mesmo formulário do passo 1), compartilhar
	 * (CompartilharColecaoModal) e apagar com confirmação destrutiva
	 * (`confirmAction`). Toda escrita invalida o cache no client de API; a tela
	 * só re-busca.
	 *
	 * Fase 2: o GET já devolve as coleções compartilhadas comigo depois das
	 * minhas — os chips de escopo apenas ESTREITAM a lista (nenhum ativo = tudo)
	 * e só aparecem quando existe alguma coleção alheia. Editar/compartilhar/
	 * apagar seguem exclusivos do dono.
	 */
	import { onMount, tick } from 'svelte';
	import { base } from '$app/paths';
	import {
		apagarColecao,
		editarColecao,
		fetchColecoes,
		peekColecoes,
		peekIaSugestoesDisponivel
	} from '$lib/api/collections';
	import { ApiClientError } from '$lib/api/client';
	import type {
		ColecaoResumo,
		ColecaoSugerida,
		CollectionColorId,
		CollectionIconId
	} from '$lib/types/collections';
	import PageHeader from '$lib/components/PageHeader.svelte';
	import Button from '$lib/components/Button.svelte';
	import CountBadge from '$lib/components/CountBadge.svelte';
	import SelectMenu from '$lib/components/SelectMenu.svelte';
	import type { SelectMenuOption } from '$lib/types/selectMenu';
	import FilterChipGroup from '$lib/components/FilterChipGroup.svelte';
	import ColecaoCard from '$lib/components/ColecaoCard.svelte';
	import ColecaoIconTile from '$lib/components/ColecaoIconTile.svelte';
	import NovaColecaoModal from '$lib/components/NovaColecaoModal.svelte';
	import SugerirColecoesModal from '$lib/components/SugerirColecoesModal.svelte';
	import CompartilharColecaoModal from '$lib/components/CompartilharColecaoModal.svelte';
	import Modal from '$lib/components/Modal.svelte';
	import StateBanner from '$lib/components/StateBanner.svelte';
	import LoadErrorState from '$lib/components/LoadErrorState.svelte';
	import ColecoesSkeleton from '$lib/components/skeletons/ColecoesSkeleton.svelte';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import TopnavIcon from '$lib/components/TopnavIcon.svelte';
	import { COLLECTION_ICONS } from '$lib/icons/collectionIcons';
	import { confirmAction } from '$lib/stores/confirm';
	import { flash } from '$lib/stores/flash';

	type LoadState = 'loading' | 'ready' | 'error';
	type Ordenacao = 'criacao' | 'nome';
	/** `''` = nenhum chip ativo, isto é, minhas + compartilhadas comigo. */
	type Escopo = '' | 'minhas' | 'compartilhadas';

	const initialData = peekColecoes();
	let loadState = $state<LoadState>(initialData ? 'ready' : 'loading');
	let colecoes = $state<ColecaoResumo[] | null>(initialData);
	let errorMessage = $state<string>('');

	// Filtros client-side (dataset completo já está na tela).
	let busca = $state('');
	let ordenacao = $state<Ordenacao>('criacao');
	let escopo = $state<Escopo>('');

	const ORDENACAO_OPTIONS: SelectMenuOption[] = [
		{ value: 'criacao', label: 'Data de criação' },
		{ value: 'nome', label: 'Nome' }
	];

	const ESCOPO_OPTIONS = [
		{ id: 'minhas', label: 'Minhas coleções' },
		{ id: 'compartilhadas', label: 'Compartilhadas comigo' }
	];

	let inFlight: AbortController | null = null;

	async function load(): Promise<void> {
		const cached = peekColecoes();
		if (cached) {
			colecoes = cached;
			loadState = 'ready';
		} else {
			loadState = 'loading';
		}
		errorMessage = '';
		inFlight?.abort();
		const controller = new AbortController();
		inFlight = controller;
		try {
			const next = await fetchColecoes(controller.signal);
			if (controller.signal.aborted) return;
			colecoes = next;
			iaDisponivel = peekIaSugestoesDisponivel() ?? false;
			loadState = 'ready';
		} catch (err) {
			if (controller.signal.aborted) return;
			if (err instanceof ApiClientError && err.code === 'unauthenticated') return;
			const message = err instanceof Error ? err.message : 'Falha ao carregar as coleções.';
			// Revalidação falhou com dado stale na tela: mantém o grid e avisa.
			if (colecoes) {
				flash.danger(message);
				return;
			}
			errorMessage = message;
			loadState = 'error';
		}
	}

	onMount(() => {
		void load();
		return () => inFlight?.abort();
	});

	const COMBINING_MARKS = /[̀-ͯ]/g;
	const norm = (s: string): string =>
		s.normalize('NFD').replace(COMBINING_MARKS, '').toLowerCase();

	const temCompartilhada = $derived((colecoes ?? []).some((c) => c.papel !== 'dono'));
	// Sem coleção alheia não há o que estreitar: os chips somem e o escopo é neutro.
	const escopoAtivo = $derived<Escopo>(temCompartilhada ? escopo : '');

	function noEscopo(colecao: ColecaoResumo): boolean {
		if (escopoAtivo === 'minhas') return colecao.papel === 'dono';
		if (escopoAtivo === 'compartilhadas') return colecao.papel !== 'dono';
		return true;
	}

	const visiveis = $derived.by<ColecaoResumo[]>(() => {
		if (!colecoes) return [];
		const termo = norm(busca.trim());
		const filtradas = colecoes.filter((c) => {
			if (!noEscopo(c)) return false;
			if (!termo) return true;
			return norm(c.nome).includes(termo) || norm(c.descricao ?? '').includes(termo);
		});
		filtradas.sort((a, b) => {
			// Favoritos sempre primeiro, independentemente da ordenação.
			if (a.tipo !== b.tipo) return a.tipo === 'favoritos' ? -1 : 1;
			if (ordenacao === 'nome') return a.nome.localeCompare(b.nome, 'pt-BR');
			const porCriacao = b.created_at.localeCompare(a.created_at);
			return porCriacao !== 0 ? porCriacao : b.id - a.id;
		});
		return filtradas;
	});

	const totalColecoes = $derived(colecoes?.length ?? 0);
	const totalProjetos = $derived(
		(colecoes ?? []).reduce((soma, c) => soma + c.projetos, 0)
	);

	// ── Criar ────────────────────────────────────────────────────────────────
	let createOpen = $state(false);
	/** Sugestão de IA aceita: pré-preenche o modal de criação até ele fechar. */
	let sugestaoAceita = $state<ColecaoSugerida | null>(null);

	function fecharCriacao(): void {
		createOpen = false;
		sugestaoAceita = null;
	}

	function onColecaoCriada(colecao: ColecaoResumo): void {
		flash.success(`Coleção "${colecao.nome}" criada.`);
		// Aceite de sugestão: fecha o modal de sugestões; reabrir refaz o GET
		// barato e o cartão aceito já não volta (deixou de ser pendente).
		if (sugestaoAceita) sugerirOpen = false;
		void load();
	}

	// ── Sugerir com IA ───────────────────────────────────────────────────────
	let sugerirOpen = $state(false);
	// Flag vem do GET /api/colecoes; oculto até o servidor confirmar. O 503 em
	// runtime (onIndisponivel) segue como fallback caso a feature caia no meio.
	let iaDisponivel = $state(peekIaSugestoesDisponivel() ?? false);

	function criarDaSugestao(sugestao: ColecaoSugerida): void {
		sugestaoAceita = sugestao;
		createOpen = true;
	}

	// ── Editar (mesmo formulário do passo 1 do modal de criação) ─────────────
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

	let editTarget = $state<ColecaoResumo | null>(null);
	let editNome = $state('');
	let editDescricao = $state('');
	let editIcone = $state<CollectionIconId>('camadas');
	let editCor = $state<CollectionColorId>('primary');
	let editTriedSave = $state(false);
	let editSaving = $state(false);
	let editErro = $state<string | null>(null);
	let editNomeInputEl = $state<HTMLInputElement | null>(null);

	const editNomeInvalido = $derived(editTriedSave && !editNome.trim());

	function abrirEdicao(colecao: ColecaoResumo): void {
		editTarget = colecao;
		editNome = colecao.nome;
		editDescricao = colecao.descricao ?? '';
		editIcone = colecao.icone;
		editCor = colecao.cor;
		editTriedSave = false;
		editSaving = false;
		editErro = null;
		void tick().then(() => editNomeInputEl?.focus());
	}

	function fecharEdicao(): void {
		if (editSaving) return;
		editTarget = null;
	}

	async function salvarEdicao(): Promise<void> {
		if (!editTarget || editSaving) return;
		editTriedSave = true;
		if (!editNome.trim()) {
			editNomeInputEl?.focus();
			return;
		}
		editSaving = true;
		editErro = null;
		try {
			const atualizada = await editarColecao(editTarget.id, {
				nome: editNome.trim(),
				descricao: editDescricao.trim() || null,
				icone: editIcone,
				cor: editCor
			});
			editSaving = false;
			editTarget = null;
			flash.success(`Coleção "${atualizada.nome}" atualizada.`);
			void load();
		} catch (err) {
			editSaving = false;
			editErro =
				err instanceof ApiClientError ? err.message : 'Não foi possível salvar a coleção.';
		}
	}

	// ── Compartilhar (só dono; o modal cuida das concessões) ─────────────────
	let shareTarget = $state<ColecaoResumo | null>(null);

	// ── Apagar ───────────────────────────────────────────────────────────────
	async function confirmarApagar(colecao: ColecaoResumo): Promise<void> {
		const ok = await confirmAction({
			title: `Apagar a coleção "${colecao.nome}"?`,
			description:
				'Os projetos continuam intactos — apenas a coleção deixa de existir. Esta ação não pode ser desfeita.',
			confirmLabel: 'Apagar coleção',
			busyLabel: 'Apagando…',
			run: async () => {
				await apagarColecao(colecao.id);
			}
		});
		if (!ok) return;
		flash.success(`Coleção "${colecao.nome}" apagada.`);
		void load();
	}

	const labelCls = 'text-xs font-medium text-text-secondary';
	const fieldCls =
		'h-[var(--control-h-md)] w-full rounded-control border bg-surface px-3.5 text-md text-text-primary placeholder:text-text-faint transition-colors duration-fast focus:outline-none';
</script>

<svelte:head>
	<title>ProjetosRJ — Coleções</title>
</svelte:head>

<section aria-labelledby="colecoes-title" class="flex flex-col gap-4">
	<!-- CARD ÚNICO header + toolbar (padrão de Projetos/Pendentes/Tarefas). -->
	<div class="rounded-xl border border-border-subtle bg-surface shadow-sm">
		<PageHeader compact embedded class="min-h-[3.5rem]" labelId="colecoes-title">
			{#snippet titleContent()}
				<span>Coleções</span>
				{#if colecoes}
					<CountBadge class="ml-2">
						{totalColecoes}
						{totalColecoes === 1 ? 'coleção' : 'coleções'} · {totalProjetos}
						{totalProjetos === 1 ? 'projeto' : 'projetos'}
					</CountBadge>
				{/if}
			{/snippet}
			{#snippet actions()}
				{#if iaDisponivel}
					<Button variant="secondary" size="sm" onclick={() => (sugerirOpen = true)}>
						{#snippet icon()}
							<i class="fas fa-wand-magic-sparkles" aria-hidden="true"></i>
						{/snippet}
						Sugerir com IA
					</Button>
				{/if}
				<Button size="sm" onclick={() => (createOpen = true)}>
					{#snippet icon()}
						<i class="fas fa-plus" aria-hidden="true"></i>
					{/snippet}
					Nova coleção
				</Button>
			{/snippet}
		</PageHeader>

		<!-- Toolbar embutida: busca + ordenação client-side + escopo do MVP. -->
		<form
			class="flex flex-wrap items-center gap-2 border-t border-border-subtle px-4 py-2.5"
			role="search"
			aria-label="Filtros de coleções"
			onsubmit={(e) => e.preventDefault()}
		>
			<div class="relative w-full min-w-[14rem] max-w-[26rem]">
				<i
					class="fas fa-search pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-sm text-text-muted"
					aria-hidden="true"
				></i>
				<input
					id="colecoesSearch"
					name="search"
					type="search"
					autocomplete="off"
					bind:value={busca}
					aria-label="Buscar coleção"
					placeholder="Buscar coleção"
					class="h-9 w-full rounded-lg border border-border-subtle bg-surface pl-8 pr-2.5 text-md text-text-primary placeholder:text-text-muted transition-colors duration-fast focus:border-brand focus:outline-none"
				/>
			</div>

			<div class="min-w-[13rem]">
				<SelectMenu
					id="colecoesOrdenacao"
					options={ORDENACAO_OPTIONS}
					value={ordenacao}
					onSelect={(v) => (ordenacao = (v ?? 'criacao') as Ordenacao)}
					ariaLabel="Ordenar coleções"
				/>
			</div>

			{#if temCompartilhada}
				<div class="ml-auto">
					<!-- Clicar no chip ativo desliga o filtro e volta a mostrar tudo. -->
					<FilterChipGroup
						label="Escopo das coleções"
						options={ESCOPO_OPTIONS}
						value={escopoAtivo}
						onchange={(id) => (escopo = id === escopoAtivo ? '' : (id as Escopo))}
					/>
				</div>
			{/if}
		</form>
	</div>

	{#if loadState === 'loading' && !colecoes}
		<p role="status" aria-live="polite" class="sr-only">Carregando coleções…</p>
		<ColecoesSkeleton />
	{:else if loadState === 'error'}
		<LoadErrorState message={errorMessage} onRetry={() => load()} />
	{:else if colecoes}
		{#if visiveis.length === 0}
			<!-- Busca sem resultado (mesmo quadro do estado vazio de Projetos). -->
			<div
				role="status"
				aria-live="polite"
				class="rounded-lg border border-dashed border-border-strong bg-surface-muted px-4 py-8 text-center"
			>
				<div
					class="mx-auto mb-3 inline-flex h-14 w-14 items-center justify-center rounded-xl border border-brand-soft bg-wash-neutral text-xl text-brand"
				>
					<AppIcon id="projetos" size={28} />
				</div>
				<h2 class="m-0 font-heading text-xl font-bold text-text-primary">
					Nenhuma coleção encontrada
				</h2>
				<p class="mb-0 mt-1.5 text-sm text-text-muted">
					{#if busca.trim()}
						Nenhuma coleção corresponde a "{busca.trim()}". Ajuste a busca ou crie uma nova.
					{:else if escopoAtivo === 'compartilhadas'}
						Ninguém compartilhou uma coleção com você ainda.
					{:else}
						Você ainda não tem coleções próprias. Crie a primeira.
					{/if}
				</p>
			</div>
		{:else}
			<div class="grid grid-cols-2 gap-4 lg:grid-cols-4" aria-busy={loadState !== 'ready'}>
				{#each visiveis as colecao (colecao.id)}
					{@const gerenciavel = colecao.tipo === 'custom' && colecao.papel === 'dono'}
					<ColecaoCard
						{colecao}
						href={`${base}/colecoes/${colecao.id}`}
						onEditar={gerenciavel ? () => abrirEdicao(colecao) : undefined}
						onCompartilhar={gerenciavel ? () => (shareTarget = colecao) : undefined}
						onApagar={gerenciavel ? () => void confirmarApagar(colecao) : undefined}
					/>
				{/each}

				<!-- Card fantasma: cria coleção (button tracejado, a11y de verdade). -->
				<button
					type="button"
					onclick={() => (createOpen = true)}
					class="flex h-full flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border-strong bg-surface p-4 text-center transition-ui duration-fast hover:border-brand hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
				>
					<span
						class="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-wash-brand text-brand"
						aria-hidden="true"
					>
						<TopnavIcon kind="colecoes" active={false} />
					</span>
					<span class="text-sm font-semibold text-text-primary">Criar uma nova coleção</span>
				</button>
			</div>
		{/if}
	{/if}
</section>

<!-- Antes do NovaColecaoModal no DOM: o de criação empilha por cima e fica com o Esc. -->
<SugerirColecoesModal
	open={sugerirOpen}
	onClose={() => (sugerirOpen = false)}
	onCriar={criarDaSugestao}
	onIndisponivel={() => (iaDisponivel = false)}
/>

<NovaColecaoModal
	open={createOpen}
	nomeInicial={sugestaoAceita?.nome}
	descricaoInicial={sugestaoAceita?.descricao ?? undefined}
	projectIdsIniciais={sugestaoAceita?.project_ids}
	sugestaoId={sugestaoAceita?.id}
	onClose={fecharCriacao}
	onCreated={onColecaoCriada}
/>

{#if shareTarget}
	<CompartilharColecaoModal
		colecao={shareTarget}
		onClose={() => (shareTarget = null)}
		onChanged={() => void load()}
	/>
{/if}

<!-- Edição de identidade: mesmo formulário do passo 1 do modal de criação. -->
{#if editTarget}
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
