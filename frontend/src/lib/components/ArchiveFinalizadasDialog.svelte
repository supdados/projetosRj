<script lang="ts">
	/**
	 * Card modal "Arquivar concluídas" (proposta C do canvas de design): o título
	 * diz quantas saem e a lista de seleção fica recolhida em "Revisar" — o
	 * caminho rápido é só confirmar. Aberta, a lista segue o desenho da proposta
	 * A (caixa, descrição, iniciais do responsável à direita).
	 *
	 * Usado no drawer "Tarefas da etapa", no cabeçalho de cada projeto da lista
	 * de Tarefas e no "Arquivar finalizados" global (lista e Kanban). Recebe a
	 * revisão já consultada (`startArchiveReview`) e faz ele mesmo a chamada do
	 * lote, devolvendo o resultado em `onArchived`; quem abre decide o toast e o
	 * re-fetch. Não passa por `confirmAction()`, que só aceita texto.
	 */
	import { onMount, tick } from 'svelte';
	import { fade, slide } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';
	import { prefersReducedMotion } from 'svelte/motion';
	import { ApiClientError } from '$lib/api/client';
	import { focusTrap } from '$lib/actions/focusTrap';
	import FeedbackIcon from '$lib/components/FeedbackIcon.svelte';
	import StateBanner from '$lib/components/StateBanner.svelte';
	import type { ArchiveFinalizadasResult } from '$lib/types/tasks';
	import { confirmArchiveReview, tarefasLabel, type ArchiveReview } from '$lib/utils/taskArchive';

	interface Props {
		review: ArchiveReview;
		onCancel: () => void;
		onArchived: (result: ArchiveFinalizadasResult) => void;
	}

	let { review, onCancel, onArchived }: Props = $props();

	// Guarda as DESMARCADAS: o card nasce com tudo marcado sem copiar a prop.
	let desmarcadas = $state<number[]>([]);
	let aberto = $state(false);
	let busy = $state(false);
	let error = $state<string | null>(null);
	let confirmEl = $state<HTMLButtonElement | null>(null);

	const candidatas = $derived(review.candidatas);
	const selecionadas = $derived(candidatas.filter((t) => !desmarcadas.includes(t.id)));
	const todasMarcadas = $derived(selecionadas.length === candidatas.length);
	const nenhumaMarcada = $derived(selecionadas.length === 0);
	// Lote de vários projetos (hub global): a linha precisa dizer de qual é.
	const mostrarProjeto = $derived(new Set(candidatas.map((t) => t.project_titulo)).size > 1);
	const titulo = $derived(
		`Arquivar ${tarefasLabel(selecionadas.length)} ${selecionadas.length === 1 ? 'concluída' : 'concluídas'}?`
	);

	// Mesma régua do painel de comentários do hub (TaskHubTaskRow): 240ms com
	// desaceleração. O card é centralizado, então cresce para os dois lados —
	// por isso a altura anima em vez de saltar.
	const slideParams = $derived({ duration: prefersReducedMotion.current ? 0 : 240, easing: cubicOut });
	const fadeParams = $derived({ duration: prefersReducedMotion.current ? 0 : 150 });

	// Ação restaurável: o foco entra no confirmar (como o ConfirmDialog de tom
	// brand). `tick` deixa o focusTrap focar primeiro.
	onMount(() => {
		void tick().then(() => confirmEl?.focus());
	});

	function toggleTarefa(taskId: number): void {
		desmarcadas = desmarcadas.includes(taskId)
			? desmarcadas.filter((id) => id !== taskId)
			: [...desmarcadas, taskId];
	}

	function toggleTodas(): void {
		desmarcadas = todasMarcadas ? candidatas.map((t) => t.id) : [];
	}

	async function confirmar(): Promise<void> {
		if (busy || nenhumaMarcada) return;
		busy = true;
		error = null;
		try {
			onArchived(await confirmArchiveReview(review, selecionadas.map((t) => t.id)));
		} catch (err) {
			error = err instanceof ApiClientError ? err.message : 'Erro ao arquivar tarefas.';
			busy = false;
		}
	}

	function cancelar(): void {
		if (!busy) onCancel();
	}

	/** Esc fecha só o card; `preventDefault` avisa drawers abaixo para não fecharem. */
	function onDialogKeydown(event: KeyboardEvent): void {
		if (event.key !== 'Escape') return;
		event.preventDefault();
		cancelar();
	}

	function onBackdropClick(event: MouseEvent): void {
		if (event.target === event.currentTarget) cancelar();
	}

	const CHECKBOX =
		'h-4 w-4 shrink-0 rounded border-border-subtle text-brand focus:ring-0 focus:ring-offset-0 focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-60';
</script>

<div
	class="fixed inset-0 z-modal flex items-center justify-center bg-overlay p-4"
	role="presentation"
	onclick={onBackdropClick}
>
	<div
		use:focusTrap
		tabindex="-1"
		role="dialog"
		aria-modal="true"
		aria-labelledby="archive-finalizadas-title"
		onkeydown={onDialogKeydown}
		class="archive-dialog flex max-h-[calc(100vh-2rem)] w-full max-w-[460px] animate-modal-slide-in flex-col gap-5 overflow-hidden rounded-[14px] border border-border-subtle bg-surface p-6 shadow-modal focus:outline-none"
	>
		<header class="flex shrink-0 items-start gap-3">
			<FeedbackIcon id="archive" size={24} class="mt-px text-brand" />
			<h3
				id="archive-finalizadas-title"
				class="text-xl font-bold leading-snug tracking-tight text-text-primary"
			>
				{titulo}
			</h3>
		</header>

		<!-- Lista recolhível. A barra é a MESMA aberta ou fechada (contagem à
		     esquerda, ações à direita): abrir só acrescenta "Desmarcar todas" e
		     desliza as linhas por baixo — nada troca de lugar nem salta. -->
		<div class="flex min-h-0 flex-col overflow-hidden rounded-control border border-border-subtle">
			<div class="flex min-h-[48px] shrink-0 items-center gap-3 bg-surface-muted px-4 py-1.5">
				<span class="flex-1 whitespace-nowrap text-sm font-medium text-text-primary">
					{selecionadas.length} de {candidatas.length} selecionadas
				</span>
				{#if aberto}
					<span class="flex items-center gap-1" transition:fade={fadeParams}>
						<button
							type="button"
							onclick={toggleTodas}
							disabled={busy}
							class="whitespace-nowrap rounded-md px-2 py-1.5 text-sm font-semibold text-brand transition-colors duration-fast hover:bg-wash-neutral focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-60"
						>
							{todasMarcadas ? 'Desmarcar todas' : 'Selecionar todas'}
						</button>
						<span class="h-4 w-px bg-border-subtle" aria-hidden="true"></span>
					</span>
				{/if}
				<button
					type="button"
					aria-expanded={aberto}
					aria-controls="archive-finalizadas-lista"
					onclick={() => (aberto = !aberto)}
					class="-mr-2 inline-flex items-center gap-1.5 whitespace-nowrap rounded-md px-2 py-1.5 text-sm font-semibold text-brand transition-colors duration-fast hover:bg-wash-neutral focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
				>
					{aberto ? 'Ocultar' : 'Revisar'}
					<svg
						viewBox="0 0 24 24"
						class="h-3.5 w-3.5 transition-transform duration-base ease-out {aberto ? 'rotate-180' : ''}"
						fill="none"
						stroke="currentColor"
						stroke-width="2.2"
						stroke-linecap="round"
						stroke-linejoin="round"
						aria-hidden="true"
					>
						<path d="m6 9 6 6 6-6" />
					</svg>
				</button>
			</div>

			{#if aberto}
				<!-- Altura máxima própria (e não encolher no flex): encolhida pelo
				     card, a lista transbordava e o gutter da barra de rolagem cortava
				     os divisores antes da borda. -->
				<ul
					id="archive-finalizadas-lista"
					transition:slide={slideParams}
					class="archive-scroll thin-scroll m-0 max-h-[min(296px,calc(100vh-18rem))] shrink-0 list-none divide-y divide-border-subtle overflow-y-auto border-t border-border-subtle p-0"
				>
					{#each candidatas as task (task.id)}
						{@const marcada = !desmarcadas.includes(task.id)}
						{@const responsavel = task.assignees[0]}
						<li>
							<label
								class="flex min-h-[48px] cursor-pointer items-center gap-3 px-4 py-2.5 transition-colors duration-fast hover:bg-surface-muted"
							>
								<input
									type="checkbox"
									checked={marcada}
									onchange={() => toggleTarefa(task.id)}
									disabled={busy}
									class={CHECKBOX}
								/>
								<span class="flex min-w-0 flex-1 flex-col">
									<span
										class="line-clamp-2 break-words text-sm leading-snug transition-colors duration-fast {marcada
											? 'text-text-primary'
											: 'text-text-muted'}"
									>
										{task.descricao}
									</span>
									{#if mostrarProjeto}
										<span class="truncate text-xs text-text-muted">
											{task.project_titulo ?? 'Sem projeto'}
										</span>
									{/if}
								</span>
								{#if responsavel}
									<span
										title={task.assignees.map((a) => a.name).join(', ')}
										class="inline-flex h-6 min-w-[1.5rem] shrink-0 items-center justify-center rounded-full bg-wash-neutral px-1 text-[10px] font-semibold text-text-secondary"
									>
										{responsavel.initials}{task.assignees.length > 1
											? ` +${task.assignees.length - 1}`
											: ''}
									</span>
								{/if}
							</label>
						</li>
					{/each}
				</ul>
			{/if}
		</div>

		{#if error}
			<StateBanner tone="danger" title={error} />
		{/if}

		<footer class="flex shrink-0 justify-end gap-2.5">
			<button
				type="button"
				disabled={busy}
				onclick={cancelar}
				class="rounded-sm border border-border-strong bg-surface px-4 py-2.5 text-md font-semibold text-text-secondary transition-colors duration-fast hover:border-text-muted hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
			>
				Cancelar
			</button>
			<button
				bind:this={confirmEl}
				type="button"
				disabled={busy || nenhumaMarcada}
				onclick={() => void confirmar()}
				class="rounded-sm bg-brand px-4 py-2.5 text-md font-semibold text-on-brand transition-opacity duration-fast hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-text-faint disabled:hover:opacity-100"
			>
				{busy ? 'Arquivando…' : 'Arquivar'}
			</button>
		</footer>
	</div>
</div>

<style>
	/* Checkbox nativo na cor da marca (sem isso o macOS pinta no azul do sistema). */
	.archive-dialog input[type='checkbox'] {
		accent-color: var(--ds-color-fill-brand);
	}

	/* Sombras de rolagem só em CSS: as faixas `local` (cor do fundo) andam com o
	 * conteúdo e cobrem as sombras `scroll` nas pontas; a sombra só aparece do
	 * lado em que ainda há linhas — sem isso o corte parecia uma linha vazia. */
	.archive-scroll {
		background:
			linear-gradient(var(--ds-color-surface-base) 30%, transparent) top / 100% 24px no-repeat local,
			linear-gradient(transparent, var(--ds-color-surface-base) 70%) bottom / 100% 24px no-repeat local,
			radial-gradient(farthest-side at 50% 0, rgb(0 0 0 / 0.14), transparent) top / 100% 10px no-repeat scroll,
			radial-gradient(farthest-side at 50% 100%, rgb(0 0 0 / 0.14), transparent) bottom / 100% 10px no-repeat scroll,
			var(--ds-color-surface-base);
	}

	@media (prefers-reduced-motion: reduce) {
		.archive-dialog {
			animation-duration: 0ms;
		}
	}
</style>
