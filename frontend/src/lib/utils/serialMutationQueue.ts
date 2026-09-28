/** Mantém a ordem de envio das escritas, inclusive quando uma delas falha. */
export function createSerialMutationQueue(): { run<T>(operation: () => Promise<T>): Promise<T> } {
	let tail: Promise<void> | null = null;
	return {
		run<T>(operation: () => Promise<T>): Promise<T> {
			const result = tail ? tail.then(operation) : operation();
			const current = result.then(() => {}, () => {});
			tail = current;
			void current.then(() => { if (tail === current) tail = null; });
			return result;
		}
	};
}
