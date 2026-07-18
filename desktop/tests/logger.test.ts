import assert from "node:assert/strict";
import test from "node:test";
import { sanitizeLogValue } from "../src/main/logger.js";

test("redacts secrets recursively without mutating safe values", () => {
  const sanitized = sanitizeLogValue({
    apiKey: "secret-value",
    nested: {
      authorization: "Bearer token",
      model: "gpt-test",
    },
    values: [{ password: "hidden", name: "safe" }],
  });

  assert.deepEqual(sanitized, {
    apiKey: "[REDACTED]",
    nested: {
      authorization: "[REDACTED]",
      model: "gpt-test",
    },
    values: [{ password: "[REDACTED]", name: "safe" }],
  });
});
