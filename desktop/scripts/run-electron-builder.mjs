import { spawn } from "node:child_process";
import process from "node:process";
import { setTimeout as delay } from "node:timers/promises";

const mode = process.argv[2] ?? "pack";
const maxAttempts = Number.parseInt(
  process.env.OPENXFLOW_DESKTOP_BUILD_ATTEMPTS ?? "3",
  10,
);
const retryDelayMs = Number.parseInt(
  process.env.OPENXFLOW_DESKTOP_BUILD_RETRY_DELAY_MS ?? "5000",
  10,
);

if (!Number.isInteger(maxAttempts) || maxAttempts < 1 || maxAttempts > 10) {
  throw new Error(
    "OPENXFLOW_DESKTOP_BUILD_ATTEMPTS must be an integer between 1 and 10.",
  );
}

const args = mode === "pack" ? ["--dir"] : [];

for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
  const exitCode = await runBuilder(args);
  if (exitCode === 0) {
    process.exit(0);
  }

  if (attempt === maxAttempts) {
    process.exit(exitCode);
  }

  console.warn(
    `electron-builder failed with exit code ${exitCode}. Retrying in ${retryDelayMs}ms (${attempt}/${maxAttempts})...`,
  );
  await delay(retryDelayMs);
}

async function runBuilder(args) {
  return await new Promise((resolve, reject) => {
    const executable =
      process.platform === "win32"
        ? "node_modules\\.bin\\electron-builder.cmd"
        : "node_modules/.bin/electron-builder";
    const child = spawn(executable, args, {
      cwd: process.cwd(),
      env: process.env,
      stdio: "inherit",
      shell: process.platform === "win32",
    });
    child.once("error", reject);
    child.once("exit", (code) => resolve(code ?? 1));
  });
}
