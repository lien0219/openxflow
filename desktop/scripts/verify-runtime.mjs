import { access, readFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const runtimeRoot = path.join(desktopRoot, "resources", "runtime");
const python =
  process.platform === "win32"
    ? path.join(runtimeRoot, "python", "Scripts", "python.exe")
    : path.join(runtimeRoot, "python", "bin", "python");
const frontend = path.join(runtimeRoot, "frontend", "index.html");
const manifestPath = path.join(runtimeRoot, "runtime-manifest.json");

await Promise.all([access(python), access(frontend), access(manifestPath)]);
const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
if (manifest.schemaVersion !== 1) {
  throw new Error("Unsupported runtime manifest schema.");
}
if (manifest.platform !== process.platform || manifest.architecture !== process.arch) {
  throw new Error(
    `Runtime target mismatch: expected ${process.platform}/${process.arch}, got ${manifest.platform}/${manifest.architecture}`,
  );
}
console.log(`Runtime verified for ${manifest.platform}/${manifest.architecture}.`);
