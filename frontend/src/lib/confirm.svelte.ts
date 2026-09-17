/**
 * In-app replacement for window.confirm(): `await confirmDialog({...})` resolves to true or false.
 * The dialog itself is rendered once by ConfirmDialog.svelte in the root layout.
 */
export interface ConfirmOptions {
	title: string;
	message: string;
	/** Extra line in muted text, for consequences and side notes. */
	note?: string;
	confirmLabel?: string;
	/** "danger" for actions that remove something or disconnect players. */
	tone?: 'primary' | 'danger';
}

export const pendingConfirm = $state<{ options: ConfirmOptions | null }>({ options: null });

let settle: ((answer: boolean) => void) | null = null;

export function confirmDialog(options: ConfirmOptions): Promise<boolean> {
	settle?.(false); // a second question replaces an unanswered one
	pendingConfirm.options = options;
	return new Promise((resolve) => (settle = resolve));
}

export function answerConfirm(answer: boolean) {
	pendingConfirm.options = null;
	settle?.(answer);
	settle = null;
}
