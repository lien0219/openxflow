import assert from "node:assert/strict";
import test from "node:test";
import { isAllowedExternalUrl } from "../src/main/security.js";

test("allows HTTPS and mailto external links", () => {
  assert.equal(isAllowedExternalUrl("https://openxflow.dev/docs"), true);
  assert.equal(isAllowedExternalUrl("mailto:support@example.com"), true);
});

test("rejects executable and insecure protocols", () => {
  assert.equal(isAllowedExternalUrl("http://example.com"), false);
  assert.equal(isAllowedExternalUrl("file:///tmp/test"), false);
  assert.equal(isAllowedExternalUrl("javascript:alert(1)"), false);
  assert.equal(isAllowedExternalUrl("not-a-url"), false);
});
