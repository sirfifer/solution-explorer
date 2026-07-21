/// <reference types="vite/client" />

declare const __APP_VERSION__: string;
// Build-time maturity gate (card R3). False in a production build so guarded
// experimental code is dead-code-eliminated; true in an experimental build
// (VITE_EXPERIMENTAL_BUILD=1). See src/utils/channel.ts.
declare const __EXPERIMENTAL_BUILD__: boolean;
