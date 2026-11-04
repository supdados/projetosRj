<script lang="ts">
	/**
	 * Estado "convite pendente" da página `/colecoes/<id>`: quando
	 * `.../projetos` responde 404 mas existe convite para mim
	 * (`GET .../convite`). Mesmo header-card da coleção (tile + nome, segunda
	 * linha embutida de 58px) e, abaixo, o convite com Recusar/Aceitar.
	 *
	 * Só metadados: nenhum projeto, contagem, KPI ou cronograma antes do aceite
	 * — o backend nem os entrega. Quem decide o que acontece depois (recarregar
	 * a coleção, voltar ao índice) é a página, via `onRespondido`.
	 */
	import PageHeader from '$lib/components/PageHeader.svelte';
	import ColecaoIconTile from '$lib/components/ColecaoIconTile.svelte';
	import ColecaoConviteBotoes from '$lib/components/ColecaoConviteBotoes.svelte';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import { permissaoDoConvite, procedenciaDoConvite } from '$lib/utils/colecaoShares';
	import { formatIsoDateBRLocalTz } from '$lib/utils/dateFormat';
	import type { DesfechoConvite } from '$lib/utils/conviteColecao';
	import type { ConviteColecao } from '$lib/types/collections';

	interface Props {
		convite: ConviteColecao;
		onRespondido: (desfecho: DesfechoConvite) => void;
	}

	let { convite, onRespondido }: Props = $props();

	const data = $derived(formatIsoDateBRLocalTz(convite.convidado_em));
	const permissao = $derived(permissaoDoConvite(convite.papel));
</script>

<div class="rounded-xl border border-border-subtle bg-surface shadow-sm">
	<PageHeader compact embedded class="min-h-[3.5rem]" labelId="colecao-title">
		{#snippet titleContent()}
			<span class="inline-flex max-w-full items-center gap-2 align-middle">
				<ColecaoIconTile icone={convite.icone} cor={convite.cor} size={32} />
				<span class="min-w-0 truncate">{convite.nome}</span>
				<span
					class="shrink-0 rounded-sm border border-brand-soft bg-wash-brand px-2 py-0.5 text-2xs font-medium text-brand"
				>
					Convite
				</span>
			</span>
		{/snippet}
	</PageHeader>
	<div
		class="flex min-h-[calc(var(--control-h-md)+1.25rem)] flex-wrap items-center gap-x-3 gap-y-1 border-t border-border-subtle px-4 py-2.5 text-sm text-text-secondary"
	>
		{#if convite.descricao}
			<span class="min-w-0 truncate">{convite.descricao}</span>
		{/if}
		{#if data}
			<span class="ml-auto shrink-0 text-xs text-text-muted">Convite recebido em {data}</span>
		{/if}
	</div>
</div>

<div
	class="rounded-lg border border-border-subtle bg-surface px-4 py-10 text-center shadow-sm"
	role="region"
	aria-label="Convite pendente"
>
	<div
		class="mx-auto mb-3 inline-flex h-14 w-14 items-center justify-center rounded-xl border border-brand-soft bg-wash-neutral text-brand"
	>
		<AppIcon id="convite" size={28} />
	</div>
	<h2 class="m-0 font-heading text-xl font-bold text-text-primary">
		{procedenciaDoConvite(convite)}
	</h2>
	<p class="mx-auto mb-4 mt-1.5 max-w-xl text-sm text-text-muted">
		{permissao} Os projetos aparecem depois do aceite.
	</p>
	<div class="flex justify-center">
		<ColecaoConviteBotoes {convite} size="md" {onRespondido} />
	</div>
</div>
