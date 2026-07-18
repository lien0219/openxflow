import { access } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const requiredFiles = [
  path.join(desktopRoot, "dist", "main", "index.js"),
  path.join(desktopRoot, "dist", "preload", "index.cjs"),
  path.join(desktopRoot, "dist", "loading", "index.html"),
  path.join(desktopRoot, "dist", "loading", "error.html"),
];

for (const file of requiredFiles) {
  try {
    await access(file);
  } catch {
    throw new Error(`Required desktop build artifact is missing: ${file}`);
  }
}

console.log("Desktop build artifacts verified.");
