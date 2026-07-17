import path from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const desktopRoot = path.resolve(scriptDirectory, "..");

await build({
  entryPoints: [path.join(desktopRoot, "src", "preload", "index.ts")],
  outfile: path.join(desktopRoot, "dist", "preload", "index.cjs"),
  bundle: true,
  platform: "node",
  format: "cjs",
  target: "node22",
  external: ["electron"],
  sourcemap: true,
  minify: false,
  legalComments: "none",
});
