import { spawn } from "node:child_process";
import { cp, mkdir, rm } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = path.resolve(desktopRoot, "..");
const frontendRoot = path.join(repositoryRoot, "src", "frontend");
const buildRoot = path.join(frontendRoot, "build");
const backendFrontendRoot = path.join(repositoryRoot, "src", "backend", "base", "langflow", "frontend");

await runNpm(["ci"], frontendRoot);
await runNpm(["run", "build"], frontendRoot);
await rm(backendFrontendRoot, { recursive: true, force: true });
await mkdir(backendFrontendRoot, { recursive: true });
await cp(buildRoot, backendFrontendRoot, { recursive: true, force: true });

async function runNpm(args, cwd) {
  const command = process.platform === "win32" ? "npm.cmd" : "npm";
  await new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd,
      env: process.env,
      stdio: "inherit",
      shell: process.platform === "win32",
    });
    child.once("error", reject);
    child.once("exit", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`${command} exited with code ${String(code)}`));
    });
  });
}
