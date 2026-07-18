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

child.once("exit",