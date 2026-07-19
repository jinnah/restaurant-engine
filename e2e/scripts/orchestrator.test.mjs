// Deterministic regression coverage for the E2E lifecycle owner
// (node:test, no dependencies): every mandated failure path is proven
// against injected fakes — no real processes, servers, or databases.

import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  ADMIN_PASSWORD,
  BACKEND_PORT,
  CLEANUP_FAILED_EXIT,
  E2E_DATABASE_NAME,
  E2E_DATABASE_URL,
  SIGNAL_EXIT,
  UI_PORT,
  createOrchestrator,
} from './orchestrator.mjs';

const UI_ARGV = ['node', '/resolved/vite.js', '--port', '5273', '--strictPort'];

function isReset(argv, mode) {
  return argv.includes('scripts.reset_e2e_database') && argv.includes(mode);
}

function isBootstrap(argv) {
  return argv.includes('scripts.create_platform_admin');
}

/**
 * A scriptable fake world. Every interaction is recorded so tests can
 * assert exactly what the orchestrator did — and did not — touch.
 */
function fakeWorld(overrides = {}) {
  const calls = {
    portChecks: [],
    commands: [],
    spawns: [],
    kills: [],
    testRuns: [],
    logs: [],
    errors: [],
  };
  const deps = {
    checkPortFree: async (port) => {
      calls.portChecks.push(port);
      return overrides.occupiedPorts?.includes(port) !== true;
    },
    runCommand: async (argv, options = {}) => {
      calls.commands.push({ argv, options });
      if (isReset(argv, '--recreate')) {
        return overrides.recreateExit ?? 0;
      }
      if (isBootstrap(argv)) {
        return overrides.bootstrapExit ?? 0;
      }
      if (isReset(argv, '--drop')) {
        return overrides.dropExit ?? 0;
      }
      return 0;
    },
    spawnChild: (name, argv, options = {}) => {
      const handle = {
        name,
        argv,
        options,
        // Resolves with an Error for a scripted spawn failure; stays
        // pending otherwise (the real contract).
        spawnFailed:
          overrides.spawnFails === name
            ? Promise.resolve(new Error(name + ' spawn ENOENT'))
            : new Promise(() => {}),
      };
      calls.spawns.push(handle);
      return handle;
    },
    killChild: async (handle) => {
      calls.kills.push(handle);
      if (overrides.killThrows === true) {
        throw new Error('kill failed');
      }
    },
    pollReady: async (urls) => {
      const isBackend = urls.some((url) => url.includes(String(BACKEND_PORT)));
      const target = isBackend ? 'backend' : 'control-center';
      if (overrides.spawnFails === target) {
        // A child that failed to spawn can never become ready; the
        // spawnFailed race must win, exactly as in the real world.
        return new Promise(() => {});
      }
      if (isBackend) {
        return overrides.backendReady ?? true;
      }
      return overrides.uiReady ?? true;
    },
    runTests: async (extraArgs, env) => {
      calls.testRuns.push({ extraArgs, env });
      return overrides.testsExit ?? 0;
    },
    uiArgv: UI_ARGV,
    uiCwd: '/resolved/control-center',
    log: (text) => calls.logs.push(text),
    logError: (text) => calls.errors.push(text),
  };
  return { deps, calls };
}

test('1. an occupied port fails preflight before any database mutation', async () => {
  const { deps, calls } = fakeWorld({ occupiedPorts: [BACKEND_PORT] });
  const exit = await createOrchestrator(deps).run();

  assert.notEqual(exit, 0);
  assert.ok(calls.errors.some((text) => text.includes('preflight')));
  // No recreate, no bootstrap, no servers, no tests ran.
  assert.equal(
    calls.commands.filter(({ argv }) => isReset(argv, '--recreate')).length,
    0,
  );
  assert.equal(calls.spawns.length, 0);
  assert.equal(calls.testRuns.length, 0);
});

test('2. a database recreation failure still attempts safe cleanup', async () => {
  const { deps, calls } = fakeWorld({ recreateExit: 1 });
  const exit = await createOrchestrator(deps).run();

  assert.notEqual(exit, 0);
  assert.equal(calls.spawns.length, 0);
  assert.equal(
    calls.commands.filter(({ argv }) => isReset(argv, '--drop')).length,
    1,
  );
});

test('3. a bootstrap failure prevents server startup and cleans up', async () => {
  const { deps, calls } = fakeWorld({ bootstrapExit: 1 });
  const exit = await createOrchestrator(deps).run();

  assert.notEqual(exit, 0);
  assert.equal(calls.spawns.length, 0);
  assert.equal(calls.testRuns.length, 0);
  assert.equal(
    calls.commands.filter(({ argv }) => isReset(argv, '--drop')).length,
    1,
  );
});

test('4. a backend readiness timeout stops the backend and drops the database', async () => {
  const { deps, calls } = fakeWorld({ backendReady: false });
  const exit = await createOrchestrator(deps).run();

  assert.notEqual(exit, 0);
  assert.deepEqual(
    calls.kills.map((handle) => handle.name),
    ['backend'],
  );
  assert.equal(
    calls.commands.filter(({ argv }) => isReset(argv, '--drop')).length,
    1,
  );
  assert.equal(calls.testRuns.length, 0);
});

test('5. a frontend readiness timeout stops both children and drops the database', async () => {
  const { deps, calls } = fakeWorld({ uiReady: false });
  const exit = await createOrchestrator(deps).run();

  assert.notEqual(exit, 0);
  // Reverse order: the most recently started child stops first.
  assert.deepEqual(
    calls.kills.map((handle) => handle.name),
    ['control-center', 'backend'],
  );
  assert.equal(
    calls.commands.filter(({ argv }) => isReset(argv, '--drop')).length,
    1,
  );
});

test('6. a Playwright failure code is preserved after successful cleanup', async () => {
  const { deps, calls } = fakeWorld({ testsExit: 7 });
  const exit = await createOrchestrator(deps).run();

  assert.equal(exit, 7);
  assert.equal(
    calls.commands.filter(({ argv }) => isReset(argv, '--drop')).length,
    1,
  );
});

test('7. a cleanup failure is reported without hiding the primary failure', async () => {
  const { deps, calls } = fakeWorld({ testsExit: 7, dropExit: 1 });
  const exit = await createOrchestrator(deps).run();

  assert.equal(exit, 7); // the primary failure wins
  assert.ok(
    calls.errors.some((text) =>
      text.includes(`FAILED to drop ${E2E_DATABASE_NAME}`),
    ),
  );
});

test('8. a cleanup failure after green tests still fails the run distinctly', async () => {
  const { deps, calls } = fakeWorld({ testsExit: 0, dropExit: 1 });
  const exit = await createOrchestrator(deps).run();

  assert.equal(exit, CLEANUP_FAILED_EXIT);
  assert.ok(
    calls.errors.some((text) =>
      text.includes(`FAILED to drop ${E2E_DATABASE_NAME}`),
    ),
  );
});

test('9. a signal initiates cleanup exactly once with the signal status', async () => {
  const { deps, calls } = fakeWorld();
  const orchestrator = createOrchestrator(deps);

  // Start servers, then interrupt mid-run: never resolves tests.
  deps.runTests = () => new Promise(() => {});
  const running = orchestrator.run();
  await new Promise((resolve) => setTimeout(resolve, 10));

  const first = await orchestrator.handleSignal();
  const second = await orchestrator.handleSignal();
  assert.equal(first, SIGNAL_EXIT);
  assert.equal(second, SIGNAL_EXIT);
  // Cleanup ran once: each child killed once, one drop.
  assert.deepEqual(
    calls.kills.map((handle) => handle.name),
    ['control-center', 'backend'],
  );
  assert.equal(
    calls.commands.filter(({ argv }) => isReset(argv, '--drop')).length,
    1,
  );
  void running; // intentionally left pending, like an interrupted process
});

test('10. commands and children target only the approved ports and database', async () => {
  const { deps, calls } = fakeWorld();
  await createOrchestrator(deps).run();

  // Every database-touching command is pinned to the e2e URL, and the
  // bootstrap password travels via stdin, never argv.
  for (const { argv, options } of calls.commands) {
    assert.equal(options.env.DATABASE_URL, E2E_DATABASE_URL);
    assert.ok(!argv.includes(ADMIN_PASSWORD));
  }
  const bootstrap = calls.commands.find(({ argv }) => isBootstrap(argv));
  assert.equal(bootstrap.options.input, ADMIN_PASSWORD + '\n');

  const backend = calls.spawns.find((handle) => handle.name === 'backend');
  assert.ok(backend.argv.includes(String(BACKEND_PORT)));
  assert.equal(backend.options.env.DATABASE_URL, E2E_DATABASE_URL);
  assert.equal(
    backend.options.env.TRUSTED_ORIGINS,
    `http://localhost:${UI_PORT}`,
  );

  const ui = calls.spawns.find((handle) => handle.name === 'control-center');
  assert.deepEqual(ui.argv, UI_ARGV);
  assert.equal(ui.options.cwd, '/resolved/control-center');
  assert.equal(
    ui.options.env.CC_API_PROXY_TARGET,
    `http://127.0.0.1:${BACKEND_PORT}`,
  );
});

test('11. Playwright selection arguments are forwarded unchanged', async () => {
  const { deps, calls } = fakeWorld();
  const selection = ['tests/onboarding.spec.ts', '--grep', 'redirect'];
  await createOrchestrator(deps).run(selection);

  assert.deepEqual(calls.testRuns[0].extraArgs, selection);
  assert.equal(calls.testRuns[0].env.E2E_ORCHESTRATED, '1');
});

test('12. only tracked children are ever targeted by cleanup', async () => {
  const { deps, calls } = fakeWorld({ testsExit: 1 });
  await createOrchestrator(deps).run();

  const spawned = new Set(calls.spawns);
  assert.equal(calls.kills.length, calls.spawns.length);
  for (const killed of calls.kills) {
    assert.ok(spawned.has(killed), 'killed a handle it never spawned');
  }
});

test('a kill failure marks cleanup failed but still attempts the drop', async () => {
  const { deps, calls } = fakeWorld({ testsExit: 0, killThrows: true });
  const exit = await createOrchestrator(deps).run();

  assert.equal(exit, CLEANUP_FAILED_EXIT);
  assert.equal(
    calls.commands.filter(({ argv }) => isReset(argv, '--drop')).length,
    1,
  );
});

test('14. a backend spawn failure becomes a controlled failure with cleanup', async () => {
  const { deps, calls } = fakeWorld({ spawnFails: 'backend' });
  const exit = await createOrchestrator(deps).run();

  assert.notEqual(exit, 0);
  assert.ok(
    calls.errors.some((text) => text.includes('backend failed to start')),
  );
  assert.equal(calls.testRuns.length, 0);
  // The tracked (failed) child is handed to cleanup; the drop still runs.
  assert.deepEqual(
    calls.kills.map((handle) => handle.name),
    ['backend'],
  );
  assert.equal(
    calls.commands.filter(({ argv }) => isReset(argv, '--drop')).length,
    1,
  );
});

test('15. a frontend spawn failure stops both children and cleans up', async () => {
  const { deps, calls } = fakeWorld({ spawnFails: 'control-center' });
  const exit = await createOrchestrator(deps).run();

  assert.notEqual(exit, 0);
  assert.ok(
    calls.errors.some((text) =>
      text.includes('control-center failed to start'),
    ),
  );
  assert.deepEqual(
    calls.kills.map((handle) => handle.name),
    ['control-center', 'backend'],
  );
  assert.equal(
    calls.commands.filter(({ argv }) => isReset(argv, '--drop')).length,
    1,
  );
  assert.equal(calls.testRuns.length, 0);
});

test('16. a Playwright spawn failure is a controlled failure with cleanup', async () => {
  const { deps, calls } = fakeWorld();
  deps.runTests = async () => {
    throw new Error('playwright spawn ENOENT');
  };
  const exit = await createOrchestrator(deps).run();

  assert.notEqual(exit, 0);
  assert.ok(
    calls.errors.some((text) => text.includes('playwright spawn ENOENT')),
  );
  assert.deepEqual(
    calls.kills.map((handle) => handle.name),
    ['control-center', 'backend'],
  );
  assert.equal(
    calls.commands.filter(({ argv }) => isReset(argv, '--drop')).length,
    1,
  );
});

test('17. a cleanup failure alongside a spawn failure reports both, once', async () => {
  const { deps, calls } = fakeWorld({ spawnFails: 'backend', dropExit: 1 });
  const exit = await createOrchestrator(deps).run();

  assert.notEqual(exit, 0);
  assert.ok(
    calls.errors.some((text) => text.includes('backend failed to start')),
  );
  assert.ok(
    calls.errors.some((text) =>
      text.includes('FAILED to drop ' + E2E_DATABASE_NAME),
    ),
  );
  // Single-shot cleanup: one drop attempt, each child killed once.
  assert.equal(
    calls.commands.filter(({ argv }) => isReset(argv, '--drop')).length,
    1,
  );
  assert.deepEqual(
    calls.kills.map((handle) => handle.name),
    ['backend'],
  );
});
