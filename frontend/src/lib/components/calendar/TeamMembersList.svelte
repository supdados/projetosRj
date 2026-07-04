<script lang="ts">
	import AssigneeAvatar from '$lib/components/AssigneeAvatar.svelte';
	import type { CalendarMember } from '$lib/types/calendar';

	interface Props {
		members: CalendarMember[];
	}

	let { members }: Props = $props();
</script>

<section aria-label="Time">
	<h3 class="mb-2 text-2xs font-semibold uppercase tracking-wider text-text-muted">
		Time
	</h3>

	{#if members.length === 0}
		<p class="text-sm text-text-muted">Nenhum membro encontrado.</p>
	{:else}
		<ul class="space-y-1" role="list">
			{#each members as member (member.id)}
				<li class="flex items-center gap-2 rounded-md px-1 py-1">
					<AssigneeAvatar name={member.name} initials={member.initials} size="sm" />
					<span class="truncate text-sm text-text-primary">{member.name}</span>
				</li>
			{/each}
		</ul>
	{/if}
</section>
