<script lang="ts">
	/**
	 * Ponte entre `confirmAction()` e o `ConfirmDialog`. Montado UMA vez no
	 * layout autenticado, ao lado de `<FlashToasts />`.
	 */
	import { afterNavigate } from '$app/navigation';
	import ConfirmDialog from './ConfirmDialog.svelte';
	import { confirmRequest, dismissConfirmOnNavigation, resolveConfirm } from '$lib/stores/confirm';

	interface Flight {
		id: number;
		busy: boolean;
		error?: string;
	}

	// O voo carrega o id da solicitação: busy/erro de um pedido nunca vazam para
	// o seguinte, sem depender de efeito de limpeza.
	let flight = $state<Flight | null>(null);

	const request = $derived($confirmRequest);
	const current = $derived(request && flight?.id === request.id ? flight : null);
	const busy = $derived(current?.busy ?? false);
	const error = $derived(current?.error);

	async function runAndResolve(id: number, run: () => Promise<void>): Promise<void> {
		flight = { id, busy: true };
		try {
			await run();
			resolveConfirm(true, id);
		} catch (err) {
			const message =
				err instanceof Error && err.message ? err.message : 'Não foi possível concluir a ação.';
			flight = { id, busy: false, error: message };
		}
	}

	function handleConfirm(): void {
		if (!request || busy) return;
		if (!request.run) {
			resolveConfirm(true, request.id);
			return;
		}
		void runAndResolve(request.id, request.run);
	}

	function handleCancel(): void {
		if (!request) return;
		resolveConfirm(false, request.id);
	}

	// O host vive no layout: sem isto o diálogo sobrevive à navegação e confirmar
	// rodaria o `run` da página anterior.
	afterNavigate(() => dismissConfirmOnNavigation(busy));
</script>

{#if request}
	{#key request.id}
		<ConfirmDialog
			title={request.title}
			description={request.description}
			tone={request.tone ?? 'danger'}
			icon={request.icon}
			confirmLabel={request.confirmLabel}
			cancelLabel={request.cancelLabel}
			busyLabel={request.busyLabel}
			typeToConfirm={request.typeToConfirm}
			{busy}
			{error}
			onConfirm={handleConfirm}
			onCancel={handleCancel}
		/>
	{/key}
{/if}
