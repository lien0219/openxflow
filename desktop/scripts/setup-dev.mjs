import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = path.resolve(desktopRoot, "..");
const pythonVersion = process.env.OPENXFLOW_DESKTOP_PYTHON_VERSION ?? "3.12";
const environmentName = process.platform === "win32" ? ".venv-win" : ".venv";
const environmentRoot = path.join(repositoryRoot, environmentName);
const pythonExecutable =
  process.platform === "win32"
    ? path.join(environmentRoot, "Scripts", "python.exe")
    : path.join(environmentRoot, "bin", "python");

console.log(`Preparing OpenXFlow desktop development environment (${environmentName})...`);

await run("uv", ["python", "install", pythonVersion], repositoryRoot);

const syncEnvironment = {
  ...process.env,
  UV_PROJECT_ENVIRONMENT: environmentRoot,
};

await run(
  "uv",
  ["sync", "--python", pythonVersion, "--frozen", "--extra", "postgresql"],
  repositoryRoot,
  syncEnvironment,
);

if (!existsSync(pythonExecutable)) {
  throw new Error(`Python environment was not created at ${pythonExecutable}`);
}

await run(process.platform === "win32" ? "npm.cmd" : "npm", ["run", "frontend:prepare"], desktopRoot);

console.log("OpenXFlow desktop development environment is ready.");
console.log(`Python: ${pythonExecutable}`);

if (process.argv.includes("--start")) {
  await run(
    process.platform === "win32" ? "npm.cmd" : "npm",
    ["run", "dev"],
    desktopRoot,
    {
      ...process.env,
      OPENXFLOW_DESKTOP_PYTHON: pythonExecutable,
    },
  );
}

async function run(command, args, cwd, env = process.env) {
  await new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd,
      env,
      stdio: "inherit",
      shell: process.platform === "win32" && command.endsWith(".cmd"),
    });

    child.once("error", (error) => {
      reject(new Error(`Failed to start ${command}: ${error.message}`, { cause: error }));
    });

    child.once("exit", (code, signal) => {
      if (signal) {
        reject(new Error(`${command} exited because of signal ${signal}`));
        return;
      }
      if (code === 0) {
        resolve();
        return;
      }
      reject(new Error(`${command} exited with code ${String(code)}`));
    });
  });
}
