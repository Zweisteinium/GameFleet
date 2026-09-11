import type { Api } from './Api'

/** Union of all live-info shapes the backend can return, derived from the generated client so it never drifts. */
export type LiveServerInfo = Awaited<ReturnType<Api<unknown>['liveInfo']['getAllServersLiveInfo']>>['data'][string]
