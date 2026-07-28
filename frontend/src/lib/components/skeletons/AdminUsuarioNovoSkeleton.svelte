<script lang="ts">
	/**
	 * Skeleton de Admin > Usuários > Novo, espelho do estado pronto
	 * (UserForm.svelte modo create): 3 fieldsets em card (Identificação,
	 * Credenciais, Vínculo e Permissões) + barra de ações. Sem salto de layout
	 * na 1a visita — CPF aqui é sempre o campo editável (sem cadeado/gov.br
	 * travado, que só existe na edição).
	 */
	import Skeleton from '$lib/components/Skeleton.svelte';
</script>

<div aria-hidden="true" class="contents">
	<!-- Identificação: 4 campos em grade 2 colunas -->
	<section class="flex flex-col gap-4 rounded-xl border border-border-subtle bg-surface px-5 py-4">
		<div class="flex flex-col gap-0.5">
			<Skeleton class="h-4 w-32 rounded-md" />
			<Skeleton class="h-3 w-56 rounded" />
		</div>
		<div class="grid gap-4 md:grid-cols-2">
			{#each { length: 4 } as _, i (i)}
				<div class="flex flex-col gap-1.5">
					<Skeleton class="h-2.5 w-24 rounded" />
					<Skeleton class="h-10 w-full rounded-lg" />
				</div>
			{/each}
		</div>
	</section>

	<!-- Credenciais: 1 campo (senha obrigatória na criação) -->
	<section class="mt-4 flex flex-col gap-4 rounded-xl border border-border-subtle bg-surface px-5 py-4">
		<div class="flex flex-col gap-0.5">
			<Skeleton class="h-4 w-28 rounded-md" />
			<Skeleton class="h-3 w-64 rounded" />
		</div>
		<div class="flex max-w-md flex-col gap-1.5">
			<Skeleton class="h-2.5 w-16 rounded" />
			<Skeleton class="h-10 w-full rounded-lg" />
		</div>
	</section>

	<!-- Vínculo e Permissões: cartão admin + seletor de órgãos -->
	<section class="mt-4 flex flex-col gap-4 rounded-xl border border-border-subtle bg-surface px-5 py-4">
		<div class="flex flex-col gap-0.5">
			<Skeleton class="h-4 w-48 rounded-md" />
			<Skeleton class="h-3 w-72 rounded" />
		</div>

		<div class="flex items-start gap-3 rounded-lg border border-border-subtle bg-surface-muted px-4 py-3">
			<Skeleton class="mt-0.5 h-4 w-4 rounded" />
			<div class="flex min-w-0 flex-1 flex-col gap-1.5">
				<Skeleton class="h-3.5 w-32 rounded" />
				<Skeleton class="h-3 w-full rounded" />
			</div>
		</div>

		<div class="flex flex-col gap-2">
			<div class="flex flex-wrap items-center justify-between gap-2">
				<Skeleton class="h-2.5 w-40 rounded" />
				<Skeleton class="h-3 w-24 rounded" />
			</div>
			<div class="overflow-hidden rounded-lg border border-border-subtle">
				<div class="h-10 w-full border-b border-border-subtle bg-surface-muted"></div>
				<div class="grid grid-cols-1 gap-1 p-2 sm:grid-cols-2 lg:grid-cols-3">
					{#each { length: 9 } as _, i (i)}
						<div class="flex items-center gap-2 rounded-md px-2.5 py-1.5">
							<Skeleton class="h-4 w-4 shrink-0 rounded" />
							<Skeleton class="h-3.5 w-24 rounded" />
						</div>
					{/each}
				</div>
			</div>
		</div>
	</section>

	<!-- Barra de ações -->
	<div class="mt-4 flex items-center justify-end gap-2">
		<Skeleton class="h-9 w-24 rounded-md" />
		<Skeleton class="h-9 w-36 rounded-md" />
	</div>
</div>
