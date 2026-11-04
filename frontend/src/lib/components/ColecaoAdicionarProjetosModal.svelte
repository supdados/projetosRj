<script lang="ts">
	/**
	 * Modal "Adicionar projetos" da página interna: ColecaoProjectPicker + POST
	 * idempotente por projeto, em sequência. Extraído de
	 * `routes/(app)/colecoes/[id]/+page.svelte` (passava de 1000 linhas).
	 *
	 * O picker só lista o que o backend ACEITA incluir (`visibilidade`), para o
	 * lote não falhar no meio: o editor vê só os projetos da própria área
	 * (`area` — projeto visto só por convite é recusado), o dono vê área e
	 * convite sem a visibilidade derivada de coleção (`propria`). Favoritos
	 * aceita a derivada (nunca é compartilhada): sem filtro.
	 */
	import Modal from '$lib/components/Modal.svelte';
	import Button from '$lib/components/Button.svelte';
	import StateBanner from '$lib/components/StateBanner.svelte';
	import ColecaoProjectPicker from '$lib/components/ColecaoProjectPicker.svelte';
	import { adicionarProjeto } from '$lib/api/collections';
	import { ApiClientError } from '$lib/api/client';
	import { flash } from '$lib/stores/flash';
	import type { ProjectsVisibilidadePicker } from '$lib/types/projects';

	interface Props {
		collectionId: number;
		/** Já na coleção: some da lista na hora (o servidor também exclui). */
		idsNaColecao: number[];
		/** Ausente = sem estreitar (Favoritos). */
		visibilidade?: ProjectsVisibilidadePicker;
		onClose: () => void;
		/** Houve inclusão (lote inteiro ou parcial) — a página re-busca. */
		onAdicionados: () => void;
	}

	let { collectionId, idsNaColecao, visibilidade, onClose, onAdicionados }: Props = $props();

	let selecionados = $state<number[]>([]);
	let adding = $state(false);
	let erro = $state<string | null>(null);

	function fechar(): void {
		if (adding) return;
		onClose();
	}

	async function adicionarSelecionados(): Promise<void> {
		if (adding || selecionados.length === 0) return;
		adding = true;
		erro = null;
		const total = selecionados.length;
		let adicionados = 0;
		try {
			// Sequencial: POST idempotente por projeto (repetir um id é no-op).
			for (const projectId of selecionados) {
				await adicionarProjeto(collectionId, projectId);
				adicionados += 1;
			}
			adding = false;
			flash.success(
				total === 1 ? '1 projeto adicionado à coleção.' : `${total} projetos adicionados à coleção.`
			);
			onAdicionados();
			onClose();
		} catch (err) {
			adding = false;
			const motivo =
				err instanceof ApiClientError ? err.message : 'Não foi possível adicionar os projetos.';
			erro =
				adicionados > 0 ? `${motivo} ${adicionados} de ${total} projetos foram adicionados.` : motivo;
			// Falha no meio do lote: sem resync a tabela e os KPIs mentem até o F5.
			if (adicionados > 0) onAdicionados();
		}
	}
</script>

<Modal labelId="colecao-add-projetos-title" maxWidth="max-w-[540px]" onBackdrop={fechar}>
	<div class="flex max-h-[80vh] flex-col gap-4">
		<div class="flex items-center gap-3">
			<h2 id="colecao-add-projetos-title" class="font-heading text-xl font-bold text-text-primary">
				Adicionar projetos
			</h2>
			<button
				type="button"
				onclick={fechar}
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
				{selecionados}
				colecaoId={collectionId}
				exclude={idsNaColecao}
				{visibilidade}
				onchange={(ids) => (selecionados = ids)}
			/>
			{#if erro}
				<StateBanner tone="danger" title={erro} />
			{/if}
		</div>

		<footer class="flex justify-end gap-2 border-t border-border-hairline pt-4">
			<Button variant="secondary" onclick={fechar} disabled={adding}>Cancelar</Button>
			<Button
				onclick={() => void adicionarSelecionados()}
				disabled={adding || selecionados.length === 0}
			>
				{adding
					? 'Adicionando…'
					: selecionados.length === 1
						? 'Adicionar 1 projeto'
						: `Adicionar ${selecionados.length} projetos`}
			</Button>
		</footer>
	</div>
</Modal>
