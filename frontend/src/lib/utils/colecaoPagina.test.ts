/**
 * Ligações da página `/colecoes/<id>` lidas do FONTE (sem DOM — o vitest roda
 * em `node`), no molde de `projectPageRace.test.ts`: o handler que a página
 * passa a cada componente é avaliado num contexto isolado com `load` e
 * `loadCronograma` espionados.
 *
 * Regressões cobertas:
 *   - revogar/rebaixar no modal de compartilhar PODA itens, mas `onChanged`
 *     só recarregava a tabela — o Gantt seguia mostrando os projetos que
 *     saíram até navegar;
 *   - convite pendente para quem JÁ participa (`.../projetos` 200) não tinha
 *     onde ser respondido na página.
 */
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';
import { describe, expect, it, vi } from 'vitest';

const FONTE = readFileSync(
	new URL('../../routes/(app)/colecoes/[id]/+page.svelte', import.meta.url),
	'utf8'
);
const SCRIPT = FONTE.slice(FONTE.indexOf('>') + 1, FONTE.indexOf('</script>'));
const MARCACAO = FONTE.slice(FONTE.indexOf('</script>'));

/** Texto da tag `<Componente ... />` na marcação da página (falha se não houver). */
function tagDo(componente: string): string {
	const inicio = MARCACAO.indexOf(`<${componente}`);
	if (inicio < 0) throw new Error(`<${componente}> não aparece na página`);
	return MARCACAO.slice(inicio, MARCACAO.indexOf('/>', inicio));
}

/** Expressão de `nome={...}` numa tag, com chaves aninhadas balanceadas. */
function expressaoDoAtributo(tag: string, nome: string): string {
	const abre = tag.indexOf(`${nome}={`);
	if (abre < 0) throw new Error(`atributo ${nome} ausente`);
	let profundidade = 0;
	for (let i = abre + nome.length + 1; i < tag.length; i++) {
		if (tag[i] === '{') profundidade++;
		if (tag[i] === '}' && --profundidade === 0) return tag.slice(abre + nome.length + 2, i);
	}
	throw new Error(`atributo ${nome} sem fecha-chaves`);
}

/** Funções declaradas no `<script>` da página, transpiladas para JS. */
function funcoesDaPagina(nomes: readonly string[]): string {
	const parsed = ts.createSourceFile('page.ts', SCRIPT, ts.ScriptTarget.Latest, true);
	const alvo = parsed.statements.filter(
		(node) => ts.isFunctionDeclaration(node) && node.name && nomes.includes(node.name.text)
	);
	return ts.transpileModule(alvo.map((node) => node.getText(parsed)).join('\n'), {
		compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.None }
	}).outputText;
}

/** Chama o handler `expressao` da marcação e diz o que ele recarregou. */
function recargasDo(expressao: string): { load: number; loadCronograma: number } {
	const contexto = {
		load: vi.fn(async () => undefined),
		loadCronograma: vi.fn(async () => undefined),
		handler: null as null | (() => void)
	};
	runInNewContext(`${funcoesDaPagina(['recarregarTudo'])}\nhandler = ${expressao};`, contexto);
	contexto.handler?.();
	return {
		load: contexto.load.mock.calls.length,
		loadCronograma: contexto.loadCronograma.mock.calls.length
	};
}

describe('/colecoes/<id>: o que cada componente recarrega', () => {
	it('mudança no modal de compartilhar recarrega a tabela E o cronograma', () => {
		const onChanged = expressaoDoAtributo(tagDo('CompartilharColecaoModal'), 'onChanged');
		expect(recargasDo(onChanged)).toEqual({ load: 1, loadCronograma: 1 });
	});

	it('adicionar projetos segue recarregando as duas coisas', () => {
		const onAdicionados = expressaoDoAtributo(tagDo('ColecaoAdicionarProjetosModal'), 'onAdicionados');
		expect(recargasDo(onAdicionados)).toEqual({ load: 1, loadCronograma: 1 });
	});
});

describe('/colecoes/<id>: convite de quem já participa', () => {
	it('o banner aparece na página da coleção ABERTA (não só no estado do 404)', () => {
		const tag = tagDo('ColecaoConviteExtraBanner');
		expect(expressaoDoAtributo(tag, 'papelAtual')).toBe('colecao.papel');
		expect(tag).toContain('{collectionId}');
		const ramoAberto = MARCACAO.slice(MARCACAO.indexOf('{:else if colecao}'));
		expect(ramoAberto).toContain('<ColecaoConviteExtraBanner');
	});

	it('aceitar pelo banner recarrega tudo (o papel sobe e o cronograma acompanha)', () => {
		const onAceito = expressaoDoAtributo(tagDo('ColecaoConviteExtraBanner'), 'onAceito');
		expect(recargasDo(onAceito)).toEqual({ load: 1, loadCronograma: 1 });
	});
});

describe('itens órfãos (de quem já não é editor) chegam às confirmações', () => {
	it('"Sair da coleção" conta os órfãos do payload de `.../projetos`', () => {
		expect(SCRIPT).toMatch(/textoDeSaida\([^)]*data\.itens_orfaos/);
	});

	it('revogar e rebaixar no modal usam os órfãos de `.../compartilhamentos`', () => {
		const modal = readFileSync(
			new URL('../components/CompartilharColecaoModal.svelte', import.meta.url),
			'utf8'
		);
		expect(modal).toMatch(/itensOrfaos = dados\.itens_orfaos/);
		expect(modal).toMatch(/textoDeRevogacao\([^;]*itensOrfaos\)/);
		expect(modal).toMatch(/textoDeRebaixamento\([^;]*itensOrfaos\)/);
	});
});
