import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import electronExecutable from "electron";

const desktopRoot = fileURLToPath(new URL("..", import.meta.url));
const child = spawn(electronExecutable, ["."], {
  cwd: desktopRoot,
  env: process.env,
  stdio: "inherit",
  shell: false,
});

child.once("exit", (code, signal) => {
  if (signal) {
    console.error(`Electron exited because of signal ${signal}`);
    process.exit(1);
  }
  process.exit(code ?? 1);
});

child.once("error", (error) => {
  console.error("Failed to start Electron:", error);
  process.exit(1);
});
