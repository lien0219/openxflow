import assert from "node:assert/strict";
import net from "node:net";
import test from "node:test";
import { allocateLoopbackPort } from "../src/main/port-manager.js";

test("allocates a reusable loopback port", async () => {
  const port = await allocateLoopbackPort();
  assert.equal(Number.isInteger(port), true);
  assert.equal(port > 0 && port <= 65_535, true);

  await new Promise<void>((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen({ host: "127.0.0.1", port }, () => {
      server.close((error) => (error ? reject(error) : resolve()));
    });
  });
});
