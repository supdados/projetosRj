<script lang="ts">
	/**
	 * Cartão de coleção do índice (`/colecoes`) no formato CAPA (design
	 * "Coleções 2b"): a capa leva o ícone, o nome e "N projetos"; embaixo ficam
	 * a barra das etapas por situação e os três números. A pílula "N áreas"
	 * abre, no hover/foco, quantos projetos vêm de cada área.
	 *
	 * O card inteiro é clicável por um link SOBREPOSTO (`absolute inset-0`), e não
	 * envolvendo o conteúdo num `<a>` — assim o kebab e a pílula continuam sendo
	 * controles legítimos (interativo dentro de link é HTML inválido). Molde do
	 * sobreposto: `dashboard/+page.svelte:474-478`.
	 *
	 * Variante Favoritos (`tipo === 'favoritos'`): badge "Padrão" no lugar do
	 * kebab — coleção de sistema não é renomeável nem deletável — e, vazia, a
	 * dica de usar a estrela no lugar dos números, sob a mesma barra (vazia) dos
	 * outros cards: a anatomia barra + linha de texto se repete em todo card,
	 * então a linha do grid fica alinhada (e sem o "0 projetos" na capa).
	 *
	 * Compartilhamento: coleção que chegou por share mostra a procedência
	 * ("Compartilhada por Fulano · Leitura") no rodapé, com `mt-auto` para as
	 * barras seguirem alinhadas na linha do grid, e NÃO tem kebab — editar,
	 * apagar e gerir acessos são só do dono. Com quem está compartilhada fica
	 * no modal Compartilhar, não no card.
	 */
	import AppIcon from '$lib/components/AppIcon.svelte';
	import ColecaoAndamento from '$lib/components/ColecaoAndamento.svelte';
	import ColecaoAreasPill from '$lib/components/ColecaoAreasPill.svelte';
	import ColecaoCapa from '$lib/components/ColecaoCapa.svelte';
	import SelectMenu from '$lib/components/SelectMenu.svelte';
	import { plural } from '$lib/utils/colecaoCapa';
	import type { SelectMenuOption } from '$lib/types/selectMenu';
	import type { ColecaoResumo } from '$lib/types/collections';

	interface Props {
		colecao: ColecaoResumo;
		/** Destino do card inteiro (ex.: `${base}/colecoes/12`). */
		href: string;
		/** Abre o modal de edição; ausente esconde o item do menu. */
		onEditar?: () => void;
		/** Abre o modal de compartilhamento; ausente esconde o item do menu. */
		onCompartilhar?: () => void;
		/** Pede confirmação e apaga; ausente esconde o item do menu. */
		onApagar?: () => void;
	}

	let { colecao, href, onEditar, onCompartilhar, onApagar }: Props = $props();

	const isFavoritos = $derived(colecao.tipo === 'favoritos');
	const isDono = $derived(colecao.papel === 'dono');
	const projetosLabel = $derived(plural(colecao.projetos, 'projeto'));
	const linkLabel = $derived(
		`Abrir coleção ${colecao.nome}: ${projetosLabel}, ${plural(colecao.etapas_total, 'etapa')}, ${colecao.progresso_pct}% concluído`
	);

	const PAPEL_LABEL: Record<string, string> = { viewer: 'Leitura', editor: 'Edição' };

	// `?? []`: payload antigo em cache SWR (pré-capa) não quebra o card.
	const areas = $derived(colecao.areas ?? []);

	// Procedência de coleção alheia; `owner` só vem preenchido quando papel ≠ dono.
	const procedencia = $derived(
		isDono || !colecao.owner
			? ''
			: `Compartilhada por ${colecao.owner.nome} · ${PAPEL_LABEL[colecao.papel] ?? 'Leitura'}`
	);

	const acoesMenu = $derived.by<SelectMenuOption[]>(() => {
		const out: SelectMenuOption[] = [];
		if (onEditar) out.push({ value: 'editar', label: 'Editar' });
		if (onCompartilhar) out.push({ value: 'compartilhar', label: 'Compartilhar' });
		if (onApagar) out.push({ value: 'apagar', label: 'Apagar' });
		return out;
	});

	function executarAcao(acao: string | null): void {
		if (acao === 'editar') onEditar?.();
		if (acao === 'compartilhar') onCompartilhar?.();
		if (acao === 'apagar') onApagar?.();
	}
</script>

<!-- Sem `h-full`: num item de grid o 100% resolve contra a LINHA inteira e o
     card esticava até o painel do estado vazio mesmo com `items-start`. A
     altura igual entre cards vem do `align-items: stretch` do grid. -->
<article
	class="relative flex flex-col rounded-xl border border-border-subtle bg-surface shadow-sm transition-ui duration-slow focus-within:border-brand hover:border-brand hover:shadow-md"
>
	<a
		{href}
		aria-label={linkLabel}
		class="absolute inset-0 z-10 rounded-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
	></a>

	<ColecaoCapa
		icone={colecao.icone}
		cor={colecao.cor}
		nome={colecao.nome}
		meta={isFavoritos && colecao.projetos === 0 ? undefined : projetosLabel}
		class="rounded-t-[15px]"
	>
		{#snippet acoes()}
			{#if areas.length > 0}
				<ColecaoAreasPill {areas} cor={colecao.cor} detalhe />
			{/if}
			{#if isFavoritos}
				<span
					class="bg-capa-veu inline-flex h-6 items-center rounded-full px-2.5 text-2xs font-semibold text-text-secondary"
				>
					Padrão
				</span>
			{:else if isDono && acoesMenu.length > 0}
				<div class="w-7 shrink-0">
					<SelectMenu
						options={acoesMenu}
						value={null}
						onSelect={executarAcao}
						unstyled
						hideCheck
						align="right"
						ariaLabel={`Ações da coleção ${colecao.nome}`}
					>
						{#snippet trigger()}
							<span
								class="bg-capa-veu flex h-7 w-7 items-center justify-center rounded-full text-text-secondary transition-colors duration-fast hover:text-text-primary"
							>
								<AppIcon id="kebab" size={16} />
							</span>
						{/snippet}
					</SelectMenu>
				</div>
			{/if}
		{/snippet}
	</ColecaoCapa>

	<div class="flex flex-1 flex-col gap-3 px-4 pb-4 pt-3.5">
		{#if isFavoritos && colecao.projetos === 0}
			<!-- Mesma anatomia do ColecaoAndamento (barra de 6px + gap-2.5 + texto),
			     com a trilha vazia: o texto cai onde os números caem nos vizinhos. -->
			<div class="flex flex-col gap-2.5">
				<div class="h-1.5 rounded-full bg-progress-track" aria-hidden="true"></div>
				<p class="m-0 text-xs leading-snug text-text-muted">
					Use a estrela nos projetos para guardá-los aqui.
				</p>
			</div>
		{:else}
			<ColecaoAndamento etapas={colecao} />
		{/if}

		{#if procedencia}
			<div class="mt-auto border-t border-border-hairline pt-3">
				<span class="block min-w-0 truncate text-xs text-text-muted">{procedencia}</span>
			</div>
		{/if}
	</div>
</article>
