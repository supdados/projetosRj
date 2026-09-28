/** Executa os handlers reais da página sem DOM/navegador, com respostas controladas. */
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';
import { describe, expect, it, vi } from 'vitest';
import type { ProjectDetailData, ProjectInlineResult } from '$lib/types/projectDetail';
import { createProjectRequestScope } from './projectRequestScope';

class Deferred<T> {
	resolve!: (value: T) => void;
	reject!: (reason: Error) => void;
	promise = new Promise<T>((resolve, reject) => {
		this.resolve = resolve;
		this.reject = reject;
	});
}

function projectData(id: number, canEdit = true): ProjectDetailData {
	return { project: { id, titulo: `Projeto ${id}` }, permissions: { can_edit: canEdit }, etapas: [] } as unknown as ProjectDetailData;
}

function pageHarness() {
	const source = readFileSync(new URL('../../routes/(app)/projetos/[id]/+page.svelte', import.meta.url), 'utf8');
	const script = source.slice(source.indexOf('>') + 1, source.indexOf('</script>'));
	const parsed = ts.createSourceFile('page.ts', script, ts.ScriptTarget.Latest, true);
	const selected = new Set([
		'load', 'refresh', 'saveProjectField', 'hasCurrentProjectData',
		'saveOrgao', 'saveSeiProcesses', 'saveCustomLinks', 'saveEegg', 'onReopenProject'
	]);
	const handlers = parsed.statements.filter((node) => ts.isFunctionDeclaration(node) && node.name && selected.has(node.name.text));
	const compiled = ts.transpileModule(handlers.map((node) => node.getText(parsed)).join('\n'), {
		compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.None }
	}).outputText;
	const state = {
		projectId: 1, data: null as ProjectDetailData | null, loadState: 'loading',
		errorMessage: '', errorKind: 'generic',
		fetchProjectDetail: vi.fn<(id: number, signal?: AbortSignal) => Promise<ProjectDetailData>>(),
		updateProjectInline: vi.fn<(id: number, fields: object) => Promise<ProjectInlineResult>>(),
		peekProjectDetail: vi.fn(() => null), setProjectFieldState: vi.fn(),
		reopenInFlight: false, isFinalizado: true, canEdit: true,
		confirmAction: vi.fn<() => Promise<boolean>>(),
		saveProjectGoals: vi.fn<(id: number, fields: object) => Promise<ProjectInlineResult>>(),
		ApiClientError: Error,
		isUnauthenticated: () => false, accessErrorKind: () => 'generic',
		accessErrorMessage: () => 'erro', MSG_PROJETO_INACESSIVEL: 'inacessível',
		messageOf: () => 'erro', flash: { danger: vi.fn(), success: vi.fn() },
		flow: {} as {
			load(): Promise<void>; refresh(): Promise<void>;
			saveProjectField(field: string, value: string): Promise<void>;
			saveOrgao(id: number): Promise<void>; saveSeiProcesses(values: string[]): Promise<void>;
			saveCustomLinks(values: { label: string; url: string }[], key: string): Promise<boolean>;
			onReopenProject(): Promise<void>;
		}
	};
	const harness = Object.assign(state, { projectRequests: createProjectRequestScope(() => state.projectId) });
	runInNewContext(`${compiled}\nflow = { load, refresh, saveProjectField, saveOrgao, saveSeiProcesses, saveCustomLinks, onReopenProject };`, harness);
	return harness;
}

describe('P2-08: respostas de outro projeto', () => {
	it('ID inválido na rota termina em erro em vez de ficar carregando', async () => {
		const state = pageHarness();
		state.projectId = Number.NaN;
		state.fetchProjectDetail.mockRejectedValueOnce(new Error('projeto inexistente'));
		await state.flow.load();
		expect(state.loadState).toBe('error');
	});

	it.each(['load', 'refresh'] as const)('%s de A chegando após B não troca dados nem permissões', async (operation) => {
		const state = pageHarness();
		const previous = new Deferred<ProjectDetailData>();
		state.fetchProjectDetail.mockReturnValueOnce(previous.promise).mockResolvedValueOnce(projectData(2, false));
		state.data = projectData(1);
		const loadingA = state.flow[operation]();
		state.projectId = 2;
		await state.flow.load();
		expect(state.fetchProjectDetail.mock.calls[0][1]?.aborted).toBe(true);
		previous.resolve(projectData(1, true));
		await loadingA;
		expect(state.data?.project.id).toBe(2);
		expect(state.data?.permissions.can_edit).toBe(false);
	});

	it('save de A chegando após B não preenche os campos do projeto B', async () => {
		const state = pageHarness();
		const previous = new Deferred<ProjectInlineResult>();
		state.updateProjectInline.mockReturnValueOnce(previous.promise);
		state.data = projectData(1);
		const savingA = state.flow.saveProjectField('titulo', 'Título A');
		state.projectId = 2;
		state.fetchProjectDetail.mockResolvedValueOnce(projectData(2));
		await state.flow.load();
		previous.resolve({ project: projectData(1).project, changed: ['titulo'] });
		await savingA;
		expect(state.data?.project.id).toBe(2);
		expect(state.data?.project.titulo).toBe('Projeto 2');
		state.updateProjectInline.mockResolvedValueOnce({ project: projectData(2).project, changed: ['titulo'] });
		await state.flow.saveProjectField('titulo', 'Título B');
		expect(state.updateProjectInline).toHaveBeenLastCalledWith(2, { titulo: 'Título B' });
	});

	it('não envia edição enquanto os dados não correspondem à rota', async () => {
		const state = pageHarness();
		state.data = projectData(1);
		state.projectId = 2;
		await state.flow.saveProjectField('titulo', 'Título A');
		expect(state.updateProjectInline).not.toHaveBeenCalled();
	});

	it('A → B → A invalida a primeira resposta de A', async () => {
		const state = pageHarness();
		const previous = new Deferred<ProjectDetailData>();
		state.fetchProjectDetail.mockReturnValueOnce(previous.promise);
		const first = state.flow.load();
		state.projectId = 2;
		state.fetchProjectDetail.mockResolvedValueOnce(projectData(2));
		await state.flow.load();
		state.projectId = 1;
		const newest = projectData(1);
		newest.project.titulo = 'A atual';
		state.fetchProjectDetail.mockResolvedValueOnce(newest);
		await state.flow.load();
		previous.resolve(projectData(1));
		await first;
		expect(state.data?.project.titulo).toBe('A atual');
	});

	it.each(['load', 'refresh', 'save'] as const)('erro antigo de %s não altera a nova tela', async (operation) => {
		const state = pageHarness();
		const previous = new Deferred<ProjectDetailData & ProjectInlineResult>();
		state.data = projectData(1);
		state.fetchProjectDetail.mockReturnValueOnce(previous.promise);
		state.updateProjectInline.mockReturnValueOnce(previous.promise);
		const first = operation === 'save' ? state.flow.saveProjectField('titulo', 'A') : state.flow[operation]();
		state.projectId = 2;
		state.fetchProjectDetail.mockReset().mockResolvedValueOnce(projectData(2));
		await state.flow.load();
		state.setProjectFieldState.mockClear();
		previous.reject(new Error('falha de A'));
		await first;
		expect(state.data?.project.id).toBe(2);
		expect(state.errorMessage).toBe('');
		expect(state.setProjectFieldState).not.toHaveBeenCalled();
		expect(state.flash.danger).not.toHaveBeenCalled();
	});

	it('refresh mais recente substitui load sem deixar loading preso', async () => {
		const state = pageHarness();
		const previous = new Deferred<ProjectDetailData>();
		state.fetchProjectDetail.mockReturnValueOnce(previous.promise).mockResolvedValueOnce(projectData(1));
		const first = state.flow.load();
		await state.flow.refresh();
		previous.reject(new Error('leitura cancelada'));
		await first;
		expect(state.loadState).toBe('ready');
		expect(state.data?.project.id).toBe(1);
	});

	it('confirmação do projeto A não reabre o projeto B após navegar', async () => {
		const state = pageHarness();
		state.data = projectData(1);
		const confirmation = new Deferred<boolean>();
		state.confirmAction.mockReturnValueOnce(confirmation.promise);
		const first = state.flow.onReopenProject();
		state.projectId = 2;
		state.fetchProjectDetail.mockResolvedValueOnce(projectData(2));
		await state.flow.load();
		confirmation.resolve(true);
		await first;
		expect(state.updateProjectInline).not.toHaveBeenCalled();
	});

	it.each(['orgao', 'sei', 'links'] as const)('save de %s também preserva a identidade do projeto', async (field) => {
		const state = pageHarness();
		state.data = projectData(1);
		const previous = new Deferred<ProjectInlineResult>();
		state.updateProjectInline.mockReturnValueOnce(previous.promise);
		const first = field === 'orgao' ? state.flow.saveOrgao(3)
			: field === 'sei' ? state.flow.saveSeiProcesses(['SEI-123'])
			: state.flow.saveCustomLinks([{ label: 'A', url: 'https://example.com/a' }], 'link');
		state.projectId = 2;
		state.fetchProjectDetail.mockResolvedValueOnce(projectData(2));
		await state.flow.load();
		previous.resolve({ project: projectData(1).project, changed: [field] });
		await first;
		expect(state.data?.project.id).toBe(2);
	});

	it('desmontar aborta a leitura e ignora seu resultado', async () => {
		const state = pageHarness();
		const previous = new Deferred<ProjectDetailData>();
		state.fetchProjectDetail.mockReturnValueOnce(previous.promise);
		const first = state.flow.load();
		state.projectRequests.dispose();
		previous.resolve(projectData(1));
		await first;
		expect(state.data).toBeNull();
		expect(state.fetchProjectDetail.mock.calls[0][1]?.aborted).toBe(true);
	});
});
