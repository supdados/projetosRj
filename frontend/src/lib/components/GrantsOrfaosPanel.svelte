<script lang="ts">
	/**
	 * Painel admin de grants órfãos (S4/F3-25): convites ativos cujo concedente
	 * foi removido ou perdeu rank gestor no projeto. Só renderiza quando há algo
	 * a revisar — sem grants (ou sem tabela de convites) não ocupa a tela.
	 */
	import { onMount } from 'svelte';
	import { fetchGrantsOrfaos } from '$lib/api/adminReports';
	import type { GrantOrfao, GrantOrfaoMotivo } from '$lib/types/adminReports';

	let grants = $state<GrantOrfao[]>([]);

	const MOTIVO_LABEL: Record<GrantOrfaoMotivo, string> = {
		concedente_removido: 'Concedente removido',
		concedente_sem_gestao: 'Concedente sem gestão'
	};

	function isoToBr(iso: string | null): string {
		if (!iso) return '—';
		const d = new Date(iso);
		if (Number.isNaN(d.getTime())) return '—';
		return d.toLocaleDateString('pt-BR', {
			day: '2-digit',
			month: '2-digit',
			year: 'numeric',
			timeZone: 'UTC'
		});
	}

	onMount(() => {
		const controller = new AbortController();
		void fetchGrantsOrfaos(controller.signal)
			.then((result) => {
				grants = result;
			})
			.catch(() => {
				// Relatório de housekeeping: falha silenciosa não bloqueia a tela.
			});
		return () => controller.abort();
	});
</script>

{#if grants.length > 0}
	<section
		aria-labelledby="grants-orfaos-title"
		class="overflow-hidden rounded-xl border border-warning-soft bg-surface"
	>
		<div class="flex items-center gap-2 border-b border-border-subtle bg-surface-muted px-4 py-2.5">
			<i class="fas fa-triangle-exclamation text-warning" aria-hidden="true"></i>
			<h2 id="grants-orfaos-title" class="text-sm font-semibold text-text-primary">
				Convites órfãos ({grants.length})
			</h2>
			<span class="text-xs text-text-muted">
				Convites ativos cujo concedente não pode mais geri-los — revise ou revogue no projeto.
			</span>
		</div>
		<div class="overflow-x-auto">
			<table class="w-full border-collapse align-middle text-sm">
				<caption class="sr-only">Convites ativos sem concedente responsável</caption>
				<thead>
					<tr class="border-b border-border-subtle bg-surface-muted text-left">
						<th scope="col" class="whitespace-nowrap px-3 py-2 text-2xs font-semibold uppercase tracking-caps text-text-muted">Projeto</th>
						<th scope="col" class="whitespace-nowrap px-3 py-2 text-2xs font-semibold uppercase tracking-caps text-text-muted">Convidado</th>
						<th scope="col" class="whitespace-nowrap px-3 py-2 text-2xs font-semibold uppercase tracking-caps text-text-muted">Concedente</th>
						<th scope="col" class="whitespace-nowrap px-3 py-2 text-2xs font-semibold uppercase tracking-caps text-text-muted">Motivo</th>
						<th scope="col" class="whitespace-nowrap px-3 py-2 text-2xs font-semibold uppercase tracking-caps text-text-muted">Criado em</th>
						<th scope="col" class="whitespace-nowrap px-3 py-2 text-2xs font-semibold uppercase tracking-caps text-text-muted">Expira em</th>
					</tr>
				</thead>
				<tbody>
					{#each grants as grant (grant.member_id)}
						<tr class="border-t border-border-subtle transition-colors duration-fast hover:bg-surface-muted">
							<td class="px-3 py-2 align-middle font-medium text-text-primary">{grant.project_titulo}</td>
							<td class="px-3 py-2 align-middle text-text-secondary">{grant.user_name}</td>
							<td class="px-3 py-2 align-middle text-text-secondary">
								{grant.granted_by_name ?? 'Removido'}
							</td>
							<td class="px-3 py-2 align-middle">
								<span
									class="inline-flex items-center rounded-full border border-warning-soft bg-surface-muted px-2 py-0.5 text-xs font-bold text-warning"
								>
									{MOTIVO_LABEL[grant.motivo]}
								</span>
							</td>
							<td class="whitespace-nowrap px-3 py-2 align-middle text-text-secondary">{isoToBr(grant.created_at)}</td>
							<td class="whitespace-nowrap px-3 py-2 align-middle text-text-secondary">{isoToBr(grant.expires_at)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	</section>
{/if}
