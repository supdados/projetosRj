<script lang="ts">
	/**
	 * Painel read-only de uma reunião Google de etapa (Detalhe do Projeto, Fase 6).
	 *
	 * Equivalente ao popover `.cal-event-popover` do legado
	 * (static/js/pages/projects/detail/06-project-meetings.js openMeetingPopover):
	 * horário, dono (owner_email), local, descrição, aviso de sync error, link
	 * "Abrir Meet" + copiar (toast efêmero "Link copiado!" ~1.7s), e as ações
	 * condicionais a `can_manage`/`can_edit` (Editar, Apagar) ou o bloqueio
	 * (fa-lock) quando o usuário não é a conta Google dona.
	 *
	 * CONTROLADO: recebe o bloco `meeting` da etapa e emite callbacks; a PÁGINA
	 * abre o modal de edição (CalendarEventModal) e chama a API. Sem som/confete —
	 * a fidelidade aqui é toasts + spinners + diálogo de confirmação.
	 */
	import type { EtapaMeeting } from '$lib/types/projectDetail';
	import Badge from './Badge.svelte';

	interface Props {
		meeting: EtapaMeeting;
		/** Operação de exclusão em andamento (spinner no botão Apagar). */
		busy?: boolean;
		/** Abre o modal de edição da reunião. */
		onEdit: () => void;
		/** Exclui a reunião (a página confirma e chama a API). */
		onDelete: () => void;
	}

	let { meeting, busy = false, onEdit, onDelete }: Props = $props();

	let copied = $state(false);
	let copyResetTimer: ReturnType<typeof setTimeout> | null = null;

	const hasSyncError = $derived(meeting.sync_status === 'error');

	/** Copia o link do Meet e mostra o feedback "Link copiado!" por ~1.7s. */
	async function copyMeetLink(): Promise<void> {
		if (!meeting.meet_link) return;
		try {
			await navigator.clipboard.writeText(meeting.meet_link);
			copied = true;
			if (copyResetTimer) clearTimeout(copyResetTimer);
			copyResetTimer = setTimeout(() => {
				copied = false;
			}, 1700);
		} catch {
			// Clipboard indisponível: silencioso (paridade com o legado, que só
			// mostra o toast em sucesso).
		}
	}
</script>

<div class="flex flex-col gap-2 rounded-md border border-border-subtle bg-surface-muted px-3 py-2">
	<div class="flex items-center gap-2 text-sm text-text-secondary">
		<i class="fas fa-clock text-text-muted" aria-hidden="true"></i>
		<span>{meeting.time_summary}</span>
	</div>

	{#if meeting.owner_email}
		<div class="flex items-center gap-2 text-sm text-text-secondary">
			<i class="far fa-user text-text-muted" aria-hidden="true"></i>
			<span class="break-all">{meeting.owner_email}</span>
		</div>
	{/if}

	{#if meeting.location}
		<div class="flex items-center gap-2 text-sm text-text-secondary">
			<i class="fas fa-map-marker-alt text-text-muted" aria-hidden="true"></i>
			<span class="break-words">{meeting.location}</span>
		</div>
	{/if}

	{#if meeting.description}
		<p class="whitespace-pre-wrap break-words text-sm text-text-secondary">{meeting.description}</p>
	{/if}

	{#if hasSyncError}
		<p
			role="status"
			class="flex items-center gap-2 rounded-md border border-warning bg-surface px-2 py-1 text-sm text-warning"
		>
			<i class="fas fa-triangle-exclamation" aria-hidden="true"></i>
			{meeting.sync_error || 'Evento indisponível no Google Calendar.'}
		</p>
	{/if}

	<div class="flex flex-wrap items-center gap-2">
		{#if meeting.meet_link}
			<a
				href={meeting.meet_link}
				target="_blank"
				rel="noopener noreferrer"
				class="inline-flex items-center gap-1.5 rounded-md border-none bg-success px-2.5 py-1 text-sm font-medium text-success-fg no-underline transition-colors duration-fast ease-out hover:brightness-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-success"
			>
				<i class="fab fa-google" aria-hidden="true"></i>
				Abrir Meet
			</a>
			<button
				type="button"
				onclick={copyMeetLink}
				title={copied ? 'Link copiado!' : 'Copiar link do Meet'}
				aria-label={copied ? 'Link copiado' : 'Copiar link do Meet'}
				aria-live="polite"
				class="inline-flex h-[1.7rem] w-[1.7rem] items-center justify-center rounded-md border bg-surface text-text-muted transition-colors duration-fast ease-out hover:bg-surface-muted hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 {copied
					? 'border-success text-success'
					: 'border-border-subtle'}"
			>
				<i class="fas {copied ? 'fa-check' : 'fa-copy'}" aria-hidden="true"></i>
			</button>
		{/if}

		{#if meeting.can_manage}
			{#if meeting.can_edit}
				<button
					type="button"
					onclick={onEdit}
					disabled={busy}
					class="inline-flex items-center gap-1 rounded-md border border-border-subtle bg-surface px-2.5 py-1 text-sm font-medium text-text-primary transition-colors duration-fast ease-out hover:bg-surface-muted hover:text-primary-700 disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
				>
					<i class="fas fa-pen" aria-hidden="true"></i>
					Editar
				</button>
			{/if}
			<button
				type="button"
				onclick={onDelete}
				disabled={busy}
				class="inline-flex items-center gap-1 rounded-md border border-danger bg-surface px-2.5 py-1 text-sm font-medium text-danger transition-colors duration-fast ease-out hover:bg-danger hover:text-danger-fg disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-danger"
			>
				<i class="fas {busy ? 'fa-spinner fa-spin' : 'fa-trash'}" aria-hidden="true"></i>
				{busy ? 'Apagando…' : 'Apagar'}
			</button>
		{:else}
			<span class="inline-flex items-center gap-1 text-sm text-text-muted">
				<i class="fas fa-lock" aria-hidden="true"></i>
				Somente a mesma conta Google conectada pode editar ou apagar.
			</span>
		{/if}
	</div>
</div>
