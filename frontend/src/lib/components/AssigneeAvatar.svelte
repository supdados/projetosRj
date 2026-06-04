<script lang="ts">
	/**
	 * Avatar circular de INICIAIS (sem foto) para responsáveis de tarefa.
	 *
	 * A cor de fundo é derivada deterministicamente do nome (hue por hash) com
	 * saturação/luminância fixas + texto branco — legível em tema claro E escuro
	 * sem depender de tokens de tema (a cor do avatar é a mesma nos dois temas,
	 * como na referência de design).
	 *
	 * Uso: <AssigneeAvatar name="Alex Johnson" size="sm" />
	 */
	interface Props {
		name: string;
		/** Iniciais já calculadas pelo backend; se ausente, derivamos do nome. */
		initials?: string;
		size?: 'sm' | 'md' | 'lg';
		title?: string;
	}

	let { name, initials, size = 'sm', title }: Props = $props();

	function computeInitials(value: string): string {
		const parts = (value || '').trim().split(/\s+/).filter(Boolean);
		if (parts.length === 0) return '?';
		if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
		return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
	}

	function hueFor(value: string): number {
		let hash = 0;
		const source = value || '?';
		for (let i = 0; i < source.length; i++) {
			hash = (hash * 31 + source.charCodeAt(i)) % 360;
		}
		return hash;
	}

	const text = $derived(initials ?? computeInitials(name));
	const hue = $derived(hueFor(name || '?'));
	const dim = $derived(
		size === 'lg'
			? 'h-8 w-8 text-xs'
			: size === 'md'
				? 'h-7 w-7 text-[11px]'
				: 'h-6 w-6 text-[10px]'
	);
</script>

<span
	class="inline-flex shrink-0 items-center justify-center rounded-full font-semibold leading-none text-white ring-1 ring-black/10 {dim}"
	style="background-color: hsl({hue} 52% 45%);"
	title={title ?? name}
	aria-hidden="true"
>
	{text}
</span>
