import { cp, mkdir } from "node:fs/promises";

const source = new URL("../resources/loading", import.meta.url);
const destination = new URL("../dist/loading", import.meta.url);

await mkdir(destination, { recursive: true });
await cp(source, destination, { recursive: true, force: true });
