<script lang="ts">
	/**
	 * Painel de projetos recentes do Dashboard. Lista acessivel (cada item
	 * focavel via link). Status -> Badge. Datas derivadas chegam prontas do
	 * backend (read-only).
	 */
	import { base } from '$app/paths';
	import Card from './Card.svelte';
	import Badge from './Badge.svelte';
	import type { Project, ProjectStatus } from '$lib/types/entities';

	interface Props {
		projects: Project[];
	}

	let { projects }: Props = $props();

	function statusTone(status: ProjectStatus): 'success' | 'info' {
		return status === 'Finalizado' ? 'success' : 'info';
	}
</script>

<Card title="Projetos recentes" labelId="recent-projects-title">
	{#if projects.length === 0}
		<p class="text-sm text-text-muted">Nenhum projeto recente.</p>
	{:else}
		<ul class="flex flex-col gap-2" aria-labelledby="recent-projects-title">
			{#each projects as project (project.id)}
				<li>
					<a
						href={`${base}/projetos/${project.id}`}
						class="flex items-center justify-between gap-3 rounded-md border border-border-subtle bg-surface px-4 py-3 no-underline transition-colors duration-fast hover:bg-surface-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
					>
						<span class="flex min-w-0 flex-col">
							<span class="truncate font-medium text-text-primary">
								{project.titulo}
							</span>
							{#if project.orgao_sigla || project.orgao}
								<span class="truncate text-xs text-text-muted">
									{project.orgao_sigla ?? project.orgao}
								</span>
							{/if}
						</span>
						<Badge tone={statusTone(project.status)}>{project.status}</Badge>
					</a>
				</li>
			{/each}
		</ul>
	{/if}
</Card>
