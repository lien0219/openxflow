import assert from "node:assert/strict";
import { createRequire } from "node:module";
import path from "node:path";
import { test } from "node:test";
import { pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);
const parserRoot = path.dirname(require.resolve("chromium-bidi"));
const { Browser } = await import(
  pathToFileURL(path.join(parserRoot, "protocol-parser", "protocol-parser.js"))
    .href
);

test("Chromium BiDi converts invalid parameters into protocol errors", () => {
  assert.throws(
    () =>
      Browser.parseCreateUserContextParameters({
        acceptInsecureCerts: "invalid",
      }),
    (error) => error.constructor.name === "InvalidArgumentException",
  );
});
