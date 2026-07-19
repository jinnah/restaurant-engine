// The single E2E lifecycle owner (M2F, ADR-016): ports, database,
// seeding, servers, Playwright, and guaranteed cleanup live here, in one
// auditable sequence. Playwright's webServer/globalSetup/globalTeardown
// are deliberately unused — two lifecycle owners is how databases leak.
//
// This module is pure orchestration logic over injectable process/net
// primitives so every failure path is testable without launching the
// real stack (see orchestrator.test.mjs). run-e2e.mjs wires real deps.

export const E2E_DATABASE_NAME = 'restaurant_engine_e2e';
// Constructed here, never inherited: an external DATABASE_URL cannot
// choose the target. The reset script additionally hard-refuses any
// database name except the literal above.
export const E2E_DATABASE_URL =
  'postgresql+psycopg://restaurant_dev:restaurant_dev_only@127.0.0.1:5433/' +
  E2E_DATABASE_NAME;

export const BACKEND_PORT = 8100;
export const UI_PORT = 5273;
export const UI_ORIGIN = `http://localhost:${UI_PORT}`;
export const BACKEND_READY_URLS = [
  `http://127.0.0.1:${BACKEND_PORT}/health/ready`,
];
// Vite binds whichever loopback family `localhost` resolves to (the
// M1C ::1 gotcha), and Node's fetch may try the other one — poll both
// literals; the browser resolves localhost across families itself.
export const UI_READY_URLS = [
  `http://127.0.0.1:${UI_PORT}/`,
  `http://[::1]:${UI_PORT}/`,
];
export const READY_TIMEOUT_MS = 120_000;

// Synthetic, E2E-only credentials for a database that is dropped after
// every run. The password travels exclusively via stdin and child env —
// never argv, never logged.
export const ADMIN_EMAIL = 'e2e.admin@e2e.example';
export const ADMIN_DISPLAY_NAME = 'E2E Platform Admin';
export const ADMIN_PASSWORD = 'e2e-only synthetic admin pw 4417!';

/** Distinct nonzero status when tests passed but cleanup failed. */
export const CLEANUP_FAILED_EXIT = 3;
/** Conventional status after SIGINT/SIGTERM-initiated cleanup. */
export const SIGNAL_EXIT = 130;

export function resetArgv(mode) {
  return [
    'uv',
    'run',
    '--directory',
    'backend',
    'python',
    '-m',
    'scripts.reset_e2e_database',
    mode,
  ];
}

export const BOOTSTRAP_ARGV = [
  'uv',
  'run',
  '--directory',
  'backend',
  'python',
  '-m',
  'scripts.create_platform_admin',
  '--email',
  ADMIN_EMAIL,
  '--display-name',
  ADMIN_DISPLAY_NAME,
  '--password-stdin',
];

export const BACKEND_ARGV = [
  'uv',
  'run',
  '--directory',
  'backend',
  'uvicorn',
  'app.main:create_app',
  '--factory',
  '--port',
  String(BACKEND_PORT),
];

/** Vite argv, given the entry-resolved node executable and vite script. */
export function buildUiArgv(nodeExecPath, viteScriptPath) {
  return [
    nodeExecPath,
    viteScriptPath,
    '--port',
    String(UI_PORT),
    '--strictPort',
  ];
}

function messageOf(error) {
  return error instanceof Error ? error.message : String(error);
}

/**
 * @param deps injectable primitives:
 *   checkPortFree(port) -> Promise<boolean>
 *   runCommand(argv, {env, input}) -> Promise<exit code>   (foreground step)
 *   spawnChild(name, argv, {env}) -> handle                 (tracked server)
 *   killChild(handle) -> Promise<void>                      (bounded stop)
 *   pollReady(urls, timeoutMs) -> Promise<boolean>  (any-of readiness)
 *   runTests(extraArgs, env) -> Promise<exit code>
 *   uiArgv -> string[]  (entry-resolved: node + vite script + port args)
 *   uiCwd -> string     (the control-center app directory)
 *   log(text), logError(text)
 */
export function createOrchestrator(deps) {
  const {
    checkPortFree,
    runCommand,
    spawnChild,
    killChild,
    pollReady,
    runTests,
    log,
    logError,
  } = deps;

  // The kill scope is exactly the children this run started — never a
  // port sweep, never a process-name match.
  const children = [];
  let cleanupStarted = false;
  let cleanupFailed = false;

  // Cleanup exists (and is registered by the entry's signal handlers)
  // before any database mutation begins, so a failure in creation,
  // migration, bootstrap, server startup, tests, or artifact writing
  // all funnel through this one path. It runs at most once.
  async function cleanup() {
    if (cleanupStarted) {
      return cleanupFailed;
    }
    cleanupStarted = true;
    for (const handle of [...children].reverse()) {
      try {
        await killChild(handle);
        log(`cleanup: stopped ${handle.name}`);
      } catch (error) {
        cleanupFailed = true;
        logError(`cleanup: could not stop ${handle.name}: ${messageOf(error)}`);
      }
    }
    try {
      const code = await runCommand(resetArgv('--drop'), {
        env: { DATABASE_URL: E2E_DATABASE_URL },
      });
      if (code !== 0) {
        throw new Error(`reset --drop exited with ${code}`);
      }
      log(`cleanup: dropped ${E2E_DATABASE_NAME}`);
    } catch (error) {
      cleanupFailed = true;
      logError(
        `cleanup: FAILED to drop ${E2E_DATABASE_NAME}: ${messageOf(error)}. ` +
          'Drop it manually, or simply rerun pnpm e2e — the next run ' +
          'recreates from scratch.',
      );
    }
    return cleanupFailed;
  }

  async function step(name, argv, options) {
    const code = await runCommand(argv, options);
    if (code !== 0) {
      throw new Error(`${name} failed with exit code ${code}`);
    }
  }

  async function run(extraArgs = []) {
    let primaryExit = 1;
    try {
      // 1. Preflight: refuse occupied ports before any mutation; this
      // run never attaches to (or kills) servers it did not start.
      for (const port of [BACKEND_PORT, UI_PORT]) {
        if (!(await checkPortFree(port))) {
          throw new Error(
            `preflight: port ${port} is already in use; stop whatever is ` +
              'listening there (this runner never attaches to or kills ' +
              'an existing process)',
          );
        }
      }

      // 2. Fresh, head-migrated database. --recreate starts with
      // DROP IF EXISTS, which also self-heals an interrupted prior run.
      await step('database recreate', resetArgv('--recreate'), {
        env: { DATABASE_URL: E2E_DATABASE_URL },
      });

      // 3. Universal seed: the documented bootstrap CLI. Password via
      // stdin only — it never appears in argv or output.
      await step('admin bootstrap', BOOTSTRAP_ARGV, {
        env: { DATABASE_URL: E2E_DATABASE_URL },
        input: ADMIN_PASSWORD + '\n',
      });

      // 4–5. Backend, readiness-gated (readiness proves the database).
      children.push(
        spawnChild('backend', BACKEND_ARGV, {
          env: {
            DATABASE_URL: E2E_DATABASE_URL,
            TRUSTED_ORIGINS: UI_ORIGIN,
          },
        }),
      );
      if (!(await pollReady(BACKEND_READY_URLS, READY_TIMEOUT_MS))) {
        throw new Error('backend did not become ready in time');
      }

      // 6–7. Control center through the same-origin proxy. Vite must
      // run from the app directory so it serves the app and loads its
      // config (index.html, proxy) — not the repository root.
      children.push(
        spawnChild('control-center', deps.uiArgv, {
          env: { CC_API_PROXY_TARGET: `http://127.0.0.1:${BACKEND_PORT}` },
          cwd: deps.uiCwd,
        }),
      );
      if (!(await pollReady(UI_READY_URLS, READY_TIMEOUT_MS))) {
        throw new Error('control center did not become ready in time');
      }

      // 8. Playwright. Selection args pass through unchanged so single
      // files and --grep work via pnpm e2e.
      primaryExit = await runTests(extraArgs, {
        E2E_ORCHESTRATED: '1',
        E2E_BASE_URL: UI_ORIGIN,
        E2E_ADMIN_EMAIL: ADMIN_EMAIL,
        E2E_ADMIN_PASSWORD: ADMIN_PASSWORD,
      });
    } catch (error) {
      logError(messageOf(error));
      primaryExit = 1;
    } finally {
      const failed = await cleanup();
      // A cleanup failure is always loud, but it never masks the
      // primary result; if the run itself was green it still fails.
      if (failed && primaryExit === 0) {
        primaryExit = CLEANUP_FAILED_EXIT;
      }
    }
    return primaryExit;
  }

  async function handleSignal() {
    await cleanup();
    return SIGNAL_EXIT;
  }

  return { run, handleSignal };
}
