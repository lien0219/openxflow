import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";
import { createBackendEnvironment, createDesktopPaths } from "../src/main/path-manager.js";

test("createDesktopPaths keeps all mutable data under userData", () => {
  const root = path.resolve("tmp", "OpenXFlow User");
  const paths = createDesktopPaths(root);
  for (const value of Object.values(paths)) {
    assert.equal(value === root || value.startsWith(`${root}${path.sep}`), true);
  }
});

test("createBackendEnvironment uses loopback-safe writable locations", () => {
  const paths = createDesktopPaths(path.resolve("tmp", "OpenXFlow"));
  const environment = createBackendEnvironment(paths);
  assert.equal(environment.OPENXFLOW_DESKTOP, "true");
  assert.match(environment.LANGFLOW_DATABASE_URL ?? "", /^sqlite:\/\/\//);
  assert.equal(environment.LANGFLOW_CONFIG_DIR, paths.config);
  assert.equal(environment.LANGFLOW_CACHE_DIR, paths.cache);
});
