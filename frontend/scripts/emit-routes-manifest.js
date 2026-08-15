#!/usr/bin/env node
/*
 * Pos-build: emite static/spa/routes.json a partir dos fontes
 * frontend/src/routes/(app)/** — a fonte da verdade do matcher da SPA.
 *
 * routes/spa.py carrega esse manifesto para decidir quais paths o catch-all
 * serve; listas mantidas a mao no Python morreram (uma pagina nova entra no
 * matcher automaticamente no proximo build). Segmentos [param] viram \d+ —
 * todos os params atuais sao ids numericos, e restringir a \d+ mantem paths
 * como /colecoes/abc em 404.
 */
import { readdirSync, writeFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const appRoutesDir = resolve(__dirname, '../src/routes/(app)');
const manifestPath = resolve(__dirname, '../../static/spa/routes.json');

if (!existsSync(appRoutesDir)) {
	console.error(`[emit-routes-manifest] diretorio nao encontrado: ${appRoutesDir}`);
	process.exit(1);
}

/** Coleta recursivamente os caminhos (relativos) dos diretorios com +page.svelte. */
function collectPagePaths(dir, prefix = '') {
	const paths = [];
	for (const entry of readdirSync(dir, { withFileTypes: true })) {
		if (entry.isFile() && entry.name === '+page.svelte' && prefix) {
			paths.push(prefix);
		}
		if (!entry.isDirectory()) continue;
		// Grupos (parenteses) nao aparecem na URL.
		const segment = /^\(.*\)$/.test(entry.name) ? '' : entry.name;
		const next = segment ? (prefix ? `${prefix}/${segment}` : segment) : prefix;
		paths.push(...collectPagePaths(join(dir, entry.name), next));
	}
	return paths;
}

const exact = [];
const dynamic = [];
for (const path of collectPagePaths(appRoutesDir).sort()) {
	if (path.includes('[')) {
		dynamic.push(path.replace(/\[[^\]]+\]/g, '\\d+'));
	} else {
		exact.push(path);
	}
}

writeFileSync(manifestPath, JSON.stringify({ exact, dynamic }, null, '\t') + '\n', 'utf8');
console.log(
	`[emit-routes-manifest] ${exact.length} exatos + ${dynamic.length} dinamicos -> ${manifestPath}`
);
