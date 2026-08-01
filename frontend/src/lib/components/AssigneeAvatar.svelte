<script lang="ts">
	/**
	 * Avatar circular de iniciais; cor por nome via avatarPalette.
	 * Uso: <AssigneeAvatar name="Alex Johnson" size="sm" />
	 */
	interface Props {
		name: string;
		/** Iniciais já calculadas pelo backend; se ausente, derivamos do nome. */
		initials?: string;
		size?: 'xs' | 'sm' | 'md' | 'lg';
		title?: string;
	}

	import { avatarColorForName } from '$lib/utils/avatarPalette';

	let { name, initials, size = 'sm', title }: Props = $props();

	function computeInitials(value: string): string {
		const parts = (value || '').trim().split(/\s+/).filter(Boolean);
		if (parts.length === 0) return '?';
		if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
		return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
	}

	const text = $derived(initials ?? computeInitials(name));
	const bgColor = $derived(avatarColorForName(name || '?'));
	const dim = $derived(
		size === 'lg'
			? 'h-8 w-8 text-xs'
			: size === 'md'
				? 'h-7 w-7 text-2xs'
				: size === 'xs'
					? 'h-5 w-5 text-[9px]'
					: 'h-6 w-6 text-[10px]'
	);
</script>

<span
	class="inline-flex shrink-0 items-center justify-center rounded-full font-semibold leading-none text-white ring-1 ring-border-subtle {dim}"
	style="background-color: {bgColor};"
	title={title ?? name}
	aria-hidden="true"
>
	{text}
</span>
