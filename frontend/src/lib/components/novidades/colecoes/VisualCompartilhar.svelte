<script lang="ts">
	/**
	 * Ilustração do passo 3 da novidade de Coleções: o sino com um convite, o
	 * cartão do convite (Recusar / Aceitar) e quem já respondeu. Nomes e
	 * coleção são EXEMPLOS. Decorativa: os "botões" são `span` (não focáveis).
	 */
	import ColecaoIconTile from '$lib/components/ColecaoIconTile.svelte';

	const PESSOAS: readonly {
		sigla: string;
		nome: string;
		area?: boolean;
		status: string;
		tom: 'ok' | 'pendente' | 'neutro';
	}[] = [
		{ sigla: 'BL', nome: 'Bruno Lima', status: 'Aceitou', tom: 'ok' },
		{ sigla: 'SUP', nome: 'SUPIM', area: true, status: '2 de 3 com acesso', tom: 'neutro' },
		{ sigla: 'CR', nome: 'Carla Reis', status: 'Pendente', tom: 'pendente' }
	];
	const TOM_STATUS = {
		ok: 'rounded-md bg-success-100 px-2 py-0.5 font-bold text-success-700',
		pendente: 'rounded-md bg-warning-100 px-2 py-0.5 font-bold text-warning-700',
		neutro: 'text-text-secondary'
	} as const;
</script>

<div class="flex w-[340px] flex-col gap-3.5" aria-hidden="true">
	<div
		class="flex items-center gap-2.5 self-end rounded-full border border-border-subtle bg-surface py-1.5 pl-2 pr-3.5 shadow-md"
	>
		<span class="relative grid h-[30px] w-[30px] place-items-center rounded-full bg-primary-700 text-white">
			<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" /><path d="M10 21h4" /></svg>
			<span
				class="absolute -right-1 -top-1 grid h-4 min-w-4 place-items-center rounded-full bg-attention-400 text-[10px] font-extrabold text-white ring-2 ring-surface"
				>1</span
			>
		</span>
		<span class="text-sm font-bold text-text-primary">1 convite pendente</span>
	</div>

	<div class="flex flex-col gap-3.5 rounded-xl border border-border-subtle bg-surface p-[18px] shadow-lg">
		<div class="flex items-center gap-3">
			<ColecaoIconTile icone="camadas" cor="primary" size={40} />
			<div class="min-w-0">
				<div class="text-md font-extrabold text-text-primary">Transformação Digital</div>
				<div class="mt-0.5 text-xs text-text-muted">Ana convidou você como Leitor</div>
			</div>
		</div>
		<div class="flex justify-end gap-2">
			<span
				class="inline-flex h-[34px] items-center rounded-md border border-primary-600 px-3.5 text-sm font-bold text-primary-600"
				>Recusar</span
			>
			<span class="inline-flex h-[34px] items-center rounded-md bg-primary-600 px-4 text-sm font-bold text-white"
				>Aceitar</span
			>
		</div>
	</div>

	<div class="rounded-lg bg-surface/80 px-3.5 py-1.5">
		{#each PESSOAS as pessoa, i (pessoa.nome)}
			<div class="flex items-center gap-2.5 py-2 text-sm {i > 0 ? 'border-t border-border-subtle' : ''}">
				<span
					class="grid h-[26px] w-[26px] place-items-center text-[10px] font-extrabold {pessoa.area
						? 'rounded-md border border-border-subtle bg-surface text-primary-700'
						: 'rounded-full bg-primary-600 text-white'}">{pessoa.sigla}</span
				>
				<span class="flex-1 font-semibold text-text-primary">{pessoa.nome}</span>
				<span class="text-2xs {TOM_STATUS[pessoa.tom]}">{pessoa.status}</span>
			</div>
		{/each}
	</div>
</div>
