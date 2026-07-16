// Smoke verification for the one-command development stack (`pnpm dev`).
//
// Polls the backend health probes and both application shells with a
// bounded timeout and reports each check. Exit 0 when everything is up,
// exit 1 otherwise. Uses only Node built-ins (global fetch, Node 24).
//
// Not a CI job by design: CI builds and tests every component; this script
// is the documented local and clean-clone proof that the composed dev
// stack actually serves (docs/05).

const TIMEOUT_MS = 180_000; // Next.js compiles its first page on demand.
const POLL_INTERVAL_MS = 2_000;

const CHECKS = [
  {
    name: 'API liveness (http://127.0.0.1:8000/health/live)',
    url: 'http://127.0.0.1:8000/health/live',
    verify: async (response) =>
      response.status === 200 && (await response.json()).status === 'alive',
  },
  {
    name: 'API readiness (http://127.0.0.1:8000/health/ready)',
    url: 'http://127.0.0.1:8000/health/ready',
    verify: async (response) => {
      if (response.status !== 200) return false;
      const body = await response.json();
      return body.status === 'ready' && body.checks?.database?.status === 'up';
    },
  },
  // The shells use localhost, not 127.0.0.1: Vite binds only the loopback
  // family that `localhost` resolves to first (::1 on this machine), and
  // Node's fetch tries both families. The 127.0.0.1 rule (docs/05) applies
  // to PostgreSQL connections, not to the dev servers.
  {
    name: 'Storefront shell (http://localhost:3000/)',
    url: 'http://localhost:3000/',
    verify: async (response) =>
      response.status === 200 && (await response.text()).includes('Storefront'),
  },
  {
    name: 'Control-center shell (http://localhost:5173/)',
    url: 'http://localhost:5173/',
    verify: async (response) =>
      response.status === 200 &&
      (await response.text()).includes('Restaurant Engine Control Center'),
  },
];

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function passes(check) {
  try {
    const response = await fetch(check.url, {
      signal: AbortSignal.timeout(5_000),
    });
    return await check.verify(response);
  } catch {
    return false;
  }
}

const deadline = Date.now() + TIMEOUT_MS;
const pending = new Set(CHECKS);

while (pending.size > 0 && Date.now() < deadline) {
  for (const check of [...pending]) {
    if (await passes(check)) {
      console.log(`smoke: OK   ${check.name}`);
      pending.delete(check);
    }
  }
  if (pending.size > 0) {
    await sleep(POLL_INTERVAL_MS);
  }
}

if (pending.size > 0) {
  for (const check of pending) {
    console.error(
      `smoke: FAIL ${check.name} (not up within ${TIMEOUT_MS / 1000}s)`,
    );
  }
  console.error(
    'smoke: is the stack running? Start it with `corepack pnpm dev`.',
  );
  process.exit(1);
}
console.log('smoke: development stack is fully up.');
