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
		// O ROUTER opera na RAIZ (base vazia) para casar com os PATHS NATIVOS
		// servidos pelo Flask (`/dashboard`, `/projetos`, `/tarefas`, `/admin/*`,
		// `/busca`, `/calendarios`...). routes/spa.py serve o index (via Jinja, com
		// CSP nonce) nesses paths, entao deep-link/refresh (F5) resolvem a rota
		// client-side correta sem loop.
		//
		// Os ASSETS continuam fisicamente sob /static/spa/ (adapter-static gravou
		// ali). `assets` e independente de `base` no SvelteKit: o bootstrap usa
		// `assets` para resolver modulepreload/start/app e os chunks, enquanto o
		// roteamento client-side usa `base`. Assim o router fica coerente com a URL
		// servida sem precisar duplicar/mover o bundle.
		paths: {
			base: '',
			relative: false
		}
	}
};

export default config;
