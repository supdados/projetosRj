<script lang="ts">
	/**
	 * Modal "Editar coleção" do índice, no mesmo conceito de CAPA do Nova
	 * coleção (design "Coleções 3a"): o topo é a capa da coleção com nome e
	 * descrição editáveis (`ColecaoCapaEditavel`, já com a pílula das áreas
	 * atuais) e, embaixo, o bloco "Aparência" — cor e ícone repintam a capa na
	 * hora. Projetos e quem enxerga não mudam aqui (página interna e
	 * CompartilharColecaoModal).
	 *
	 * Só o dono abre (a página decide); Favoritos nunca chega aqui (422 no
	 * backend). O PUT invalida os caches de coleção no client de API; quem
	 * chama só re-busca em `onSalva`.
	 */
	import { onMount, tick, untrack } from 'svelte';
	import Modal from '$lib/components/Modal.svelte';
	import Button from '$lib/components/Button.svelte';
	import StateBanner from '$lib/components/StateBanner.svelte';
	import ColecaoAparencia from '$lib/components/ColecaoAparencia.svelte';
	import ColecaoCapaEditavel from '$lib/components/ColecaoCapaEditavel.svelte';
	import { editarColecao } from '$lib/api/collections';
	import { ApiClientError } from '$lib/api/client';
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

	const TITULO_ID = 'editar-colecao-title';
	// Espelham o backend (`NOME_MAX_COLECAO`, `_validar_descricao`).
	const NOME_MAX = 100;
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
	const semMudanca = $derived(
		editNome.trim() === inicial.nome &&
			editDescricao.trim() === (inicial.descricao ?? '') &&
			editIcone === inicial.icone &&
			editCor === inicial.cor
	);

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
		// Nada mudou: fechar é a resposta honesta, sem PUT nem recibo de "atualizada".
		if (semMudanca) {
			onClose();
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
</script>

<Modal labelId={TITULO_ID} flush maxWidth="max-w-[560px]" onBackdrop={fecharEdicao}>
	<form
		class="flex max-h-[calc(100dvh-2rem)] flex-col"
		onsubmit={(e) => {
			e.preventDefault();
			void salvarEdicao();
		}}
	>
		<ColecaoCapaEditavel
			titleId={TITULO_ID}
			titulo="Editar coleção"
			icone={editIcone}
			cor={editCor}
			bind:nome={editNome}
			bind:descricao={editDescricao}
			bind:nomeInputEl={editNomeInputEl}
			areas={inicial.areas ?? []}
			nomeInvalido={editNomeInvalido}
			nomeMax={NOME_MAX}
			descricaoMax={DESCRICAO_MAX}
			fecharDesabilitado={editSaving}
			onFechar={fecharEdicao}
		/>

		<div class="thin-scroll min-h-0 flex-1 overflow-y-auto px-5 py-6 sm:px-7">
			<ColecaoAparencia bind:icone={editIcone} bind:cor={editCor} idPrefix="ec" />
		</div>

		{#if editErro}
			<div class="px-5 pb-3 sm:px-7">
				<StateBanner tone="danger" title={editErro} />
			</div>
		{/if}

		<footer
			class="flex items-center justify-end gap-2.5 border-t border-border-subtle px-5 py-4 sm:px-7"
		>
			<Button variant="secondary" onclick={fecharEdicao} disabled={editSaving}>Cancelar</Button>
			<!-- Esmaecido sem nome ou sem mudança, mas clicável (mesma regra do Nova coleção).
			     Opacidade no wrapper — `class` no Button troca as classes dele. -->
			<div
				class="transition-opacity duration-slow {editNome.trim() && !semMudanca ? '' : 'opacity-50'}"
			>
				<Button type="submit" disabled={editSaving}>
					{editSaving ? 'Salvando…' : 'Salvar alterações'}
				</Button>
			</div>
		</footer>
	</form>
</Modal>
