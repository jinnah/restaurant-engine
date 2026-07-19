// Deterministic coverage for tracked child-tree termination (F5):
// fakes only — no real processes are spawned or signaled.

import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createChildTerminator } from './processControl.mjs';

function fakes(overrides = {}) {
  const calls = { signals: [], taskkills: [] };
  const deps = {
    platform: overrides.platform ?? 'linux',
    signalProcess: (pid, signal) => {
      calls.signals.push({ pid, signal });
      if (overrides.signalThrows) {
        const error = new Error('kill failed');
        error.code = overrides.signalThrows;
        throw error;
      }
    },
    runTaskkill: (args) => {
      calls.taskkills.push(args);
    },
    // Immediate 'timeout' unless the handle exits first (both fakes
    // resolve synchronously; Promise.race order breaks the tie).
    wait: async () => {},
  };
  return { deps, calls };
}

function liveHandle(pid, { exits = false } = {}) {
  return {
    name: 'backend',
    child: { pid, exitCode: null, signalCode: null },
    exited: exits ? Promise.resolve() : new Promise(() => {}),
  };
}

test('POSIX signals exactly the tracked group, graceful before forced', async () => {
  const { deps, calls } = fakes();
  await createChildTerminator(deps)(liveHandle(123));

  // Only -123 was ever targeted; SIGTERM strictly precedes SIGKILL.
  assert.deepEqual(
    calls.signals.map((entry) => entry.pid),
    [-123, -123],
  );
  assert.deepEqual(
    calls.signals.map((entry) => entry.signal),
    ['SIGTERM', 'SIGKILL'],
  );
  assert.equal(calls.taskkills.length, 0);
});

test('POSIX stops after SIGTERM when the child exits within the grace', async () => {
  const { deps, calls } = fakes();
  await createChildTerminator(deps)(liveHandle(123, { exits: true }));

  assert.deepEqual(calls.signals, [{ pid: -123, signal: 'SIGTERM' }]);
});

test('an already-exited child is left alone without failing', async () => {
  const { deps, calls } = fakes();
  await createChildTerminator(deps)({
    name: 'backend',
    child: { pid: 123, exitCode: 0, signalCode: null },
    exited: Promise.resolve(),
  });
  assert.equal(calls.signals.length, 0);
  assert.equal(calls.taskkills.length, 0);
});

test('a handle that never spawned (no pid) is refused without signaling', async () => {
  const { deps, calls } = fakes();
  await createChildTerminator(deps)({
    name: 'backend',
    child: { pid: undefined, exitCode: null, signalCode: null },
    exited: Promise.resolve(),
  });
  assert.equal(calls.signals.length, 0);
  assert.equal(calls.taskkills.length, 0);
});

test('ESRCH (group already gone) is success, not a cleanup failure', async () => {
  const { deps, calls } = fakes({ signalThrows: 'ESRCH' });
  await createChildTerminator(deps)(liveHandle(123, { exits: true }));
  assert.equal(calls.signals.length, 1); // attempted once, absorbed
});

test('a real signal failure surfaces so cleanup can report it', async () => {
  const { deps } = fakes({ signalThrows: 'EPERM' });
  await assert.rejects(
    () => createChildTerminator(deps)(liveHandle(123)),
    /kill failed/,
  );
});

test('Windows kills exactly the tracked PID tree via taskkill', async () => {
  const { deps, calls } = fakes({ platform: 'win32' });
  await createChildTerminator(deps)(liveHandle(4242, { exits: true }));

  assert.deepEqual(calls.taskkills, [['/pid', '4242', '/T', '/F']]);
  assert.equal(calls.signals.length, 0);
});
