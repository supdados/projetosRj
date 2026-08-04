<script lang="ts">
	/**
	 * Assistente virtual — porta 1:1 do widget que vivia em `templates/base.html`
	 * na v4.5 (launcher flutuante + painel com iframe do chatbot).
	 *
	 * Mantém o contrato original com o embed:
	 *  - token vem de `GET /api/chatbot-token` (o portal troca sua API key por um
	 *    token efêmero no upstream) e vai na query do `/embed`;
	 *  - `conversation_started` trava o fechamento por clique fora (não descartar
	 *    conversa em andamento sem querer);
	 *  - `close_embed` fecha o painel a pedido do próprio iframe;
	 *  - `token_request` é respondido com `token_response` na origem do chatbot.
	 *
	 * Desligado = a meta `chatbot-base-url` não existe no HTML (só sai quando
	 * CHATBOT_ENABLED e CHATBOT_BASE_URL estão preenchidos).
	 */
	import { onMount } from 'svelte';

	const TOKEN_URL = '/api/chatbot-token';

	let baseUrl = $state('');
	let open = $state(false);
	let iconLoaded = $state(false);
	let statusMessage = $state('Conectando ao assistente…');
	let statusIsError = $state(false);
	let statusIsLoading = $state(false);
	let frameVisible = $state(false);
	let frameEl = $state<HTMLIFrameElement | null>(null);
	let panelEl = $state<HTMLElement | null>(null);
	let launcherEl = $state<HTMLButtonElement | null>(null);

	let frameLoaded = false;
	let loading = false;
	// Conversa em andamento não pode ser descartada por um clique fora distraído.
	let hasConversation = false;

	const origin = $derived.by(() => {
		if (!baseUrl) return '';
		try {
			return new URL(baseUrl).origin;
		} catch {
			return '';
		}
	});

	onMount(() => {
		baseUrl =
			document.querySelector<HTMLMetaElement>('meta[name="chatbot-base-url"]')?.content?.trim() ?? '';
	});

	function setStatus(message: string, isError = false, isLoading = false): void {
		statusMessage = message;
		statusIsError = isError;
		statusIsLoading = isLoading;
		frameVisible = false;
	}

	async function fetchToken(): Promise<string> {
		const response = await fetch(TOKEN_URL, {
			credentials: 'same-origin',
			headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' }
		});
		const payload = await response.json().catch(() => ({}));
		if (!response.ok || !payload.token) {
			throw new Error(payload.error || 'Falha ao obter token do chatbot.');
		}
		return payload.token;
	}

	async function ensureLoaded(): Promise<void> {
		if (!frameEl || loading) return;
		if (frameLoaded) {
			frameVisible = true;
			return;
		}
		loading = true;
		setStatus('Conectando ao assistente…', false, true);
		try {
			const token = await fetchToken();
			frameEl.src = `${baseUrl}/embed?token=${encodeURIComponent(token)}`;
			hasConversation = false;
			frameLoaded = true;
			frameVisible = true;
		} catch (error) {
			setStatus(
				error instanceof Error ? error.message : 'Não foi possível carregar o assistente.',
				true
			);
		} finally {
			loading = false;
		}
	}

	function toggle(): void {
		open = !open;
		if (open) void ensureLoaded();
	}

	function onKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape' && open) open = false;
	}

	function onDocumentClick(event: MouseEvent): void {
		if (!open || hasConversation) return;
		const target = event.target as Node | null;
		if (!target) return;
		if (panelEl?.contains(target) || launcherEl?.contains(target)) return;
		open = false;
	}

	async function onMessage(event: MessageEvent): Promise<void> {
		if (!event.data) return;

		// Chega antes de a origem ser confiável: só marca que há conversa viva.
		if (event.data.type === 'conversation_started') {
			if (frameEl && event.source === frameEl.contentWindow) hasConversation = true;
			return;
		}
		if (event.origin !== origin) return;

		if (event.data.type === 'close_embed') {
			hasConversation = false;
			open = false;
			return;
		}
		if (event.data.type !== 'token_request') return;

		try {
			const renewed = await fetchToken();
			frameEl?.contentWindow?.postMessage({ type: 'token_response', token: renewed }, origin);
		} catch {
			frameLoaded = false;
			hasConversation = false;
			setStatus('Não foi possível renovar a sessão do assistente.', true);
		}
	}

	// Painel aberto trava o scroll do documento (paridade com body.dashboard-chatbot-open).
	$effect(() => {
		document.body.classList.toggle('dashboard-chatbot-open', open);
		return () => document.body.classList.remove('dashboard-chatbot-open');
	});
</script>

<svelte:window onkeydown={onKeydown} onmessage={onMessage} />
<svelte:document onclickcapture={onDocumentClick} />

{#if baseUrl}
	<button
		bind:this={launcherEl}
		type="button"
		class="dashboard-chatbot-launcher"
		class:is-icon-loaded={iconLoaded}
		aria-controls="dashboardChatbotPanel"
		aria-expanded={open}
		aria-label="Assistente virtual"
		onclick={toggle}
	>
		<img
			src="{baseUrl}/icon-chat.svg"
			class="chatbot-launcher-icon chatbot-launcher-icon--normal"
			alt=""
			aria-hidden="true"
			onload={() => (iconLoaded = true)}
		/>
		<img
			src="{baseUrl}/icon-chat-active.svg"
			class="chatbot-launcher-icon chatbot-launcher-icon--active"
			alt=""
			aria-hidden="true"
		/>
	</button>

	<section
		bind:this={panelEl}
		id="dashboardChatbotPanel"
		class="dashboard-chatbot-panel"
		hidden={!open}
		aria-label="Assistente virtual de serviços"
	>
		{#if !frameVisible}
			<div
				class="dashboard-chatbot-status"
				class:is-loading={statusIsLoading}
				class:is-error={statusIsError}
			>
				{statusMessage}
			</div>
		{/if}

		<div class="dashboard-chatbot-frame-shell" hidden={!frameVisible}>
			<iframe
				bind:this={frameEl}
				id="dashboardChatbotFrame"
				class="dashboard-chatbot-frame"
				title="Assistente virtual de serviços"
				loading="lazy"
				referrerpolicy="strict-origin-when-cross-origin"
				sandbox="allow-scripts allow-forms allow-same-origin allow-popups allow-popups-to-escape-sandbox"
				allow="clipboard-write; microphone"
			></iframe>
		</div>
	</section>
{/if}

<style>
	/* Valores literais da v4.5 (static/css/style.css) — paridade visual exata com
	   o widget anterior, por isso não passam pelos tokens do design system. */
	.dashboard-chatbot-launcher {
		position: fixed;
		right: 1.25rem;
		bottom: 1.25rem;
		z-index: 1041;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		padding: 0.6rem;
		border: 0;
		border-radius: 999px;
		background: #e2e8f0;
		box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
		cursor: pointer;
		transition:
			transform 0.16s ease,
			background-color 0.16s ease;
	}
	/* Fallback enquanto os ícones do chatbot não carregam: ícone do Font Awesome. */
	.dashboard-chatbot-launcher::before {
		content: '\f059';
		font-family: 'Font Awesome 6 Free';
		font-weight: 900;
		color: #0077b6;
		font-size: 1.2rem;
		line-height: 1;
	}
	.chatbot-launcher-icon {
		width: 56px;
		height: 56px;
		display: none;
		flex-shrink: 0;
	}
	.dashboard-chatbot-launcher.is-icon-loaded::before {
		display: none;
	}
	.dashboard-chatbot-launcher.is-icon-loaded .chatbot-launcher-icon--normal {
		display: block;
	}
	.dashboard-chatbot-launcher.is-icon-loaded[aria-expanded='true'] .chatbot-launcher-icon--normal {
		display: none;
	}
	.dashboard-chatbot-launcher.is-icon-loaded[aria-expanded='true'] .chatbot-launcher-icon--active {
		display: block;
	}
	.dashboard-chatbot-launcher:hover,
	.dashboard-chatbot-launcher:focus-visible {
		transform: translateY(-2px);
		background: #cbd5e1;
	}
	.dashboard-chatbot-launcher[aria-expanded='true'] {
		background: #cbd5e1;
	}

	.dashboard-chatbot-panel {
		position: fixed;
		right: 1.25rem;
		bottom: 6rem;
		width: min(26rem, calc(100vw - 1.5rem));
		height: clamp(22rem, 62vh, 36rem);
		z-index: 1040;
		display: flex;
		flex-direction: column;
		overflow: hidden;
		border: 1px solid rgba(0, 90, 146, 0.14);
		border-radius: 1.25rem;
		background: #fff;
		box-shadow:
			0 24px 60px rgba(15, 23, 42, 0.18),
			0 8px 24px rgba(15, 23, 42, 0.1);
		transform-origin: bottom right;
	}
	.dashboard-chatbot-panel[hidden] {
		display: none;
	}
	.dashboard-chatbot-panel:not([hidden]) {
		animation: chatbotPanelIn 0.22s cubic-bezier(0.34, 1.15, 0.64, 1) both;
	}
	@keyframes chatbotPanelIn {
		from {
			opacity: 0;
			transform: translateY(16px) scale(0.95);
		}
		to {
			opacity: 1;
			transform: translateY(0) scale(1);
		}
	}

	.dashboard-chatbot-status {
		flex: 1;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 0.75rem;
		padding: 2rem 1.5rem;
		text-align: center;
		color: #475569;
		font-size: 0.9rem;
		line-height: 1.5;
	}
	.dashboard-chatbot-status.is-loading::before {
		content: '';
		display: block;
		width: 1.75rem;
		height: 1.75rem;
		border: 2px solid rgba(0, 119, 182, 0.2);
		border-top-color: #0077b6;
		border-radius: 50%;
		animation: chatbotSpin 0.7s linear infinite;
	}
	@keyframes chatbotSpin {
		to {
			transform: rotate(360deg);
		}
	}
	.dashboard-chatbot-status.is-error {
		color: #991b1b;
	}
	.dashboard-chatbot-status.is-error::before {
		content: '\f071';
		font-family: 'Font Awesome 6 Free';
		font-weight: 900;
		font-size: 1.4rem;
		display: block;
		color: #dc2626;
		animation: none;
		border: none;
		width: auto;
		height: auto;
	}

	.dashboard-chatbot-frame-shell {
		flex: 1;
		min-height: 0;
		display: flex;
		flex-direction: column;
	}
	.dashboard-chatbot-frame-shell[hidden] {
		display: none;
	}
	.dashboard-chatbot-frame {
		display: block;
		width: 100%;
		height: 100%;
		border: 0;
		background: #fff;
	}

	:global([data-theme='dark']) .dashboard-chatbot-panel {
		border-color: rgba(77, 169, 249, 0.16);
		background: #0f1c2e;
		box-shadow:
			0 28px 64px rgba(0, 0, 0, 0.5),
			0 8px 24px rgba(0, 0, 0, 0.3);
	}
	:global([data-theme='dark']) .dashboard-chatbot-frame {
		background: #0f1c2e;
	}
	:global([data-theme='dark']) .dashboard-chatbot-status {
		color: #94a3b8;
	}
	:global([data-theme='dark']) .dashboard-chatbot-status.is-error {
		color: #fca5a5;
	}

	@media (max-width: 991.98px) {
		.dashboard-chatbot-panel {
			right: 0.75rem;
			left: 0.75rem;
			bottom: 5.75rem;
			width: auto;
			height: min(65dvh, calc(100vh - 6.5rem));
			border-radius: 1.1rem;
		}
		.dashboard-chatbot-launcher {
			right: 0.75rem;
			bottom: 0.75rem;
		}
	}
</style>
