<script lang="ts">
	/**
	 * Ilustração do passo 4 da novidade de Coleções: a lista de projetos vista
	 * por um editor — cada item com "Incluído por …" e a lixeira só no que ele
	 * incluiu. Projetos e nomes são EXEMPLOS. Decorativa.
	 */
	const ITENS: readonly { nome: string; incluidoPor: string; meu: boolean }[] = [
		{ nome: 'Painel de indicadores EEGD', incluidoPor: 'você', meu: true },
		{ nome: 'Monitor de atendimento', incluidoPor: 'Ana', meu: false },
		{ nome: 'Painel orçamentário', incluidoPor: 'você', meu: true }
	];
</script>

<div
	class="w-[350px] overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-lg"
	aria-hidden="true"
>
	<div class="flex items-center justify-between border-b border-border-subtle px-4 py-3.5">
		<span class="text-sm font-extrabold text-text-primary">Painéis de Gestão</span>
		<span class="rounded-md bg-primary-100 px-2 py-0.5 text-2xs font-bold text-primary-700">Você é editor</span>
	</div>
	{#each ITENS as item, i (item.nome)}
		<div class="flex items-center gap-2.5 px-4 py-3 {i > 0 ? 'border-t border-border-subtle' : ''}">
			<div class="min-w-0 flex-1">
				<div class="text-sm font-bold text-text-primary">{item.nome}</div>
				<span
					class="mt-1.5 inline-block rounded-md border px-1.5 py-px text-2xs {item.meu
						? 'border-primary-200 bg-primary-50 font-bold text-primary-600'
						: 'border-border-subtle bg-surface-muted font-semibold text-text-secondary'}"
				>
					Incluído por {item.incluidoPor}
				</span>
			</div>
			{#if item.meu}
				<span class="grid h-8 w-8 place-items-center rounded-md bg-danger-50 text-danger-600">
					<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" /></svg>
				</span>
			{/if}
		</div>
	{/each}
</div>
