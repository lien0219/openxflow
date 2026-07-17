import { spawn } from "node:child_process";

const child = spawn(process.platform === "win32" ? "electron.cmd" : "electron", ["."], {
  cwd: new URL("..", import.meta.url),
  env: process.env,
  stdio: "inherit",
  shell: false,
});

child.once("exit", (code) => process.exit(code ?? 1));
child.once("error", (error) => {
  console.error(error);
  process.exit(1);
});
