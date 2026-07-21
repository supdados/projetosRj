/**
 * Config mínima do Vitest para os utils PUROS do frontend (B2).
 *
 * Ambiente `node`: os alvos atuais (`src/lib/utils/taskStatus.ts`,
 * `src/lib/utils/autosave.ts`) não tocam DOM/Svelte — são funções puras.
 * Se um teste futuro precisar de DOM, trocar para `environment: 'jsdom'`
 * (e adicionar `jsdom` como devDependency).
 *
 * Separado do `vite.config.ts` (SvelteKit) de propósito: rodar os testes não
 * deve arrastar o plugin do SvelteKit nem exigir `svelte-kit sync`.
 */
import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'node:url';

export default defineConfig({
	// alias manual (sem plugin do SvelteKit) para resolver imports `$lib/...` nos testes.
	resolve: {
		alias: {
			$lib: fileURLToPath(new URL('./src/lib', import.meta.url))
		}
	},
	test: {
		environment: 'node',
		include: ['src/**/*.{test,spec}.ts'],
		globals: false
	}
});
