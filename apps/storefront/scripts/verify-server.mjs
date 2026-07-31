// Built-server verification (M4D, ADR-021).
//
// Boots the storefront's production build (`next start`) against a
// disposable in-process stub API on ephemeral loopback ports and asserts
// the wire behavior that unit tests cannot prove: emitted Cache-Control
// headers (pages no-store, hashed assets immutable), real HTTP statuses
// for the neutral 404 / generic error / production-disabled proxy, Host
// forwarding through the whole rendering stack, and the measured number
// of backend requests per render. Node built-ins only; nothing preserved
// is touched and everything started here is stopped on every exit path.
//
// Requires a completed production build (`pnpm build`). Run from anywhere:
// `node apps/storefront/scripts/verify-server.mjs`.

import { spawn, spawnSync } from 'node:child_process';
import http from 'node:http';
import net from 'node:net';
import { createRequire } from 'node:module';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const APP_DIR = join(fileURLToPath(new URL('.', import.meta.url)), '..');
const require_ = createRequire(join(APP_DIR, 'package.json'));

const STARTUP_TIMEOUT_MS = 60_000;
const REQUEST_TIMEOUT_MS = 10_000;

// ---------------------------------------------------------------- fixtures

const STOREFRONT_PAYLOAD = {
  business: {
    name: 'Verify Kitchen',
    slug: 'verify-kitchen',
    timezone: 'America/New_York',
    currency: 'USD',
  },
  design_variant: 'classic',
  // M4G-B: a deliberately NON-default palette and pairing, so the
  // delivered HTML proves the theme tokens reach the tenant-page
  // element itself (the canvas), not merely a descendant.
  theme: {
    accent: '#0f2f4f',
    palette: 'midnight',
    type_pairing: 'serif_display',
    logo: null,
  },
  sections: [
    {
      id: 'hero-main',
      type: 'hero',
      props: {
        heading: 'Verification hero heading',
        subheading: 'Verification subheading',
        image: null,
        primary_action: 'view_menu',
      },
    },
    {
      id: 'menu-main',
      type: 'menu',
      props: { heading: 'Menu preview', intro: null },
    },
  ],
};

const MENU_PAYLOAD = {
  business: STOREFRONT_PAYLOAD.business,
  categories: [
    {
      id: '00000000-0000-0000-0000-000000000201',
      name: 'Verification mains',
      description: null,
      items: [
        {
          id: '00000000-0000-0000-0000-000000000101',
          name: 'Verification dish',
          description: null,
          price_minor: 1250,
          is_available: true,
          is_orderable: true,
          dietary_tags: [],
          image: null,
          modifier_groups: [],
        },
      ],
    },
  ],
  featured_item_ids: ['00000000-0000-0000-0000-000000000101'],
};

const NOT_FOUND_BODY = JSON.stringify({
  error: { code: 'not_found', message: 'Not found.' },
});

// ------------------------------------------------------------------ helpers

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address();
      server.close((error) => (error ? reject(error) : resolve(port)));
    });
  });
}

function request(port, path, host, method = 'GET') {
  return new Promise((resolve, reject) => {
    const req = http.request(
      { host: '127.0.0.1', port, path, method, headers: { host } },
      (res) => {
        const chunks = [];
        res.on('data', (c) => chunks.push(c));
        res.on('end', () =>
          resolve({
            status: res.statusCode ?? 0,
            headers: res.headers,
            body: Buffer.concat(chunks).toString('utf-8'),
          }),
        );
      },
    );
    const timer = setTimeout(() => {
      req.destroy();
      reject(new Error(`request timeout: ${path}`));
    }, REQUEST_TIMEOUT_MS);
    req.on('close', () => clearTimeout(timer));
    req.on('error', reject);
    req.end();
  });
}

const failures = [];
function check(name, condition, detail = '') {
  const verdict = condition ? 'OK  ' : 'FAIL';
  console.log(`verify: ${verdict} ${name}${detail ? ` (${detail})` : ''}`);
  if (!condition) {
    failures.push(name);
  }
}

// --------------------------------------------------------------------- main

const tenantRequests = [];
let stubClosed = false;

async function main() {
  const stubPort = await freePort();
  const appPort = await freePort();
  const tenantHost = `verify-kitchen.localhost:${appPort}`;
  const unknownHost = `unknown.localhost:${appPort}`;

  const stub = http.createServer((req, res) => {
    tenantRequests.push({ url: req.url ?? '', host: req.headers.host ?? '' });
    const isTenant = (req.headers.host ?? '') === tenantHost;
    const respond = (status, body, type = 'application/json') => {
      res.writeHead(status, {
        'content-type': type,
        'cache-control': status === 200 ? 'public, max-age=60' : 'no-store',
      });
      res.end(body);
    };
    if (!isTenant) {
      respond(404, NOT_FOUND_BODY);
    } else if (req.url === '/api/v1/public/storefront') {
      respond(200, JSON.stringify(STOREFRONT_PAYLOAD));
    } else if (req.url === '/api/v1/public/menu') {
      respond(200, JSON.stringify(MENU_PAYLOAD));
    } else {
      respond(404, NOT_FOUND_BODY);
    }
  });
  await new Promise((resolve) => stub.listen(stubPort, '127.0.0.1', resolve));

  const nextBin = require_.resolve('next/dist/bin/next');
  const child = spawn(
    process.execPath,
    [nextBin, 'start', '-p', String(appPort), '-H', '127.0.0.1'],
    {
      cwd: APP_DIR,
      env: {
        ...process.env,
        NODE_ENV: 'production',
        STOREFRONT_API_ORIGIN: `http://127.0.0.1:${stubPort}`,
      },
      stdio: ['ignore', 'pipe', 'pipe'],
    },
  );
  child.stdout.on('data', () => {});
  child.stderr.on('data', () => {});

  const stop = () => {
    if (process.platform === 'win32' && child.pid !== undefined) {
      spawnSync('taskkill', ['/pid', String(child.pid), '/T', '/F'], {
        stdio: 'ignore',
      });
    } else {
      child.kill('SIGTERM');
    }
    if (!stubClosed) {
      stub.close();
      stubClosed = true;
    }
  };

  try {
    // Readiness: poll until the tenant page answers.
    const deadline = Date.now() + STARTUP_TIMEOUT_MS;
    let ready = false;
    while (Date.now() < deadline && !ready) {
      try {
        const probe = await request(appPort, '/', tenantHost);
        if (probe.status === 200 || probe.status === 404) {
          ready = true;
          break;
        }
      } catch {
        // Not listening yet.
      }
      await new Promise((r) => setTimeout(r, 500));
    }
    if (!ready) {
      throw new Error('storefront server did not become ready');
    }

    // --- Tenant home page.
    tenantRequests.length = 0;
    const home = await request(appPort, '/', tenantHost);
    check('home: 200 for the published tenant', home.status === 200);
    check(
      'home: HTML is no-store',
      home.headers['cache-control'] === 'no-store',
      String(home.headers['cache-control']),
    );
    check(
      'home: renders business name and hero',
      home.body.includes('Verify Kitchen') &&
        home.body.includes('Verification hero heading'),
    );
    check(
      'home: composes featured item with exact price',
      home.body.includes('Verification dish') && home.body.includes('$12.50'),
    );
    check(
      'home: title from published data',
      home.body.includes('<title>Verify Kitchen</title>'),
    );
    check(
      'home: canonical link on the http dev-family origin',
      home.body.includes(`http://${tenantHost}/`),
    );
    check(
      'home: JSON-LD script embedded with Restaurant data',
      home.body.includes('application/ld+json') &&
        home.body.includes('"@type":"Restaurant"') &&
        home.body.includes('"name":"Verify Kitchen"'),
    );
    check(
      'home: backend saw the tenant Host on every request',
      tenantRequests.length > 0 &&
        tenantRequests.every((r) => r.host === tenantHost),
      `${String(tenantRequests.length)} backend requests`,
    );
    const homeRenderRequests = tenantRequests.map((r) => r.url);
    console.log(
      `verify: INFO home render backend requests: ${homeRenderRequests.join(', ')}`,
    );
    // M4G-B (ADR-024 section 5): the theme's custom properties are set on
    // the element carrying the tenant-page baseline class - <body> - so
    // the browser paints the canvas from the selected palette. Asserted
    // on the wire, from the built server, not inferred from a component.
    const bodyTag = /<body[^>]*>/.exec(home.body)?.[0] ?? '';
    check(
      'home: the tenant-page element carries the palette tokens',
      bodyTag.includes('--color-bg:#14171c') &&
        bodyTag.includes('--color-text:#f2f4f7'),
      bodyTag.slice(0, 200),
    );
    check(
      'home: the tenant-page element carries the typography tokens',
      bodyTag.includes('--font-heading:ui-serif') &&
        bodyTag.includes('--type-scale:1.05'),
    );
    check(
      'home: the tenant-page element carries the tenant accent',
      bodyTag.includes('--accent:#0f2f4f'),
    );
    // ADR-024 section 5: the stored accent is a dark navy, unreadable as
    // text on the midnight palette, so the derived token must differ
    // from it - and the stored accent itself must be untouched.
    const accentText = /--accent-text:(#[0-9a-f]{6})/.exec(bodyTag)?.[1];
    check(
      'home: the derived accent-text token differs from the stored accent',
      accentText !== undefined && accentText !== '#0f2f4f',
      String(accentText),
    );
    // ADR-021 section 3: the measured render cost is TWO backend reads
    // (projection + menu). The root layout reads the same argument-less
    // React.cache loader the page body and generateMetadata already call,
    // so it must deduplicate rather than add a third request.
    check(
      'home: render cost is exactly two backend reads',
      homeRenderRequests.length === 2,
      `${String(homeRenderRequests.length)}: ${homeRenderRequests.join(', ')}`,
    );

    // --- Static assets keep the framework's immutable caching.
    const assetMatch = home.body.match(/\/_next\/static\/[^"]+\.js/);
    check('assets: home references a hashed script', assetMatch !== null);
    if (assetMatch !== null) {
      const asset = await request(appPort, assetMatch[0], tenantHost);
      check(
        'assets: hashed build asset is immutable, not no-store',
        asset.status === 200 &&
          String(asset.headers['cache-control']).includes('immutable'),
        String(asset.headers['cache-control']),
      );
    }

    // --- Menu page.
    tenantRequests.length = 0;
    const menu = await request(appPort, '/menu', tenantHost);
    check('menu: 200 for the published tenant', menu.status === 200);
    check(
      'menu: renders the listing with exact price',
      menu.body.includes('Verification mains') && menu.body.includes('$12.50'),
    );
    check(
      'menu: no-store',
      menu.headers['cache-control'] === 'no-store',
      String(menu.headers['cache-control']),
    );
    const menuRenderRequests = tenantRequests.map((r) => r.url);
    console.log(
      `verify: INFO menu render backend requests: ${menuRenderRequests.join(', ')}`,
    );
    const menuBodyTag = /<body[^>]*>/.exec(menu.body)?.[0] ?? '';
    check(
      'menu: the tenant-page element carries the palette tokens',
      menuBodyTag.includes('--color-bg:#14171c'),
      menuBodyTag.slice(0, 200),
    );
    check(
      'menu: render cost is exactly two backend reads',
      menuRenderRequests.length === 2,
      `${String(menuRenderRequests.length)}: ${menuRenderRequests.join(', ')}`,
    );

    // --- Neutral 404 for an unresolved host.
    const unknown = await request(appPort, '/', unknownHost);
    check('unknown host: HTTP 404', unknown.status === 404);
    check(
      'unknown host: neutral body (no tenant data, no cause)',
      unknown.body.includes('Page not found') &&
        !unknown.body.includes('Verify Kitchen'),
    );
    check(
      'unknown host: no-store',
      unknown.headers['cache-control'] === 'no-store',
    );
    check('unknown host: noindex', unknown.body.includes('noindex'));

    // --- robots / sitemap per host.
    const robots = await request(appPort, '/robots.txt', tenantHost);
    check(
      'robots: tenant host allows and advertises sitemap',
      robots.status === 200 &&
        robots.body.includes('Allow: /') &&
        robots.body.includes(`http://${tenantHost}/sitemap.xml`),
    );
    const robotsUnknown = await request(appPort, '/robots.txt', unknownHost);
    check(
      'robots: unknown host disallows',
      robotsUnknown.status === 200 &&
        robotsUnknown.body.includes('Disallow: /'),
    );
    const sitemap = await request(appPort, '/sitemap.xml', tenantHost);
    check(
      'sitemap: exactly the existing routes on the tenant origin',
      sitemap.status === 200 &&
        sitemap.body.includes(`<loc>http://${tenantHost}/</loc>`) &&
        sitemap.body.includes(`<loc>http://${tenantHost}/menu</loc>`) &&
        (sitemap.body.match(/<url>/g) ?? []).length === 2,
    );
    const sitemapUnknown = await request(appPort, '/sitemap.xml', unknownHost);
    check('sitemap: unknown host is 404', sitemapUnknown.status === 404);

    // --- The development API forwarder is disabled in production.
    const proxied = await request(appPort, '/api/v1/public/menu', tenantHost);
    check(
      'api forwarder: production-disabled with neutral 404',
      proxied.status === 404,
      String(proxied.status),
    );
    check(
      'api forwarder: no-store when disabled',
      proxied.headers['cache-control'] === 'no-store',
    );

    // --- Backend outage: generic error experience with a 500 status.
    stub.close();
    stubClosed = true;
    await new Promise((r) => setTimeout(r, 200));
    const outage = await request(appPort, '/', tenantHost);
    check('outage: HTTP 500', outage.status === 500, String(outage.status));
    // The visible "Something went wrong" copy hydrates via the client
    // error boundary (the one allowlisted client component); the server
    // document itself must be neutral, non-indexable, and disclosure-free.
    check(
      'outage: neutral non-indexable document, nothing disclosed',
      outage.body.includes('noindex') &&
        outage.body.includes('<title>Storefront</title>') &&
        !outage.body.includes('unavailable') &&
        !outage.body.includes('127.0.0.1') &&
        !outage.body.includes('Verify Kitchen'),
    );
    check(
      'outage: no-store',
      outage.headers['cache-control'] === 'no-store',
      String(outage.headers['cache-control']),
    );
  } finally {
    stop();
  }

  if (failures.length > 0) {
    console.error(`verify: ${String(failures.length)} check(s) failed`);
    process.exit(1);
  }
  console.log('verify: all built-server checks passed');
}

main().catch((error) => {
  console.error(`verify: ERROR ${error instanceof Error ? error.message : ''}`);
  process.exit(1);
});
