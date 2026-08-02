// Registry de ícones de traço (stroke) das famílias de feedback — viewBox 24, fiel ao protótipo feedbacks.dc.html.
export interface FeedbackIconPathShape {
	type: 'path';
	d: string;
	strokeWidth?: number;
}

export interface FeedbackIconCircleShape {
	type: 'circle';
	cx: number;
	cy: number;
	r: number;
	fill?: string;
	stroke?: string;
	strokeWidth?: number;
}

export type FeedbackIconShape = FeedbackIconPathShape | FeedbackIconCircleShape;

export type FeedbackIconId =
	| 'check'
	| 'info'
	| 'alert'
	| 'x'
	| 'trash'
	| 'clock'
	| 'reopen'
	| 'unlink'
	| 'draft'
	| 'archive'
	| 'retry'
	| 'sync'
	| 'close'
	| 'back'
	| 'plug'
	| 'cloudoff';

export const FEEDBACK_ICONS: Record<FeedbackIconId, FeedbackIconShape[]> = {
	check: [{ type: 'path', d: 'M4.6 12.9 9.4 17.6 19.4 6.6', strokeWidth: 1.9 }],
	info: [
		{ type: 'circle', cx: 12, cy: 6.6, r: 1.35, fill: 'currentColor', stroke: 'none' },
		{ type: 'path', d: 'M12 10.8V18.2', strokeWidth: 1.9 }
	],
	alert: [
		{ type: 'path', d: 'M12 4.3 21 19.4H3Z' },
		{ type: 'path', d: 'M12 9.6v4.3', strokeWidth: 1.8 },
		{ type: 'circle', cx: 12, cy: 16.8, r: 1.05, fill: 'currentColor', stroke: 'none' }
	],
	x: [{ type: 'path', d: 'M6.4 6.4 17.6 17.6M17.6 6.4 6.4 17.6', strokeWidth: 1.9 }],
	trash: [
		{
			type: 'path',
			d: 'M4.4 7.3h15.2M9.4 7.3V5.1a.8.8 0 0 1 .8-.8h3.6a.8.8 0 0 1 .8.8v2.2'
		},
		{ type: 'path', d: 'M6.6 7.3 7.6 19.5a.9.9 0 0 0 .9.8h7a.9.9 0 0 0 .9-.8l1-12.2' },
		{ type: 'path', d: 'M10.3 10.9v5.6M13.7 10.9v5.6', strokeWidth: 1.5 }
	],
	clock: [
		{ type: 'circle', cx: 12, cy: 12, r: 8.1 },
		{ type: 'path', d: 'M12 6.9V12l3.4 2.1' }
	],
	reopen: [
		{ type: 'path', d: 'M4.4 5.6v5.3h5.3', strokeWidth: 1.8 },
		{ type: 'path', d: 'M4.9 10.4a7.7 7.7 0 1 1 1.4 6.6', strokeWidth: 1.8 }
	],
	unlink: [
		{
			type: 'path',
			d: 'M10.1 13.9 7.9 16.1a3.6 3.6 0 0 1-5.1-5.1L5 8.8M13.9 10.1l2.2-2.2a3.6 3.6 0 0 1 5.1 5.1L19 15.2'
		},
		{ type: 'path', d: 'M15.6 4.3v2.4M19.7 8.4h-2.4M4.3 15.6h2.4M8.4 19.7v-2.4', strokeWidth: 1.5 }
	],
	draft: [
		{ type: 'path', d: 'M6.2 4.4h7.2l4.4 4.4v10.8a.8.8 0 0 1-.8.8H6.2a.8.8 0 0 1-.8-.8V5.2a.8.8 0 0 1 .8-.8Z' },
		{ type: 'path', d: 'M13.4 4.4v4.4h4.4' },
		{ type: 'path', d: 'M8.6 12.6h6.4M8.6 15.8h4.2', strokeWidth: 1.5 }
	],
	archive: [
		{ type: 'path', d: 'M3.6 5.4h16.8v3.9H3.6Z' },
		{ type: 'path', d: 'M5.4 9.3v9.5a.8.8 0 0 0 .8.8h11.6a.8.8 0 0 0 .8-.8V9.3' },
		{ type: 'path', d: 'M10 13.1h4', strokeWidth: 1.6 }
	],
	retry: [
		{ type: 'path', d: 'M19.6 5.5v5.2h-5.2', strokeWidth: 1.8 },
		{ type: 'path', d: 'M19.1 10.2A7.7 7.7 0 1 0 17.7 17', strokeWidth: 1.8 }
	],
	sync: [
		{ type: 'path', d: 'M3.9 12a8.1 8.1 0 0 1 13.4-6.1M20.1 12a8.1 8.1 0 0 1-13.4 6.1', strokeWidth: 1.8 },
		{ type: 'path', d: 'M17.6 2.6v3.6h-3.6M6.4 21.4v-3.6h3.6', strokeWidth: 1.8 }
	],
	// No protótipo este é o único ícone em grade 20; reescalado 1.2× para a 24 do componente.
	close: [{ type: 'path', d: 'M7 7 17 17M17 7 7 17', strokeWidth: 2 }],
	back: [
		{ type: 'path', d: 'M10.4 5.4 3.9 12l6.5 6.6', strokeWidth: 1.8 },
		{ type: 'path', d: 'M3.9 12h16.2', strokeWidth: 1.8 }
	],
	plug: [
		{ type: 'path', d: 'M8.4 3.4v5.2M15.6 3.4v5.2' },
		{ type: 'path', d: 'M5.6 8.6h12.8v3a6.4 6.4 0 0 1-12.8 0Z' },
		{ type: 'path', d: 'M12 18v3' }
	],
	cloudoff: [
		{ type: 'path', d: 'M7.3 18.4h9.4a4.2 4.2 0 0 0 .9-8.3 6 6 0 0 0-9.2-3.6' },
		{ type: 'path', d: 'M6.2 9.1a4.7 4.7 0 0 0 1.1 9.3' },
		{ type: 'path', d: 'M3.6 3.6 20.4 20.4' }
	]
};
