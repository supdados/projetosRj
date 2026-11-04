<script lang="ts">
	/**
	 * Uma linha da lista "Compartilhada com" do CompartilharColecaoModal (só o
	 * dono a vê): avatar (iniciais da pessoa ou sigla da área), nome + detalhe,
	 * marcador de status do convite, "Reenviar" onde alguém recusou ou saiu,
	 * papel editável e revogação.
	 *
	 * Só apresenta: as mutações (e as confirmações) são do modal, que passa
	 * `ocupado` para travar a linha enquanto uma delas está no ar.
	 */
	import AppIcon from '$lib/components/AppIcon.svelte';
	import SelectMenu from '$lib/components/SelectMenu.svelte';
	import {
		PAPEIS_COMPARTILHAMENTO,
		detalheDoShareDeArea,
		marcadorDoShare,
		nomeDoShare,
		podeReenviarShare,
		type TomStatusShare
	} from '$lib/utils/colecaoShares';
	import { formatIsoDateBR } from '$lib/utils/dateFormat';
	import type { SelectMenuOption } from '$lib/types/selectMenu';
	import type { ColecaoShare, PapelCompartilhamento } from '$lib/types/collections';

	interface Props {
		share: ColecaoShare;
		/** Mutação desta linha no ar: controles travados e linha esmaecida. */
		ocupado: boolean;
		onTrocarPapel: (share: ColecaoShare, papel: PapelCompartilhamento) => void;
		onReenviar: (share: ColecaoShare) => void;
		onRevogar: (share: ColecaoShare) => void;
	}

	let { share, ocupado, onTrocarPapel, onReenviar, onRevogar }: Props = $props();

	const PAPEL_MENU: SelectMenuOption[] = PAPEIS_COMPARTILHAMENTO.map((o) => ({
		value: o.id,
		label: o.label
	}));

	// Mapa ESTÁTICO: classe montada em runtime não compila.
	const TOM_CLASS: Record<TomStatusShare, string> = {
		warning: 'border-warning-soft bg-wash-warning text-warning',
		success: 'border-success-soft bg-wash-success text-success',
		danger: 'border-danger-soft bg-wash-danger text-danger',
		neutral: 'border-border-subtle bg-wash-neutral text-text-secondary'
	};

	const nome = $derived(nomeDoShare(share));
	const marcador = $derived(marcadorDoShare(share));
	const reenviavel = $derived(podeReenviarShare(share));

	const meta = $derived.by(() => {
		if (share.user) {
			const desde = formatIsoDateBR(share.created_at);
			return desde ? `Pessoa · desde ${desde}` : 'Pessoa';
		}
		// Contagem antes do nome: o truncate corta o nome do órgão, nunca os números.
		const area = share.orgao?.nome ?? 'Área';
		return share.resumo ? `${detalheDoShareDeArea(share.resumo)} · ${area}` : area;
	});

	function iniciais(texto: string): string {
		const partes = texto.trim().split(/\s+/).filter(Boolean);
		if (partes.length === 0) return '?';
		const primeira = partes[0][0] ?? '';
		const segunda = partes.length > 1 ? (partes[partes.length - 1][0] ?? '') : (partes[0][1] ?? '');
		return (primeira + segunda).toUpperCase();
	}

	function escolherPapel(valor: string | null): void {
		const novo: PapelCompartilhamento = valor === 'editor' ? 'editor' : 'viewer';
		if (novo !== share.papel) onTrocarPapel(share, novo);
	}
</script>

<li
	class="flex items-center gap-3 border-b border-border-hairline py-2 transition-opacity duration-fast last:border-b-0 {ocupado
		? 'opacity-60'
		: ''}"
>
	<span
		class="grid h-8 w-8 shrink-0 place-items-center bg-wash-neutral text-2xs font-bold text-brand {share.user
			? 'rounded-full'
			: 'rounded-md'}"
		aria-hidden="true"
	>
		{share.user ? iniciais(share.user.nome) : (share.orgao?.sigla ?? '').slice(0, 3)}
	</span>

	<div class="flex min-w-0 flex-1 flex-col">
		<span class="truncate text-sm font-medium text-text-primary">{nome}</span>
		<span class="truncate text-xs text-text-muted" title={meta}>{meta}</span>
	</div>

	{#if marcador || reenviavel}
		<div class="flex shrink-0 items-center gap-2">
			{#if marcador}
				<span class="rounded-sm border px-1.5 py-0.5 text-2xs font-medium {TOM_CLASS[marcador.tom]}">
					{marcador.rotulo}
				</span>
			{/if}
			{#if reenviavel}
				<button
					type="button"
					onclick={() => onReenviar(share)}
					disabled={ocupado}
					aria-label={`Reenviar o convite para ${nome}`}
					class="rounded-sm text-xs font-semibold text-brand transition-colors duration-fast hover:underline disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
				>
					Reenviar
				</button>
			{/if}
		</div>
	{/if}

	<div class="shrink-0">
		<SelectMenu
			options={PAPEL_MENU}
			value={share.papel}
			onSelect={escolherPapel}
			disabled={ocupado}
			unstyled
			hideCheck
			align="right"
			ariaLabel={`Papel de ${nome}`}
		>
			{#snippet trigger({ open, label })}
				<span
					class="flex items-center gap-1.5 rounded-md border border-transparent px-2 py-1 text-sm font-semibold text-text-primary transition-colors duration-fast hover:border-border-subtle hover:bg-surface-muted"
				>
					{label}
					<svg
						viewBox="0 0 20 20"
						class="h-2.5 w-2.5 text-text-muted transition-transform duration-fast"
						fill="none"
						stroke="currentColor"
						stroke-width="2"
						style:transform={open ? 'rotate(180deg)' : 'none'}
						aria-hidden="true"
					>
						<path d="m4 7 6 6 6-6" stroke-linecap="round" stroke-linejoin="round" />
					</svg>
				</span>
			{/snippet}
		</SelectMenu>
	</div>

	<button
		type="button"
		onclick={() => onRevogar(share)}
		disabled={ocupado}
		aria-label={`Revogar o compartilhamento com ${nome}`}
		class="grid h-8 w-8 shrink-0 place-items-center rounded-md text-text-muted transition-colors duration-fast hover:bg-wash-danger hover:text-danger disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
	>
		<AppIcon id="exclusao" />
	</button>
</li>
