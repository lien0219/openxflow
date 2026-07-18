import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {
  resolveDevelopmentPython,
  resolveVirtualEnvironmentPython,
} from "../src/main/runtime-resolver.js";

test("resolveVirtualEnvironmentPython uses platform-native executable paths", () => {
  const root = path.resolve("tmp", "environment");
  assert.equal(
    resolveVirtualEnvironmentPython(root, "win32"),
    path.join(root, "Scripts", "python.exe"),
  );
  assert.equal(resolveVirtualEnvironmentPython(root, "linux"), path.join(root, "bin", "python"));
});

test("resolveDevelopmentPython prefers the dedicated Windows environment", () => {
  const root = mkdtempSync(path.join(os.tmpdir(), "openxflow-runtime-"));
  try {
    const windowsPython = path.join(root, ".venv-win", "Scripts", "python.exe");
    const fallbackPython = path.join(root, ".venv", "Scripts", "python.exe");
    mkdirSync(path.dirname(windowsPython), { recursive: true });
    mkdirSync(path.dirname(fallbackPython), { recursive: true });
    writeFileSync(windowsPython, "");
    writeFileSync(fallbackPython, "");

    assert.equal(resolveDevelopmentPython(root, "win32"), windowsPython);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("resolveDevelopmentPython falls back to a native .venv on Windows", () => {
  const root = mkdtempSync(path.join(os.tmpdir(), "openxflow-runtime-"));
  try {
    const fallbackPython = path.join(root, ".venv", "Scripts", "python.exe");
    mkdirSync(path.dirname(fallbackPython), { recursive: true });
    writeFileSync(fallbackPython, "");

    assert.equal(resolveDevelopmentPython(root, "win32"), fallbackPython);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
