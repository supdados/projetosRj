<script lang="ts">
	/**
	 * Cartão de coleção do índice (`/colecoes`): tile de ícone + nome + descrição
	 * + barra de progresso (% de etapas concluídas) + meta "N projetos · N etapas".
	 *
	 * O card inteiro é clicável por um link SOBREPOSTO (`absolute inset-0`), e não
	 * envolvendo o conteúdo num `<a>` — assim o kebab continua sendo um controle
	 * legítimo (interativo dentro de link é HTML inválido). Molde do sobreposto:
	 * `dashboard/+page.svelte:474-478`.
	 *
	 * Variante Favoritos (`tipo === 'favoritos'`): badge "Padrão" no lugar do
	 * kebab — coleção de sistema não é renomeável nem deletável.
	 *
	 * Fase 2 (compartilhamento): coleção MINHA e compartilhada ganha o chip
	 * "Compartilhada"; coleção que chegou por share mostra a procedência
	 * ("Compartilhada por Fulano · Leitura") e NÃO tem kebab — editar, apagar e
	 * gerir acessos são só do dono.
	 */
	import AppIcon from '$lib/components/AppIcon.svelte';
	import ColecaoIconTile from '$lib/components/ColecaoIconTile.svelte';
	import SelectMenu from '$lib/components/SelectMenu.svelte';
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

	const plural = (n: number, singular: string): string =>
		`${n} ${n === 1 ? singular : `${singular}s`}`;

	const meta = $derived(
		`${plural(colecao.projetos, 'projeto')} · ${plural(colecao.etapas_total, 'etapa')}`
	);

	const PAPEL_LABEL: Record<string, string> = { viewer: 'Leitura', editor: 'Edição' };

	// Procedência de coleção alheia; `owner` só vem preenchido quando papel ≠ dono.
	const procedencia = $derived(
		isDono || !colecao.owner
			? ''
			: `Compartilhada por ${colecao.owner.nome} · ${PAPEL_LABEL[colecao.papel] ?? 'Leitura'}`
	);

	const acoes = $derived.by<SelectMenuOption[]>(() => {
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

<article
	class="relative flex h-full flex-col gap-3 rounded-lg border border-border-subtle bg-surface p-4 shadow-sm transition-ui duration-slow focus-within:border-brand hover:border-brand hover:shadow-md"
>
	<a
		{href}
		aria-label={`Abrir coleção ${colecao.nome}: ${meta}, ${colecao.progresso_pct}% concluído`}
		class="absolute inset-0 z-10 rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
	></a>

	<div class="flex items-center gap-3">
		<ColecaoIconTile icone={colecao.icone} cor={colecao.cor} />
		<div class="flex min-w-0 flex-1 flex-col">
			<span class="min-w-0 truncate text-base font-bold text-text-primary" title={colecao.nome}>
				{colecao.nome}
			</span>
			{#if procedencia}
				<span class="min-w-0 truncate text-xs text-text-muted">{procedencia}</span>
			{/if}
		</div>
		{#if colecao.compartilhada && isDono}
			<span
				class="shrink-0 rounded-sm border border-border-subtle bg-wash-neutral px-2 py-0.5 text-2xs font-medium text-text-secondary"
			>
				Compartilhada
			</span>
		{/if}
		{#if isFavoritos}
			<span
				class="shrink-0 rounded-sm border border-border-subtle bg-wash-neutral px-2 py-0.5 text-2xs font-medium text-text-secondary"
			>
				Padrão
			</span>
		{:else if isDono && acoes.length > 0}
			<div class="relative z-20 w-8 shrink-0">
				<SelectMenu
					options={acoes}
					value={null}
					onSelect={executarAcao}
					unstyled
					hideCheck
					align="right"
					ariaLabel={`Ações da coleção ${colecao.nome}`}
				>
					{#snippet trigger()}
						<span
							class="flex h-8 w-8 items-center justify-center rounded-md text-text-muted transition-colors duration-fast hover:bg-surface-muted hover:text-text-primary"
						>
							<AppIcon id="kebab" />
						</span>
					{/snippet}
				</SelectMenu>
			</div>
		{/if}
	</div>

	{#if colecao.descricao}
		<p class="m-0 line-clamp-1 text-sm text-text-secondary">{colecao.descricao}</p>
	{/if}

	<div class="mt-auto">
		<!-- Barra decorativa: o % já é lido no texto abaixo e no label do link. -->
		<div class="h-1.5 w-full overflow-hidden rounded-full bg-progress-track" aria-hidden="true">
			<div
				class="h-full rounded-full bg-brand transition-[width] duration-300 ease-out"
				style:width={`${colecao.progresso_pct}%`}
			></div>
		</div>
		<div class="mt-2 flex items-center text-xs text-text-muted">
			<span class="truncate">{meta}</span>
			<span class="ml-auto shrink-0 font-mono text-text-secondary">{colecao.progresso_pct}%</span>
		</div>
	</div>
</article>
