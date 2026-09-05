import '@testing-library/jest-dom/vitest';
import type { AxeMatchers } from 'vitest-axe/matchers';
import * as matchers from 'vitest-axe/matchers';
import { expect } from 'vitest';

/* eslint-disable @typescript-eslint/no-empty-object-type, @typescript-eslint/no-unused-vars */
declare module 'vitest' {
  interface Assertion<T = any> extends AxeMatchers {}
  interface AsymmetricMatchersContaining extends AxeMatchers {}
}
/* eslint-enable @typescript-eslint/no-empty-object-type, @typescript-eslint/no-unused-vars */

expect.extend(matchers);

// jsdom lacks these; components guard on them for reduced-motion and streaming.
if (!window.matchMedia) {
  window.matchMedia = ((q: string) => ({
    matches: false, media: q, onchange: null,
    addListener: () => {}, removeListener: () => {},
    addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}
