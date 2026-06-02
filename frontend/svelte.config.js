import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	kit: {
		// Bundle estatico (CSR puro) servido pelo Flask via routes/spa.py.
		// fallback: index.html servido como template Jinja (injeta csp_nonce + csrf-token).
		adapter: adapter({
			pages: '../static/spa',
			assets: '../static/spa',
			fallback: 'index.html',
			precompress: false,
			strict: false
		}),
		// Backend Flask cuida do CSRF (cookie de sessao + X-CSRFToken).
		// Desligar a verificacao de origem do Kit (trustedOrigins:['*'] aceita qualquer origem);
		// em SvelteKit 2.61 'csrf.checkOrigin' foi substituido por 'csrf.trustedOrigins'.
		csrf: {
			trustedOrigins: ['*']
		},
		// Assets do bundle vivem sob /static/spa/ na origem Flask.
		paths: {
			base: '/static/spa',
			relative: false
		}
	}
};

export default config;
