/**
 * Browser-level hygiene collection for the M4G-D acceptance matrix.
 *
 * ADR-024 §11 makes the per-variant browser gates blocking, and a page
 * that renders correctly while throwing in the console is not accepted.
 * A watcher is attached before the first navigation and asserted after
 * the last, so nothing that happened in between can be missed.
 */

import { expect, type Page } from '@playwright/test';

export interface PageProblems {
  readonly consoleErrors: string[];
  readonly consoleWarnings: string[];
  readonly pageErrors: string[];
  readonly failedRequests: string[];
  readonly serverErrors: string[];
  readonly clientErrors: string[];
  /**
   * Discard everything recorded so far.
   *
   * Used to scope an assertion to the navigation under test rather than
   * to a preceding step whose behaviour is another spec's subject — most
   * concretely the Control Center's unauthenticated bootstrap, where the
   * session probe legitimately answers 401 before anyone has signed in.
   * Clearing at a stated point is honest; a standing exclusion for
   * `401 /auth/session` would also hide a real regression during
   * authenticated use, so it is deliberately not done that way.
   */
  clear(): void;
}

/**
 * The one deliberate exclusion, stated rather than hidden.
 *
 * Chromium speculatively requests `/favicon.ico` on every navigation to a
 * new origin. No storefront document references it and no product code
 * issues it, so its 404 is browser behaviour rather than an application
 * defect — but it is a real 404, so it is excluded by exact path here and
 * reported in the acceptance record instead of being quietly dropped.
 */
const SPECULATIVE_BROWSER_PATHS = ['/favicon.ico'];

function isSpeculative(url: string): boolean {
  try {
    return SPECULATIVE_BROWSER_PATHS.includes(new URL(url).pathname);
  } catch {
    return false;
  }
}

/** Start recording; call before the first navigation. */
export function watchPage(page: Page): PageProblems {
  const problems: PageProblems = {
    consoleErrors: [],
    consoleWarnings: [],
    pageErrors: [],
    failedRequests: [],
    serverErrors: [],
    clientErrors: [],
    clear() {
      for (const bucket of [
        problems.consoleErrors,
        problems.consoleWarnings,
        problems.pageErrors,
        problems.failedRequests,
        problems.serverErrors,
        problems.clientErrors,
      ]) {
        bucket.length = 0;
      }
    },
  };
  page.on('console', (message) => {
    // The originating URL is carried alongside the text so a message can
    // be attributed to the resource that caused it. A blanket "ignore
    // console errors" would hide real defects; attribution lets a test
    // that deliberately refuses one asset exclude exactly that asset.
    const url = message.location().url;
    const entry = url === '' ? message.text() : `${message.text()} @ ${url}`;
    if (message.type() === 'error') {
      problems.consoleErrors.push(entry);
    } else if (message.type() === 'warning') {
      problems.consoleWarnings.push(entry);
    }
  });
  page.on('pageerror', (error) => {
    problems.pageErrors.push(error.message);
  });
  page.on('requestfailed', (request) => {
    if (isSpeculative(request.url())) {
      return;
    }
    const failure = request.failure();
    problems.failedRequests.push(
      `${request.method()} ${request.url()} — ${failure?.errorText ?? 'unknown'}`,
    );
  });
  page.on('response', (response) => {
    const status = response.status();
    if (status >= 500) {
      problems.serverErrors.push(`${String(status)} ${response.url()}`);
    } else if (status >= 400 && !isSpeculative(response.url())) {
      problems.clientErrors.push(`${String(status)} ${response.url()}`);
    }
  });
  return problems;
}

/**
 * Assert the page stayed clean.
 *
 * Warnings are collected and surfaced in the failure message but are not
 * themselves blocking: ADR-024 §11 does not make them a gate, and turning
 * one into a gate here would be inventing a bar the contract does not
 * state. Errors, uncaught exceptions, transport failures, and any 4xx/5xx
 * the browser genuinely asked for are all blocking.
 */
export function expectPageClean(problems: PageProblems, where: string): void {
  expect(
    {
      consoleErrors: problems.consoleErrors,
      pageErrors: problems.pageErrors,
      failedRequests: problems.failedRequests,
      serverErrors: problems.serverErrors,
      clientErrors: problems.clientErrors,
    },
    `browser problems at ${where} (warnings seen: ${JSON.stringify(problems.consoleWarnings)})`,
  ).toEqual({
    consoleErrors: [],
    pageErrors: [],
    failedRequests: [],
    serverErrors: [],
    clientErrors: [],
  });
}
