// Entry point for `pnpm e2e`: wires the orchestrator to real process,
// network, and filesystem primitives, registers signal handlers BEFORE
// anything mutates, and propagates the exit status.
//
// Cross-platform notes: every spawn uses an argument array with
// `shell: false`. `uv` resolves as a native executable on PATH on both
// platforms; vite and the Playwright CLI are launched as
// `node <resolved-script>` so no Windows .cmd shim is ever executed.
// Child termination targets only tracked process trees — the recorded
// PID tree via taskkill /T on Windows, the child's own detached process
// group elsewhere (processControl.mjs) — never a port or process name.

import { spawn, spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import net from 'node:net';
import { dirname, join } from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';
import { buildUiArgv, createOrchestrator } from './orchestrator.mjs';
import { createChildTerminator } from './processControl.mjs';

const E2E_DIR = dirname(dirname(fileURLToPath(import.meta.url)));
const REPO_ROOT = dirname(E2E_DIR);
const CONTROL_CENTER_DIR = join(REPO_ROOT, 'apps', 'control-center');

const requireFromControlCenter = createRequire(
  join(CONTROL_CENTER_DIR, 'package.json'),
);
const requireFromE2e = createRequire(join(E2E_DIR, 'package.json'));

// Vite's exports map blocks deep subpaths, but './package.json' is
// always exported: resolve the manifest, then follow its bin field.
function resolveBinScript(resolver, packageName, binName) {
  const manifestPath = resolver.resolve(`${packageName}/package.json`);
  const manifest = resolver(`${packageName}/package.json`);
  const bin =
    typeof manifest.bin === 'string' ? manifest.bin : manifest.bin[binName];
  return join(dirname(manifestPath), bin);
}

const VITE_SCRIPT = resolveBinScript(requireFromControlCenter, 'vite', 'vite');
const PLAYWRIGHT_CLI = resolveBinScript(
  requireFromE2e,
  '@playwright/test',
  'playwright',
);

function listenProbe(port, host) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.unref();
    server.once('error', (error) => {
      resolve(error.code === 'EADDRINUSE' ? 'occupied' : 'unknown');
    });
    server.listen({ port, host, exclusive: true }, () => {
      server.close(() => {
        resolve('free');
      });
    });
  });
}

async function checkPortFree(port) {
  // Both loopback families: dev servers bind variously to 127.0.0.1,
  // ::1, or both (the port-8000 Docker-proxy lesson).
  for (const host of ['127.0.0.1', '::1']) {
    if ((await listenProbe(port, host)) === 'occupied') {
      return false;
    }
  }
  return true;
}

function runCommand(argv, { env = {}, input } = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(argv[0], argv.slice(1), {
      cwd: REPO_ROOT,
      env: { ...process.env, ...env },
      stdio: [input === undefined ? 'ignore' : 'pipe', 'inherit', 'inherit'],
      shell: false,
    });
    child.once('error', reject);
    if (input !== undefined) {
      child.stdin.write(input);
      child.stdin.end();
    }
    child.once('exit', (code) => {
      resolve(code ?? 1);
    });
  });
}

function spawnChild(name, argv, { env = {}, cwd = REPO_ROOT } = {}) {
  const child = spawn(argv[0], argv.slice(1), {
    cwd,
    env: { ...process.env, ...env },
    stdio: ['ignore', 'inherit', 'inherit'],
    shell: false,
    // POSIX: each long-lived child leads its own process group so
    // cleanup can signal exactly that tracked tree (processControl.mjs).
    detached: process.platform !== 'win32',
  });
  // Both settle idempotently: an 'error' (spawn failure) resolves the
  // exit promise too, so no wait can hang, no EventEmitter 'error' goes
  // unhandled, and error-then-exit cannot double-settle anything.
  let reportSpawnFailure = () => {};
  const spawnFailed = new Promise((resolve) => {
    reportSpawnFailure = resolve;
  });
  const exited = new Promise((resolve) => {
    child.once('exit', resolve);
    child.once('error', resolve);
  });
  child.once('error', (error) => {
    reportSpawnFailure(error);
  });
  return { name, child, exited, spawnFailed };
}

const killChild = createChildTerminator({
  platform: process.platform,
  signalProcess: (pid, signal) => {
    process.kill(pid, signal);
  },
  runTaskkill: (args) => {
    spawnSync('taskkill', args, { stdio: 'ignore', shell: false });
  },
  wait: sleep,
});

async function pollReady(urls, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    for (const url of urls) {
      try {
        const response = await fetch(url, {
          signal: AbortSignal.timeout(2000),
        });
        if (response.ok) {
          return true;
        }
      } catch {
        // Not up yet (or the wrong loopback family); keep polling.
      }
    }
    await sleep(500);
  }
  return false;
}

function runTests(extraArgs, env) {
  return new Promise((resolve, reject) => {
    const child = spawn(
      process.execPath,
      [PLAYWRIGHT_CLI, 'test', ...extraArgs],
      {
        cwd: E2E_DIR,
        env: { ...process.env, ...env },
        stdio: 'inherit',
        shell: false,
      },
    );
    child.once('error', reject);
    child.once('exit', (code) => {
      resolve(code ?? 1);
    });
  });
}

const orchestrator = createOrchestrator({
  checkPortFree,
  runCommand,
  spawnChild,
  killChild,
  pollReady,
  runTests,
  uiArgv: buildUiArgv(process.execPath, VITE_SCRIPT),
  uiCwd: CONTROL_CENTER_DIR,
  log: (text) => {
    console.log(`[e2e] ${text}`);
  },
  logError: (text) => {
    console.error(`[e2e] ${text}`);
  },
});

// Registered before run() starts — before any database mutation — so an
// interrupt at any stage flows through the single cleanup path.
let signaled = false;
for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => {
    if (signaled) {
      return;
    }
    signaled = true;
    void orchestrator.handleSignal().then((code) => {
      process.exit(code);
    });
  });
}

const exitCode = await orchestrator.run(process.argv.slice(2));
process.exit(exitCode);
