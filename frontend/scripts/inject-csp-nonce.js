#!/usr/bin/env node
/*
 * Pos-build: garante que TODO <script> e <style> inline do index.html gerado
 * carregue nonce="%CSP_NONCE%", para casar com a CSP do Flask
 * (script-src 'self' 'nonce-{nonce}', app.py:55).
 *
 * O SvelteKit emite um <script> de bootstrap inline SEM nonce; sob a CSP estrita
 * ele seria bloqueado. routes/spa.py (ETAPA 2) serve este index via Jinja e
 * substitui %CSP_NONCE% pelo nonce real da request. Aqui apenas inserimos o
 * placeholder nas tags inline que ainda nao o tem.
 *
 * Idempotente: nao duplica nonce em tags que ja o possuem.
 */
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const indexPath = resolve(__dirname, '../../static/spa/index.html');

if (!existsSync(indexPath)) {
	console.error(`[inject-csp-nonce] index nao encontrado: ${indexPath}`);
	process.exit(1);
}

let html = readFileSync(indexPath, 'utf8');

// Apenas tags inline (<script>...</script> e <style>...</style>) sem atributo nonce.
// Tags com src/href (externas) nao precisam de nonce sob 'self'.
html = html.replace(/<script(?![^>]*\bnonce=)(?![^>]*\bsrc=)([^>]*)>/g, '<script$1 nonce="%CSP_NONCE%">');
html = html.replace(/<style(?![^>]*\bnonce=)([^>]*)>/g, '<style$1 nonce="%CSP_NONCE%">');

writeFileSync(indexPath, html, 'utf8');
console.log('[inject-csp-nonce] nonce placeholder aplicado em', indexPath);
