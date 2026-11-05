<script lang="ts">
	/**
	 * Modal "Adicionar projetos" da página interna, no conceito de CAPA
	 * (design "Coleções 3a"): o topo é a faixa da coleção — ícone, nome e
	 * "N projetos · +M selecionados" — e a pílula mostra as áreas que a coleção
	 * TERÁ (as atuais somadas às dos projetos marcados), ao vivo. Embaixo, o
	 * ColecaoProjectPicker; o POST é idempotente por projeto, em sequência.
	 *
	 * O picker só lista o que o backend ACEITA incluir (`visibilidade`), para o
	 * lote não falhar no meio: o editor vê só os projetos da própria área
	 * (`area` — projeto visto só por convite é recusado), o dono vê área e
	 * convite sem a visibilidade derivada de coleção (`propria`). Favoritos
	 * aceita a derivada (nunca é compartilhada): sem filtro.
	 */
	import { SvelteMap } from 'svelte/reactivity';
	import Modal from '$lib/components/Modal.svelte';
	import Button from '$lib/components/Button.svelte';
	import StateBanner from '$lib/components/StateBanner.svelte';
	import ColecaoAreasPill from '$lib/components/ColecaoAreasPill.svelte';
	import ColecaoIconeSvg from '$lib/components/ColecaoIconeSvg.svelte';
	import ColecaoProjectPicker from '$lib/components/ColecaoProjectPicker.svelte';
	import { adicionarProjeto } from '$lib/api/collections';
	import { ApiClientError } from '$lib/api/client';
	import { tomDaCapa } from '$lib/icons/collectionIdentity';
	import { flash } from '$lib/stores/flash';
	import { areasDasSiglas, plural, somarAreas } from '$lib/utils/colecaoCapa';
	import type { Project } from '$lib/types/entities';
	import type { ColecaoResumo } from '$lib/types/collections';
	import type { ProjectsVisibilidadePicker } from '$lib/types/projects';

	interface Props {
		/** Coleção de destino: identidade da capa e áreas atuais. */
		colecao: ColecaoResumo;
		/** Já na coleção: some da lista na hora (o servidor também exclui). */
		idsNaColecao: number[];
		/** Ausente = sem estreitar (Favoritos). */
		visibilidade?: ProjectsVisibilidadePicker;
		onClose: () => void;
		/** Houve inclusão (lote inteiro ou parcial) — a página re-busca. */
		onAdicionados: () => void;
	}

	let { colecao, idsNaColecao, visibilidade, onClose, onAdicionados }: Props = $props();

	const TITULO_ID = 'colecao-add-projetos-title';

	let selecionados = $state<number[]>([]);
	let totalDisponivel = $state<number | null>(null);
	let adding = $state(false);
	let erro = $state<string | null>(null);

	const tom = $derived(tomDaCapa(colecao.cor));
	// Sigla de cada projeto já visto no picker: alimenta a pílula ao vivo.
	const siglaPorProjeto = new SvelteMap<number, string | null>();
	const areasPrevistas = $derived(
		somarAreas(
			colecao.areas ?? [],
			areasDasSiglas(
				selecionados
					.filter((id) => siglaPorProjeto.has(id))
					.map((id) => siglaPorProjeto.get(id) ?? null)
			)
		)
	);
	const meta = $derived(
		selecionados.length > 0
			? `${plural(colecao.projetos, 'projeto')} · +${plural(selecionados.length, 'selecionado')}`
			: `${plural(colecao.projetos, 'projeto')} na coleção`
	);
	const rotuloLista = $derived(visibilidade ? 'Projetos da sua área' : 'Projetos que você vê');

	function guardarSiglas(projetos: Project[]): void {
		for (const projeto of projetos) siglaPorProjeto.set(projeto.id, projeto.orgao_sigla);
	}

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
				await adicionarProjeto(colecao.id, projectId);
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

<Modal labelId={TITULO_ID} flush maxWidth="max-w-[720px]" onBackdrop={fechar}>
	<div class="flex max-h-[calc(100dvh-2rem)] flex-col">
		<div class="relative overflow-hidden px-5 pb-6 pt-6 sm:px-7 {tom.wash}">
			<ColecaoIconeSvg
				icone={colecao.icone}
				size={130}
				class="pointer-events-none absolute -bottom-9 right-6 opacity-[.13] sm:right-[100px] {tom.tinta}"
			/>
			<div
				class="relative z-[1] -mt-1 mb-2 flex items-center justify-end gap-2 sm:absolute sm:right-6 sm:top-6 sm:m-0"
			>
				{#if areasPrevistas.length > 0}
					<ColecaoAreasPill areas={areasPrevistas} cor={colecao.cor} />
				{/if}
				<button
					type="button"
					onclick={fechar}
					disabled={adding}
					aria-label="Fechar"
					class="bg-capa-veu grid h-8 w-8 place-items-center rounded-full text-text-secondary transition-colors duration-fast hover:text-text-primary disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
				>
					<svg viewBox="0 0 20 20" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
						<path d="m5 5 10 10M15 5 5 15" stroke-linecap="round" />
					</svg>
				</button>
			</div>
			<div class="relative flex max-w-[480px] items-center gap-3">
				<ColecaoIconeSvg icone={colecao.icone} size={30} class="shrink-0 {tom.tinta}" />
				<div class="flex min-w-0 flex-col gap-0.5">
					<h2 id={TITULO_ID} class="m-0 font-heading text-xl font-bold leading-tight text-text-primary">
						Adicionar projetos
					</h2>
					<p class="m-0 truncate text-sm text-text-secondary">
						<span class="font-semibold text-text-primary">{colecao.nome}</span> · {meta}
					</p>
				</div>
			</div>
		</div>

		<div class="flex min-h-0 flex-1 flex-col gap-2.5 px-5 py-5 sm:px-7">
			<div class="flex items-baseline justify-between gap-3">
				<span class="text-sm font-semibold text-text-secondary">{rotuloLista}</span>
				<span class="shrink-0 text-xs text-text-muted">
					{selecionados.length}{totalDisponivel !== null ? ` de ${totalDisponivel}` : ''}
					{#if selecionados.length > 0}
						·
						<button
							type="button"
							onclick={() => (selecionados = [])}
							class="font-semibold text-brand hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
						>
							Limpar
						</button>
					{/if}
				</span>
			</div>
			<!-- Altura definida: o picker com `preencher` cresce até ela e rola por dentro. -->
			<div class="flex min-h-0 flex-col md:h-[min(26rem,55dvh)]">
				<ColecaoProjectPicker
					{selecionados}
					colecaoId={colecao.id}
					exclude={idsNaColecao}
					{visibilidade}
					preencher
					onchange={(ids) => (selecionados = ids)}
					ontotal={(total) => (totalDisponivel = total)}
					onprojetosCarregados={guardarSiglas}
				/>
			</div>
			{#if erro}
				<StateBanner tone="danger" title={erro} />
			{/if}
		</div>

		<footer
			class="flex items-center justify-end gap-2.5 border-t border-border-subtle px-5 py-4 sm:px-7"
		>
			<Button variant="secondary" onclick={fechar} disabled={adding}>Cancelar</Button>
			<Button
				onclick={() => void adicionarSelecionados()}
				disabled={adding || selecionados.length === 0}
			>
				{adding
					? 'Adicionando…'
					: selecionados.length === 0
						? 'Adicionar projetos'
						: selecionados.length === 1
							? 'Adicionar 1 projeto'
							: `Adicionar ${selecionados.length} projetos`}
			</Button>
		</footer>
	</div>
</Modal>
