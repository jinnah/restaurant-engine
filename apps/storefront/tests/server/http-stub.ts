// A live loopback HTTP stub for transport tests. Real sockets on an
// ephemeral port — these suites assert what actually travels on the wire
// (Host header, header stripping, status mapping), which a mocked fetch
// cannot prove.

import http from 'node:http';
import type { AddressInfo } from 'node:net';

export interface RecordedRequest {
  method: string;
  url: string;
  headers: http.IncomingHttpHeaders;
  /** Raw header names in arrival order (case preserved, no folding). */
  rawHeaderNames: string[];
  /** The received request body, decoded as UTF-8 (empty for GET/HEAD). */
  body: string;
}

export interface StubResponsePlan {
  status?: number;
  headers?: Record<string, string>;
  body?: string | Buffer;
  /** Delay before responding, to drive timeout behavior. */
  delayMs?: number;
}

export interface HttpStub {
  origin: string;
  requests: RecordedRequest[];
  /** Replace the response plan for subsequent requests. */
  respondWith(plan: StubResponsePlan): void;
  close(): Promise<void>;
}

export async function startHttpStub(
  initial: StubResponsePlan = {},
): Promise<HttpStub> {
  let plan = initial;
  const requests: RecordedRequest[] = [];
  const server = http.createServer((req, res) => {
    const chunks: Buffer[] = [];
    req.on('data', (chunk: Buffer) => chunks.push(chunk));
    req.on('end', () => {
      requests.push({
        method: req.method ?? '',
        url: req.url ?? '',
        headers: req.headers,
        rawHeaderNames: req.rawHeaders.filter((_, i) => i % 2 === 0),
        body: Buffer.concat(chunks).toString('utf-8'),
      });
      const send = (): void => {
        res.writeHead(plan.status ?? 200, {
          'content-type': 'application/json',
          ...plan.headers,
        });
        if (req.method === 'HEAD') {
          res.end();
        } else {
          res.end(plan.body ?? '{}');
        }
      };
      if (plan.delayMs !== undefined) {
        setTimeout(send, plan.delayMs);
      } else {
        send();
      }
    });
  });
  await new Promise<void>((resolve) => {
    server.listen(0, '127.0.0.1', resolve);
  });
  const address = server.address() as AddressInfo;
  return {
    origin: `http://127.0.0.1:${String(address.port)}`,
    requests,
    respondWith(next) {
      plan = next;
    },
    close() {
      return new Promise<void>((resolve, reject) => {
        server.close((error) => (error ? reject(error) : resolve()));
      });
    },
  };
}
