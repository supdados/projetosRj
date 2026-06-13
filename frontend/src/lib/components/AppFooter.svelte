<script lang="ts">
	/**
	 * Rodapé do app shell: assinatura institucional da SETD (servida pelo Flask em
	 * /static/img/brand/). Duas versões PNG trocadas por tema — colorida no claro,
	 * negativa no escuro (variante `dark:` do Tailwind, ligada ao
	 * `html[data-theme="dark"]`). A imagem oculta fica `display:none`, então não é
	 * anunciada/baixada duas vezes pelo leitor de tela.
	 */
	const ALT = 'SETD — Subsecretaria de Estado de Tecnologia Digital';
</script>

<footer
	class="flex shrink-0 items-center justify-center border-t border-border-subtle bg-canvas px-5 py-2.5"
>
	<img
		src="/static/img/brand/assinatura-setd-colorida.png"
		alt={ALT}
		class="block h-6 w-auto select-none dark:hidden"
		draggable="false"
	/>
	<img
		src="/static/img/brand/assinatura-setd-negativo.png"
		alt={ALT}
		class="hidden h-6 w-auto select-none dark:block"
		draggable="false"
	/>
</footer>
