import { cp, mkdir, rm, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = path.resolve(desktopRoot, "..");
const runtimeRoot = path.join(desktopRoot, "resources", "runtime");
const pythonRoot = path.join(runtimeRoot, "python");
const frontendSource = path.join(repositoryRoot, "src", "backend", "base", "langflow", "frontend");
const frontendDestination = path.join(runtimeRoot, "frontend");

await rm(runtimeRoot, { recursive: true, force: true });
await mkdir(runtimeRoot, { recursive: true });

await run("uv", ["python", "install", "3.12"]);
await run("uv", ["venv", "--python", "3.12", pythonRoot]);
const runtimePython =
  process.platform === "win32"
    ? path.join(pythonRoot, "Scripts", "python.exe")
    : path.join(pythonRoot, "bin", "python");

await run("uv", ["pip", "install", "--python", runtimePython, "--editable", repositoryRoot]);
await cp(frontendSource, frontendDestination, { recursive: true, force: true });
await writeFile(
  path.join(runtimeRoot, "runtime-manifest.json"),
  `${JSON.stringify(
    {
      schemaVersion: 1,
      python: "3.12",
      platform: process.platform,
      architecture: process.arch,
      createdAt: new Date().toISOString(),
    },
    null,
    2,
  )}\n`,
  "utf8",
);

async function run(command, args) {
  await new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: repositoryRoot,
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
