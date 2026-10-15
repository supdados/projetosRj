#!/usr/bin/env node
/*
 * Gate do `npm audit` (CI security-audit): reprova o build em qualquer advisory
 * high/critical, exceto os listados em audit-allowlist.json.
 *
 * O `npm audit` não tem mecanismo de exceção, e há advisory sem versão corrigida
 * (ex.: braces, que só entra pelo tailwindcss 3 no build). Sem exceção explícita
 * o job ficaria vermelho para sempre — e um job sempre vermelho deixa de alertar.
 * A exceção é por ID de advisory (GHSA), com motivo registrado: um advisory NOVO,
 * mesmo no mesmo pacote, continua reprovando.
 */
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';

const SEVERITY = { info: 0, low: 1, moderate: 2, high: 3, critical: 4 };
const THRESHOLD = SEVERITY.high;

const allowlist = JSON.parse(readFileSync(new URL('../audit-allowlist.json', import.meta.url), 'utf8'));
const allowed = new Map(allowlist.map((entry) => [entry.id, entry]));

let raw;
try {
	raw = execFileSync('npm', ['audit', '--json'], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
} catch (err) {
	// `npm audit` sai com 1 quando há achados; o relatório continua no stdout.
	raw = err.stdout;
}

let report;
try {
	report = JSON.parse(raw);
} catch {
	console.error('[audit-gate] saída do npm audit não é JSON:\n' + raw);
	process.exit(1);
}
if (report.error) {
	console.error('[audit-gate] npm audit falhou:', JSON.stringify(report.error));
	process.exit(1);
}

// Cada pacote vulnerável lista em `via` os advisories de origem (objetos) ou os
// pacotes por onde herdou a vulnerabilidade (strings). Só os objetos importam:
// deduplicados por URL, são o conjunto real de advisories da árvore.
const advisories = new Map();
for (const vuln of Object.values(report.vulnerabilities ?? {})) {
	for (const via of vuln.via) {
		if (typeof via === 'object') advisories.set(via.url, via);
	}
}

const blocking = [];
const accepted = new Set();
for (const adv of advisories.values()) {
	if (SEVERITY[adv.severity] < THRESHOLD) continue;
	const id = adv.url.split('/').pop();
	const line = `${adv.severity} ${id} ${adv.name}@${adv.range}: ${adv.title}`;
	if (allowed.has(id)) {
		accepted.add(id);
		console.log(`[audit-gate] aceito (audit-allowlist.json): ${line}`);
	} else {
		blocking.push(line);
	}
}

for (const id of allowed.keys()) {
	if (!accepted.has(id)) {
		console.log(`::warning::[audit-gate] ${id} não aparece mais no npm audit; remova-o de audit-allowlist.json.`);
	}
}

if (blocking.length) {
	console.error(`[audit-gate] ${blocking.length} advisory(s) high/critical sem exceção:`);
	for (const line of blocking) console.error(`  - ${line}`);
	process.exit(1);
}
console.log('[audit-gate] nenhum advisory high/critical fora da allowlist.');
