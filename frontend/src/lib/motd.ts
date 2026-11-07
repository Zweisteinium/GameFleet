/**
 * Minecraft formatting codes (§ + one character) for the MOTD editor. A colour code or §r ends every style
 * before it; style codes add up until then.
 */

export const CODE = /§[0-9a-fk-or]/gi;

export interface Format {
	colour: string | null;
	styles: string[];
}

/** An edit: replace text[from, to) with `insert`, then select [select[0], select[1]). */
export interface Edit {
	from: number;
	to: number;
	insert: string;
	select: [number, number];
}

const isReset = (code: string) => /^[0-9a-fr]$/i.test(code);

/** The formatting in effect at `pos`. */
export function formatAt(text: string, pos: number): Format {
	const format: Format = { colour: null, styles: [] };
	for (const match of text.slice(0, pos).matchAll(CODE)) {
		const code = match[0][1].toLowerCase();
		if (isReset(code)) {
			format.colour = code === 'r' ? null : code;
			format.styles = [];
		} else if (!format.styles.includes(code)) format.styles.push(code);
	}
	return format;
}

const same = (a: Format, b: Format) =>
	a.colour === b.colour &&
	a.styles.length === b.styles.length &&
	a.styles.every((s) => b.styles.includes(s));

/** The codes that set exactly this formatting: a colour or reset first, since both end the styles. */
const codes = (f: Format) => `§${f.colour ?? 'r'}` + f.styles.map((s) => `§${s}`).join('');

/** Drop codes that have no effect: in a run of codes, everything before the last colour or reset. */
export function tidy(text: string): string {
	return text.replace(/(?:§[0-9a-fk-or])+/gi, (run) => {
		const list = run.match(CODE)!.map((c) => c.toLowerCase());
		let from = 0;
		list.forEach((c, i) => {
			if (isReset(c[1])) from = i;
		});
		return [...new Set(list.slice(from))].join('');
	});
}

/**
 * Apply a code. Without a selection it goes in at the cursor. With one, only the selected text changes:
 * the code goes before it, and after it the formatting that was in effect there before comes back. A style
 * that is already on for the selection is turned off; §r removes all formatting from it.
 */
export function applyCode(text: string, start: number, end: number, code: string): Edit {
	code = code.toLowerCase();
	if (start === end)
		return { from: start, to: end, insert: `§${code}`, select: [start + 2, start + 2] };
	const before = formatAt(text, start);
	let inner = text.slice(start, end);
	let prefix: string;
	if (code === 'r') {
		prefix = '§r';
		inner = inner.replace(CODE, '');
	} else if (isReset(code)) {
		prefix = `§${code}` + before.styles.map((s) => `§${s}`).join('');
		inner = inner.replace(/§[0-9a-fr]/gi, '');
	} else if (before.styles.includes(code)) {
		prefix = codes({ ...before, styles: before.styles.filter((s) => s !== code) });
		inner = inner.replace(new RegExp(`§${code}`, 'gi'), '');
	} else {
		prefix = `§${code}`;
		// A colour inside the selection would end the style there: repeat it after each one.
		inner = inner
			.replace(new RegExp(`§${code}`, 'gi'), '')
			.replace(/§[0-9a-fr]/gi, (c) => c + `§${code}`);
	}
	// Take in the codes right around the selection, so they are tidied together.
	let from = start;
	while (from >= 2 && /^§[0-9a-fk-or]$/i.test(text.slice(from - 2, from))) from -= 2;
	let to = end;
	while (/^§[0-9a-fk-or]/i.test(text.slice(to, to + 2))) to += 2;
	// Codes at the edges of the selection join those runs; the selection keeps just the text.
	const lead = inner.match(/^(?:§[0-9a-fk-or])+/i)?.[0] ?? '';
	const trail = inner.slice(lead.length).match(/(?:§[0-9a-fk-or])+$/i)?.[0] ?? '';
	inner = inner.slice(lead.length, inner.length - trail.length);
	const head = tidy(text.slice(from, start) + prefix + lead);
	const after = formatAt(text, end);
	const done = text.slice(0, from) + head + inner + trail;
	const changed = formatAt(done, done.length);
	// Nothing follows: codes at the very end do nothing.
	const tail =
		to === text.length
			? ''
			: tidy(trail + (same(after, changed) ? '' : codes(after)) + text.slice(end, to));
	const at = from + head.length;
	return { from, to, insert: head + inner + tail, select: [at, at + inner.length] };
}

/** Remove every code from text[start, end), or from all of it when nothing is selected. */
export function clearCodes(text: string, start: number, end: number): Edit {
	if (start === end) [start, end] = [0, text.length];
	const plain = text.slice(start, end).replace(CODE, '');
	return { from: start, to: end, insert: plain, select: [start, start + plain.length] };
}
