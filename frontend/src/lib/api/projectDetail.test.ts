import { expect, it, vi } from 'vitest';

vi.mock('./client', () => ({ get: vi.fn(), post: vi.fn(), del: vi.fn() }));

import { get } from './client';
import { fetchProjectDetail, peekProjectDetail } from './projectDetail';
import type { ProjectDetailData } from '$lib/types/projectDetail';

class DeferredProject {
	resolve!: (value: ProjectDetailData) => void;
	promise = new Promise<ProjectDetailData>((resolve) => { this.resolve = resolve; });
}

it('resposta cancelada não sobrescreve o cache atualizado ao retornar ao mesmo projeto', async () => {
	const first = new DeferredProject();
	const old = { project: { id: 19, titulo: 'Antigo' } } as unknown as ProjectDetailData;
	const newest = { project: { id: 19, titulo: 'Atual' } } as unknown as ProjectDetailData;
	vi.mocked(get).mockReturnValueOnce(first.promise).mockResolvedValueOnce(newest);
	const controller = new AbortController();
	const oldRequest = fetchProjectDetail(19, controller.signal);
	controller.abort();
	await fetchProjectDetail(19);
	first.resolve(old);
	await oldRequest;
	expect(peekProjectDetail(19)).toBe(newest);
});
