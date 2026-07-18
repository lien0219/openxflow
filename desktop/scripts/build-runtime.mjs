import { access, cp, mkdir, rm, writeFile } from "node:fs/promises";
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

await access(path.join(frontendSource, "index.html")).catch(() => {
  throw new Error(
    "OpenXFlow frontend assets are missing. Build the frontend before creating the desktop runtime.",
  );
});

await rm(runtimeRoot, { recursive: true, force: true });
await mkdir(runtimeRoot, { recursive: true });
await run("uv", ["python", "install", "3.12"]);
await run("uv", ["venv", "--python", "3.12", "--relocatable", pythonRoot]);
await run(
  "uv",
  ["sync", "--frozen", "--no-dev", "--no-editable", "--extra", "postgresql"],
  {
    UV_PROJECT_ENVIRONMENT: pythonRoot,
    UV_COMPILE_BYTECODE: "1",
  },
);
await cp(frontendSource, frontendDestination, { recursive: true, force: true });
await writeFile(
  path.join(runtimeRoot, "runtime-manifest.json"),
  `${JSON.stringify(
    {
      schemaVersion: 1,
      python: "3.12",
      platform: process.platform,
      architecture: process.arch,
      installation: "uv-relocatable-venv",
      editable: false,
      createdAt: new Date().toISOString(),
    },
    null,
    2,
  )}\n`,
  "utf8",
);

async function run(command, args, extraEnvironment = {}) {
  await new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: repositoryRoot,
      env: { ...process.env, ...extraEnvironment },
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
