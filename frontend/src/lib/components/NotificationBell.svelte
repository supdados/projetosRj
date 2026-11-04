<script lang="ts">
	/**
	 * Sino da topnav: botão com ponto + dropdown de notificações. Extraído do
	 * `AppTopnav.svelte` (que passava de 900 linhas) quando ganhou o polling.
	 *
	 * Resumo (`GET /api/notificacoes/resumo`): consultado ao montar, a cada
	 * ~60 s com a aba visível, ao voltar à aba e a cada navegação. O ponto soma
	 * não lidas + convites pendentes (`contagemDoSino`) — o convite segue
	 * pendente depois de "marcar lidas", então a linha de convites no topo do
	 * dropdown explica o ponto aceso e leva a quem responde. Convite NOVO vira
	 * toast com "Ver convite" (memória por pessoa no `localStorage`).
	 *
	 * Abrir o sino mantém o comportamento do v4.5: carrega a lista E marca
	 * tudo como lido. Sem botões de ação dentro do dropdown nesta entrega.
	 */
	import { afterNavigate } from '$app/navigation';
	import { base } from '$app/paths';
	import AppIcon from '$lib/components/AppIcon.svelte';
	import { APP_ICONS } from '$lib/icons/appIcons';
	import { ApiClientError } from '$lib/api/client';
	import { invalidateColecoes } from '$lib/api/collections';
	import {
		fetchNotificacoes,
		fetchNotificacoesResumo,
		marcarNotificacoesLidas
	} from '$lib/api/notifications';
	import { flash } from '$lib/stores/flash';
	import { notificationSummary } from '$lib/stores/notificationSummary';
	import {
		avisoDeConvitesNovos,
		contagemDoSino,
		convitesNaoAvisados,
		gravarConvitesAvisados,
		lerConvitesAvisados,
		rotuloDoSino,
		type ArmazenamentoDeAvisos
	} from '$lib/utils/notificationSummary';
	import { notificationIcon } from '$lib/utils/notificationIcon';
	import { iniciarPolling } from '$lib/utils/summaryPolling';
	import type { NotificacoesResumo, Notificacao } from '$lib/types/notifications';

	interface Props {
		/** Usuário logado; `null` (boot/sem sessão) não consulta nada. */
		userId: number | null;
	}

	let { userId }: Props = $props();

	/** Leve o bastante para rodar sempre; a aba oculta pula o tique. */
	const RESUMO_INTERVALO_MS = 60_000;
	/** Convite é ação pendente: o toast fica o teto do flash, não os 4 s do info. */
	const TOAST_CONVITE_MS = 10_000;

	let notifOpen = $state(false);
	let notifMenuEl = $state<HTMLDivElement | null>(null);
	let notifToggleEl = $state<HTMLButtonElement | null>(null);
	let notifItems = $state<Notificacao[]>([]);
	let notifLoading = $state(false);
	let notifError = $state(false);
	let notifLoadedOnce = $state(false);

	const resumo = $derived($notificationSummary);
	const pontoAceso = $derived(contagemDoSino(resumo) > 0);
	const rotulo = $derived(rotuloDoSino(resumo));
	const naoLidas = $derived(resumo?.unread_count ?? 0);
	const convitesPendentes = $derived(resumo?.convites ?? []);
	// Um convite leva direto à página dele (Aceitar/Recusar); vários, ao índice.
	const convitesHref = $derived(
		convitesPendentes.length === 1
			? `${base}/colecoes/${convitesPendentes[0].collection_id}`
			: `${base}/colecoes`
	);

	function armazenamentoSeguro(): ArmazenamentoDeAvisos | null {
		try {
			return window.localStorage;
		} catch {
			return null;
		}
	}

	/**
	 * Toast para convite ainda não avisado; devolve o conjunto novo de avisados
	 * (= pendentes atuais: o respondido sai e um reenvio volta a avisar).
	 */
	function avisarConvitesNovos(
		atual: NotificacoesResumo,
		avisados: ReadonlySet<number>,
		donoDaMemoria: number
	): Set<number> {
		const novos = convitesNaoAvisados(atual.convites, avisados);
		const pendentes = new Set(atual.convites.map((c) => c.collection_id));
		const mudou = novos.length > 0 || [...avisados].some((id) => !pendentes.has(id));
		if (mudou) gravarConvitesAvisados(armazenamentoSeguro(), donoDaMemoria, pendentes);
		const aviso = avisoDeConvitesNovos(novos, base);
		if (!aviso) return pendentes;
		// O índice e a página da coleção não podem servir o cache de antes do convite.
		invalidateColecoes();
		flash.info(aviso.mensagem, {
			key: aviso.key,
			action: { label: aviso.acao, href: aviso.href },
			durationMs: TOAST_CONVITE_MS
		});
		return pendentes;
	}

	// Polling ligado só com usuário: sem sessão não há o que consultar.
	$effect(() => {
		const id = userId;
		if (id === null) return;
		let avisados = lerConvitesAvisados(armazenamentoSeguro(), id);
		const polling = iniciarPolling({
			carregar: (signal) => fetchNotificacoesResumo(signal),
			aoReceber: (atual) => {
				notificationSummary.definir(atual);
				avisados = avisarConvitesNovos(atual, avisados, id);
			},
			documentoOculto: () => document.hidden,
			intervaloMs: RESUMO_INTERVALO_MS,
			deveParar: (erro) => erro instanceof ApiClientError && erro.code === 'unauthenticated'
		});
		notificationSummary.registrarAtualizador(polling.atualizarAgora);
		const aoVoltarParaAba = (): void => {
			if (!document.hidden) polling.atualizarAgora();
		};
		document.addEventListener('visibilitychange', aoVoltarParaAba);
		return () => {
			polling.parar();
			notificationSummary.registrarAtualizador(null);
			document.removeEventListener('visibilitychange', aoVoltarParaAba);
		};
	});

	// A carga inicial ('enter') já é a do polling; daqui em diante, a cada troca de tela.
	afterNavigate((navegacao) => {
		if (navegacao.type === 'enter') return;
		notificationSummary.atualizar();
	});

	/** Tempo relativo em PT a partir de ISO 8601 (ex.: "há 2 dias"). */
	function relativeTime(iso: string | null): string {
		if (!iso) return '';
		const then = Date.parse(iso);
		if (Number.isNaN(then)) return '';
		const sec = Math.round((Date.now() - then) / 1000);
		if (sec < 45) return 'agora mesmo';
		const min = Math.round(sec / 60);
		if (min < 60) return `há ${min} min`;
		const hours = Math.round(min / 60);
		if (hours < 24) return `há ${hours} h`;
		const days = Math.round(hours / 24);
		if (days < 7) return `há ${days} dia${days > 1 ? 's' : ''}`;
		const weeks = Math.round(days / 7);
		if (weeks < 5) return `há ${weeks} semana${weeks > 1 ? 's' : ''}`;
		const months = Math.round(days / 30);
		if (months < 12) return `há ${months} ${months > 1 ? 'meses' : 'mês'}`;
		const years = Math.round(days / 365);
		return `há ${years} ano${years > 1 ? 's' : ''}`;
	}

	/**
	 * Igual ao v4.5: ao ABRIR o sino, carrega os itens E marca-lidas (o ponto
	 * de não lidas apaga). A lista preserva `is_unread` da carga (destaque dos
	 * novos); os convites pendentes seguem no ponto até serem respondidos.
	 */
	async function loadNotifications(): Promise<void> {
		if (notifLoading) return;
		notifLoading = true;
		notifError = false;
		try {
			const list = await fetchNotificacoes();
			notifItems = list.items;
			notificationSummary.definirNaoLidas(list.unread_count);
			notifLoadedOnce = true;
			try {
				const marked = await marcarNotificacoesLidas();
				notificationSummary.definirNaoLidas(marked.unread_count);
			} catch {
				// Falha ao marcar nao deve apagar a lista ja carregada.
			}
		} catch {
			notifError = true;
		} finally {
			notifLoading = false;
			// Depois do marcar-lidas: um resumo pedido antes dele reacenderia o ponto.
			notificationSummary.atualizar();
		}
	}

	function closeNotif(): void {
		notifOpen = false;
	}

	function toggleNotif(): void {
		notifOpen = !notifOpen;
		if (notifOpen) void loadNotifications();
	}

	/** Esc fecha e devolve o foco ao sino; consome o gesto para o toast não sair junto. */
	function handleWindowKeydown(event: KeyboardEvent): void {
		if (event.key !== 'Escape' || !notifOpen) return;
		// O FlashToasts (listener irmão no window) checa defaultPrevented para não
		// dispensar um toast no MESMO Esc que fechou este dropdown.
		event.preventDefault();
		closeNotif();
		notifToggleEl?.focus();
	}

	function handleOutsideClick(event: MouseEvent): void {
		if (notifOpen && notifMenuEl && !notifMenuEl.contains(event.target as Node)) closeNotif();
	}

	function rotuloDosConvites(n: number): string {
		return n === 1 ? '1 convite aguardando resposta' : `${n} convites aguardando resposta`;
	}

	const stateCls =
		'app-notifications-state rounded-lg border border-border-subtle bg-surface-muted px-3 py-3 text-sm text-text-secondary';
</script>

<svelte:window onclick={handleOutsideClick} onkeydown={handleWindowKeydown} />

<div bind:this={notifMenuEl} class="relative inline-flex">
	<button
		bind:this={notifToggleEl}
		type="button"
		onclick={toggleNotif}
		aria-haspopup="menu"
		aria-expanded={notifOpen}
		title={rotulo}
		aria-label={rotulo}
		class="relative inline-flex h-[1.95rem] w-[1.95rem] items-center justify-center rounded-md border border-transparent text-md transition-ui duration-[180ms] focus:outline-none focus-visible:ring-2 focus-visible:ring-on-brand {notifOpen
			? 'border-surface-elevated bg-surface-elevated text-brand dark:border-[color-mix(in_srgb,var(--ds-color-neutral-0)_10%,transparent)] dark:bg-[color-mix(in_srgb,var(--ds-color-neutral-0)_15%,transparent)] dark:text-white'
			: 'bg-transparent text-on-brand-muted hover:bg-on-brand-hover hover:text-on-topnav'}"
	>
		<svg
			width="20"
			height="20"
			viewBox="0 0 24 24"
			fill="currentColor"
			class="shrink-0"
			aria-hidden="true"
		>
			{#each APP_ICONS.sino as p (p.d)}
				<path d={p.d} opacity={p.opacity} />
			{/each}
			<g class="nav-fade" opacity={notifOpen ? 1 : 0}
				><circle cx="12" cy="21" r="1.7" opacity=".48" /></g
			>
			<g class="nav-fade" opacity={pontoAceso ? 1 : 0}
				><circle cx="17.4" cy="6.1" r="3.3" fill="#B45A45" /></g
			>
		</svg>
	</button>

	{#if notifOpen}
		<div
			role="menu"
			aria-label="Notificações"
			class="app-notifications-dropdown absolute right-0 top-full z-dropdown mt-2 w-[min(360px,90vw)] origin-top-right animate-dropdown-in overflow-hidden rounded-xl border border-border-subtle bg-surface"
			style="box-shadow: var(--ds-shadow-popover);"
		>
			<div
				class="app-notifications-dropdown-header flex items-center justify-between gap-2 border-b border-border-subtle px-4 py-3"
				aria-hidden="true"
			>
				<span class="text-sm font-semibold text-text-primary">Notificações</span>
				<span class="text-xs text-text-secondary">{naoLidas} não lida(s)</span>
			</div>
			<div class="app-notifications-list max-h-[60vh] overflow-y-auto p-2">
				{#if convitesPendentes.length > 0}
					<!-- Explica o ponto que segue aceso depois de "marcar lidas". -->
					<a
						href={convitesHref}
						role="menuitem"
						onclick={closeNotif}
						class="mb-1 flex items-center gap-3 rounded-lg border border-brand-soft bg-wash-brand px-3 py-2.5 no-underline transition-colors duration-fast hover:border-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand"
					>
						<span class="flex h-8 w-8 shrink-0 items-center justify-center text-brand">
							<AppIcon id="convite" size={20} />
						</span>
						<span class="min-w-0 flex-1 truncate text-sm font-semibold text-text-primary">
							{rotuloDosConvites(convitesPendentes.length)}
						</span>
						<span class="shrink-0 text-xs font-semibold text-brand">Responder</span>
					</a>
				{/if}
				{#if notifLoading && !notifLoadedOnce}
					<div class={stateCls}>Carregando notificações…</div>
				{:else if notifError}
					<div class={stateCls}>Não foi possível carregar as notificações.</div>
				{:else if notifItems.length === 0}
					<div class={stateCls}>Nenhuma notificação no momento.</div>
				{:else}
					{#each notifItems as item (item.id)}
						<a
							href={item.target_url ?? '#'}
							role="menuitem"
							onclick={closeNotif}
							class="app-notification-item flex items-start gap-3 rounded-lg px-3 py-2.5 no-underline transition-colors duration-fast hover:bg-surface-muted {item.is_unread
								? 'bg-surface-muted'
								: ''}"
						>
							<span class="relative flex shrink-0 items-center justify-center">
								{#if item.is_unread}
									<span
										class="absolute -left-1.5 top-1/2 h-1.5 w-1.5 -translate-y-1/2 rounded-full bg-brand"
										aria-hidden="true"
									></span>
								{/if}
								<span class="flex h-8 w-8 items-center justify-center text-brand">
									<AppIcon id={notificationIcon(item.event_type)} size={20} />
								</span>
							</span>
							<span class="min-w-0 flex-1">
								<span class="flex items-baseline justify-between gap-2">
									<span class="truncate text-sm font-semibold text-text-primary"
										>{item.title || 'Atualização'}</span
									>
									<span class="shrink-0 text-xs text-text-muted"
										>{relativeTime(item.created_at)}</span
									>
								</span>
								{#if item.message || item.actor_name}
									<span class="mt-0.5 block text-xs text-text-secondary">
										{#if item.actor_name}<span class="font-medium text-text-primary"
												>{item.actor_name}</span
											>{/if}{#if item.actor_name && item.message}&nbsp;{/if}{item.message}
									</span>
								{/if}
							</span>
						</a>
					{/each}
				{/if}
			</div>
		</div>
	{/if}
</div>

<style>
	/* Mesmo fade dos ícones da topnav (o ponto e o "aberto" cruzam a opacidade). */
	.nav-fade {
		transition: opacity 0.22s;
	}
	@media (prefers-reduced-motion: reduce) {
		.nav-fade {
			transition: none;
		}
	}
</style>
