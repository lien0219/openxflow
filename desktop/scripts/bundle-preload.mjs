import { build } from "esbuild";

await build({
  entryPoints: [new URL("../src/preload/index.ts", import.meta.url).pathname],
  outfile: new URL("../dist/preload/index.cjs", import.meta.url).pathname,
  bundle: true,
  platform: "node",
  format: "cjs",
  target: "node22",
  external: ["electron"],
  sourcemap: true,
  minify: false,
  legalComments: "none",
});
