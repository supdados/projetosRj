/** Identidade da navegação, independente do ID (cobre A → B → A). */
export interface ProjectRequestContext {
	readonly projectId: number;
	isCurrent(): boolean;
}

export interface ProjectReadContext {
	readonly signal: AbortSignal;
	isCurrent(): boolean;
}

export interface ProjectRequestScope {
	capture(): ProjectRequestContext;
	startRead(context: ProjectRequestContext): ProjectReadContext;
	dispose(): void;
}

/** Contextos isolam mutações; cada leitura ainda tem seu próprio cancelamento. */
export function createProjectRequestScope(currentProjectId: () => number): ProjectRequestScope {
	let generation = 0;
	let active: ProjectRequestContext | null = null;
	let reading: AbortController | null = null;
	let disposed = false;

	function capture(): ProjectRequestContext {
		const projectId = currentProjectId();
		if (active && Object.is(active.projectId, projectId)) return active;
		reading?.abort();
		const token = ++generation;
		active = {
			projectId,
			isCurrent: () => !disposed && token === generation && Object.is(currentProjectId(), projectId)
		};
		return active;
	}

	function startRead(context: ProjectRequestContext): ProjectReadContext {
		const controller = new AbortController();
		if (context.isCurrent()) {
			reading?.abort();
			reading = controller;
		} else {
			controller.abort();
		}
		return {
			signal: controller.signal,
			isCurrent: () => context.isCurrent() && !controller.signal.aborted
		};
	}

	function dispose(): void {
		disposed = true;
		generation++;
		reading?.abort();
	}

	return { capture, startRead, dispose };
}
