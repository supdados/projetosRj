<script lang="ts">
	/**
	 * Orquestra as Novidades no shell `(app)`: carrega depois do login, abre
	 * sozinha a mais recente não vista (uma vez por pessoa — o servidor lembra),
	 * reabre pelo `?novidade=<slug>` (ação "Rever" do toast) e, ao fechar, mostra
	 * o toast "Tudo pronto" apontando para o botão Novidades do topo.
	 *
	 * Montado UMA vez em `routes/(app)/+layout.svelte`.
	 */
	import { get } from 'svelte/store';
	import { goto } from '$app/navigation';
	import { base } from '$app/paths';
	import { page } from '$app/stores';
	import NovidadesModal from '$lib/components/novidades/NovidadesModal.svelte';
	import { CONTEUDO_NOVIDADES, temConteudoNovidade } from '$lib/novidades/conteudo';
	import {
		hrefParaRever,
		novidadeParaAbrirSozinha,
		slugDaUrl,
		urlSemNovidade
	} from '$lib/novidades/selecao';
	import { auth } from '$lib/stores/auth';
	import { flash } from '$lib/stores/flash';
	import { novidades } from '$lib/stores/novidades';

	let carregadaPara: number | null = null;

	$effect(() => {
		const userId = $auth.status === 'authenticated' ? ($auth.user?.id ?? null) : null;
		if (userId === carregadaPara) return;
		carregadaPara = userId;
		if (userId === null) {
			novidades.limpar();
			return;
		}
		void novidades.carregar().then((itens) => {
			const slug = novidadeParaAbrirSozinha(itens, temConteudoNovidade);
			if (slug && !get(novidades).aberta) novidades.abrir(slug);
		});
	});

	// "Rever" do toast: `?novidade=<slug>` abre o modal e sai da URL (serve uma vez só).
	$effect(() => {
		const url = $page.url;
		const slug = slugDaUrl(url);
		if (!slug) return;
		if (temConteudoNovidade(slug)) novidades.abrir(slug);
		void goto(urlSemNovidade(url), { replaceState: true, noScroll: true, keepFocus: true });
	});

	const aberta = $derived($novidades.aberta);
	const conteudo = $derived(aberta ? (CONTEUDO_NOVIDADES[aberta.slug] ?? null) : null);

	function avisarComoRever(slug: string, caminho: string): void {
		flash.info('Tudo pronto', {
			key: 'novidades-rever',
			description: 'Para rever, use o botão Novidades, no topo.',
			action: { label: 'Rever', href: hrefParaRever(caminho, slug) }
		});
	}

	function fechar(concluida: boolean): void {
		if (!aberta) return;
		const { slug, previa } = aberta;
		void novidades.fechar(concluida);
		if (!previa) avisarComoRever(slug, $page.url.pathname);
	}

	function acaoFinal(): void {
		if (!aberta || !conteudo) return;
		const { slug, previa } = aberta;
		const destino = `${base}${conteudo.acaoFinal.href}`;
		void novidades.fechar(true);
		void goto(destino);
		if (!previa) avisarComoRever(slug, destino);
	}
</script>

{#if aberta && conteudo}
	{#key aberta.slug}
		<NovidadesModal {conteudo} onFechar={fechar} onAcaoFinal={acaoFinal} />
	{/key}
{/if}
