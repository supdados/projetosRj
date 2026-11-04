<script lang="ts">
	/**
	 * Modal "Editar coleção" do índice: nome, descrição, ícone e cor — o mesmo
	 * formulário do lado esquerdo do NovaColecaoModal. Extraído de
	 * `routes/(app)/colecoes/+page.svelte` (a página passava de 600 linhas).
	 *
	 * Só o dono abre (a página decide); Favoritos nunca chega aqui (422 no
	 * backend). O PUT invalida os caches de coleção no client de API; quem
	 * chama só re-busca em `onSalva`.
	 */
	import { onMount, tick, untrack } from 'svelte';
	import Modal from '$lib/components/Modal.svelte';
	import Button from '$lib/components/Button.svelte';
	import StateBanner from '$lib/components/StateBanner.svelte';
	import ColecaoIconTile from '$lib/components/ColecaoIconTile.svelte';
	import { editarColecao } from '$lib/api/collections';
	import { ApiClientError } from '$lib/api/client';
	import { COLLECTION_ICONS } from '$lib/icons/collectionIcons';
	import {
		COLECAO_COR_OPTIONS,
		COLECAO_ICONE_ATIVO_CLASS,
		COLECAO_ICONE_OPTIONS
	} from '$lib/icons/collectionIdentity';
	import type {
		ColecaoResumo,
		CollectionColorId,
		CollectionIconId
	} from '$lib/types/collections';

	interface Props {
		/** Coleção a editar (valores iniciais do formulário). */
		colecao: ColecaoResumo;
		/** Fecha sem salvar (✕, Esc, backdrop, Cancelar). */
		onClose: () => void;
		/** Salvou; o modal já pode sair (quem chama fecha e re-busca). */
		onSalva: (atualizada: ColecaoResumo) => void;
	}

	let { colecao, onClose, onSalva }: Props = $props();

	const DESCRICAO_MAX = 200;

	// Valores iniciais copiados na montagem: o formulário não pode reagir ao card de fora.
	const inicial = untrack(() => colecao);
	let editNome = $state(inicial.nome);
	let editDescricao = $state(inicial.descricao ?? '');
	let editIcone = $state<CollectionIconId>(inicial.icone);
	let editCor = $state<CollectionColorId>(inicial.cor);
	let editTriedSave = $state(false);
	let editSaving = $state(false);
	let editErro = $state<string | null>(null);
	let editNomeInputEl = $state<HTMLInputElement | null>(null);

	const editNomeInvalido = $derived(editTriedSave && !editNome.trim());

	onMount(() => {
		void tick().then(() => editNomeInputEl?.focus());
	});

	function fecharEdicao(): void {
		if (editSaving) return;
		onClose();
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
			const atualizada = await editarColecao(inicial.id, {
				nome: editNome.trim(),
				descricao: editDescricao.trim() || null,
				icone: editIcone,
				cor: editCor
			});
			editSaving = false;
			onSalva(atualizada);
		} catch (err) {
			editSaving = false;
			editErro =
				err instanceof ApiClientError ? err.message : 'Não foi possível salvar a coleção.';
		}
	}

	const labelCls = 'text-xs font-medium text-text-secondary';
	const fieldCls =
		'h-[var(--control-h-md)] w-full rounded-control border bg-surface px-3.5 text-md text-text-primary placeholder:text-text-faint transition-colors duration-fast focus:outline-none';
</script>

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
				{#each COLECAO_ICONE_OPTIONS as opcao (opcao.id)}
					{@const ativo = editIcone === opcao.id}
					<button
						type="button"
						aria-pressed={ativo}
						aria-label={opcao.label}
						onclick={() => (editIcone = opcao.id)}
						class="grid aspect-square place-items-center rounded-md border transition-colors duration-fast focus:outline-none focus-visible:ring-2 focus-visible:ring-brand {ativo
							? COLECAO_ICONE_ATIVO_CLASS[editCor]
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
				{#each COLECAO_COR_OPTIONS as opcao (opcao.id)}
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
