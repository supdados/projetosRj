<script lang="ts">
	/**
	 * Composer inline por COLUNA do Kanban (paridade com
	 * `static/js/modules/kanban/composer.js`). Cria uma tarefa diretamente na
	 * coluna do status, com:
	 *   - project picker (select buscável simples) — populado pelas opções do hub;
	 *   - select de etapa carregado SOB DEMANDA após escolher o projeto;
	 *   - multi-select simples de responsável (sugestões do hub por projeto);
	 *   - prioridade e tipo;
	 *   - estado `is-saving` (loading) durante o submit;
	 *   - Enter (sem Shift) submete; Escape fecha e limpa.
	 *
	 * Validações client (paridade):
	 *   - descrição vazia -> apenas re-foca o textarea (SEM alert);
	 *   - projeto não selecionado -> aviso inline 'Selecione um projeto para criar
	 *     a tarefa.' + foca o picker;
	 *   - abrir responsável sem projeto -> aviso 'Selecione um projeto para
	 *     escolher responsáveis.'.
	 *
	 * Em sucesso insere o card otimista na coluna do status (via `onCreated`) e
	 * fecha/reseta — SEM toast/som/confete (paridade exata). Em erro mostra a
	 * mensagem do backend inline.
	 */
	import { createTarefa, fetchHubResponsaveis } from '$lib/api/tasks';
	import { fetchProjectDetail } from '$lib/api/projectDetail';
	import { ApiClientError } from '$lib/api/client';
	import type { TaskProjectOption } from '$lib/types/tasks';
	import type { BoardCard } from '$lib/types/board';
	import type { EtapaDetail } from '$lib/types/projectDetail';
	import type { TaskStatus } from '$lib/utils/taskStatus';

	interface Props {
		/** Status (coluna) onde a tarefa será criada. */
		status: TaskStatus;
		/** Opções de projeto do hub (já respeitam o escopo do usuário). */
		projectOptions: TaskProjectOption[];
		/** Filtro de projeto ativo (pré-seleciona o picker, paridade com o hub). */
		defaultProject?: string;
		/** CONTROLADO pelo pai: este composer está aberto? (abrir um fecha os demais) */
		open: boolean;
		/** Recebe o card recém-criado para inserção otimista na coluna. */
		onCreated: (card: BoardCard, status: TaskStatus) => void;
		/** Pede ao pai para abrir este composer (e fechar os demais). */
		onRequestOpen: (status: TaskStatus) => void;
		/** Pede ao pai para fechar este composer. */
		onRequestClose: () => void;
	}

	let {
		status,
		projectOptions,
		defaultProject = '',
		open,
		onCreated,
		onRequestOpen,
		onRequestClose
	}: Props = $props();
	let saving = $state(false);
	let errorMessage = $state<string | null>(null);

	// Seed do filtro de projeto ativo (paridade com o hub). Não é reativo de
	// propósito: o usuário pode trocar o projeto livremente no composer.
	let project = $state<string>('');
	let etapa = $state<string>('');
	let descricao = $state<string>('');
	let responsavel = $state<string>('');
	let prioridade = $state<string>('');
	let tipo = $state<string>('');

	let etapaOptions = $state<EtapaDetail[]>([]);
	let etapaLoading = $state(false);
	let responsavelOptions = $state<{ id: number; name: string }[]>([]);

	let textareaEl = $state<HTMLTextAreaElement | null>(null);
	let projectEl = $state<HTMLSelectElement | null>(null);

	const PRIORIDADE_OPTIONS = [
		{ value: '', label: 'Prioridade' },
		{ value: 'baixa', label: 'Baixa' },
		{ value: 'media', label: 'Média' },
		{ value: 'alta', label: 'Alta' },
		{ value: 'urgente', label: 'Urgente' }
	];
	// Sem "implementacao": é tipo LEGADO (`LEGACY_TIPOS`) — a criação via
	// /api/tarefas só aceita VALID_TIPOS e descartaria o valor silenciosamente.
	const TIPO_OPTIONS = [
		{ value: '', label: 'Tipo' },
		{ value: 'bug', label: 'Bug' },
		{ value: 'melhoria', label: 'Melhoria' },
		{ value: 'duvida', label: 'Dúvida' },
		{ value: 'outros', label: 'Outros' }
	];

	function requestOpen(): void {
		onRequestOpen(status);
		// Foco no textarea após o paint (paridade: focus ~30ms depois).
		setTimeout(() => textareaEl?.focus(), 30);
	}

	function resetFields(): void {
		saving = false;
		errorMessage = null;
		project = '';
		etapaOptions = [];
		responsavelOptions = [];
		etapa = '';
		descricao = '';
		responsavel = '';
		prioridade = '';
		tipo = '';
	}

	function requestClose(): void {
		resetFields();
		onRequestClose();
	}

	// Limpa os campos ao fechar (por abrir outro composer) — paridade com
	// `closeComposer(true)`. Ao ABRIR, semeia o projeto com o filtro ativo do hub
	// e carrega etapas/responsáveis (paridade com a pré-seleção do composer).
	let wasOpen = false;
	$effect(() => {
		if (open && !wasOpen) {
			if (defaultProject) {
				project = defaultProject;
				void onProjectChange();
			}
		} else if (!open && wasOpen) {
			resetFields();
		}
		wasOpen = open;
	});

	async function onProjectChange(): Promise<void> {
		etapa = '';
		etapaOptions = [];
		responsavelOptions = [];
		if (!project) return;
		await Promise.all([loadEtapas(), loadResponsaveis()]);
	}

	async function loadEtapas(): Promise<void> {
		if (!project) return;
		etapaLoading = true;
		try {
			const data = await fetchProjectDetail(Number(project));
			etapaOptions = data.etapas.filter((e) => !e.is_google_meeting);
		} catch {
			etapaOptions = [];
		} finally {
			etapaLoading = false;
		}
	}

	async function loadResponsaveis(): Promise<void> {
		if (!project) return;
		try {
			const data = await fetchHubResponsaveis({ project });
			responsavelOptions = data.users;
		} catch {
			responsavelOptions = [];
		}
	}

	function onTextareaKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape') {
			event.preventDefault();
			requestClose();
			return;
		}
		if (event.key === 'Enter' && !event.shiftKey) {
			event.preventDefault();
			void submit();
		}
	}

	async function submit(): Promise<void> {
		if (saving) return;
		errorMessage = null;
		// Descrição vazia: apenas re-foca (paridade — sem alert).
		if (!descricao.trim()) {
			textareaEl?.focus();
			return;
		}
		// Sem projeto: aviso inline + foca o picker (paridade com o alert legado).
		if (!project) {
			errorMessage = 'Selecione um projeto para criar a tarefa.';
			projectEl?.focus();
			return;
		}

		saving = true;
		try {
			const { task } = await createTarefa({
				project,
				etapa: etapa || undefined,
				descricao: descricao.trim(),
				status,
				responsavel: responsavel || null,
				prioridade: prioridade || null,
				tipo_pedido: tipo || null
			});
			// Inserção otimista na coluna do status escolhido (SEM toast/som/confete).
			onCreated(task as unknown as BoardCard, status);
			requestClose();
		} catch (err) {
			errorMessage =
				err instanceof ApiClientError ? err.message : 'Erro ao adicionar tarefa.';
			saving = false;
		}
	}
</script>

<!--
	Composer inline da coluna — Variação B: o botão `+ adicionar` é um traço
	discreto e transparente (borda tracejada, texto apagado) que só ganha cor
	no hover. O formulário reproduz `.task-items-kanban-add-form` do legado
	(borda, fundo branco, gap 0.46rem). `is-saving` aplica opacity 0.72.
-->
{#if !open}
	<button
		type="button"
		onclick={requestOpen}
		class="flex w-full items-center justify-center gap-1 rounded-lg border border-dashed border-border-strong bg-transparent px-[0.48rem] py-[0.42rem] text-xs font-semibold text-text-muted transition-all duration-fast hover:border-primary-500 hover:bg-surface-muted hover:text-text-secondary focus:outline-none focus-visible:border-primary-500 focus-visible:ring-2 focus-visible:ring-primary-500"
	>
		+ adicionar
	</button>
{:else}
	<form
		class="flex flex-col gap-[0.46rem] rounded-lg border border-border-subtle bg-surface p-2 shadow-md transition-opacity duration-fast {saving
			? 'pointer-events-none opacity-[0.72]'
			: ''}"
		aria-label="Nova tarefa em {status}"
		onsubmit={(e) => {
			e.preventDefault();
			void submit();
		}}
	>
		<select
			bind:this={projectEl}
			bind:value={project}
			onchange={() => void onProjectChange()}
			disabled={saving}
			aria-label="Projeto"
			class="rounded-lg border border-border-subtle bg-surface px-2 py-1.5 text-xs text-text-primary focus:border-primary-500 focus:outline-none disabled:opacity-60"
		>
			<option value="">Selecione o projeto…</option>
			{#each projectOptions as option (option.value)}
				<option value={option.value}>{option.label}</option>
			{/each}
		</select>

		{#if project}
			<select
				bind:value={etapa}
				disabled={saving || etapaLoading}
				aria-label="Etapa"
				class="rounded-lg border border-border-subtle bg-surface px-2 py-1.5 text-xs text-text-primary focus:border-primary-500 focus:outline-none disabled:opacity-60"
			>
				<option value="">{etapaLoading ? 'Carregando etapas…' : 'Sem etapa'}</option>
				{#each etapaOptions as e (e.id)}
					<option value={e.id}>{e.descricao ?? `Etapa ${e.id}`}{e.done ? ' (concluída)' : ''}</option>
				{/each}
			</select>
		{/if}

		<textarea
			bind:this={textareaEl}
			bind:value={descricao}
			onkeydown={onTextareaKeydown}
			disabled={saving}
			rows="2"
			placeholder="Descreva a tarefa…"
			aria-label="Descrição da tarefa"
			class="min-h-[64px] w-full resize-y rounded-md border border-border-subtle bg-surface px-[0.48rem] py-[0.38rem] text-xs leading-normal text-text-primary transition-colors duration-fast focus:border-primary-500 focus:outline-none disabled:opacity-60 2xl:text-sm"
		></textarea>

		{#if project && responsavelOptions.length > 0}
			<select
				bind:value={responsavel}
				disabled={saving}
				aria-label="Responsável"
				class="rounded-lg border border-border-subtle bg-surface px-2 py-1.5 text-xs text-text-primary focus:border-primary-500 focus:outline-none disabled:opacity-60"
			>
				<option value="">Sem responsável</option>
				{#each responsavelOptions as user (user.id)}
					<option value={user.name}>{user.name}</option>
				{/each}
			</select>
		{/if}

		<div class="flex gap-2">
			<select
				bind:value={prioridade}
				disabled={saving}
				aria-label="Prioridade"
				class="flex-1 rounded-lg border border-border-subtle bg-surface px-2 py-1.5 text-xs text-text-primary focus:border-primary-500 focus:outline-none disabled:opacity-60"
			>
				{#each PRIORIDADE_OPTIONS as opt (opt.value)}
					<option value={opt.value}>{opt.label}</option>
				{/each}
			</select>
			<select
				bind:value={tipo}
				disabled={saving}
				aria-label="Tipo de pedido"
				class="flex-1 rounded-lg border border-border-subtle bg-surface px-2 py-1.5 text-xs text-text-primary focus:border-primary-500 focus:outline-none disabled:opacity-60"
			>
				{#each TIPO_OPTIONS as opt (opt.value)}
					<option value={opt.value}>{opt.label}</option>
				{/each}
			</select>
		</div>

		{#if errorMessage}
			<p role="alert" class="text-xs text-danger">{errorMessage}</p>
		{/if}

		<div class="flex justify-end gap-[0.34rem]">
			<button
				type="button"
				onclick={requestClose}
				disabled={saving}
				class="h-[30px] rounded-md border border-border-subtle bg-surface px-[0.56rem] text-xs font-semibold text-text-secondary transition-all duration-fast hover:border-border-strong hover:bg-surface-muted hover:text-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
			>
				Cancelar
			</button>
			<button
				type="submit"
				disabled={saving}
				class="h-[30px] rounded-md bg-primary-600 px-[0.56rem] text-xs font-semibold text-primary-fg shadow-sm transition-all duration-fast hover:bg-primary-700 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 disabled:opacity-50"
			>
				{saving ? 'Salvando…' : 'Salvar'}
			</button>
		</div>
	</form>
{/if}
