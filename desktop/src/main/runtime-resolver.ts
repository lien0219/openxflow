import { existsSync } from "node:fs";
import path from "node:path";
import { DesktopError } from "./errors.js";

export interface RuntimePaths { pythonExecutable: string; frontendPath: string; workingDirectory: string }
type ResolveOptions = { isPackaged: boolean; resourcesPath: string; appPath: string };

export function resolveVirtualEnvironmentPython(root: string, platform: NodeJS.Platform = process.platform): string {
  return platform === "win32" ? path.join(root, "Scripts", "python.exe") : path.join(root, "bin", "python");
}

export function resolveDevelopmentPython(root: string, platform: NodeJS.Platform = process.platform): string {
  const names = platform === "win32" ? [".venv-win", ".venv"] : [".venv"];
  const candidates = names.map((name) => resolveVirtualEnvironmentPython(path.join(root, name), platform));
  return candidates.find((candidate) => existsSync(candidate)) ?? candidates[0]!;
}

export function resolveRuntimePaths(options: ResolveOptions): RuntimePaths {
  const configuredPython = process.env.OPENXFLOW_DESKTOP_PYTHON;
  const configuredFrontend = process.env.OPENXFLOW_DESKTOP_FRONTEND;
  const root = options.isPackaged ? path.join(options.resourcesPath, "runtime") : path.resolve(options.appPath, "..");
  return validate({
    pythonExecutable: configuredPython ? path.resolve(configuredPython) : options.isPackaged ? resolveVirtualEnvironmentPython(path.join(root, "python")) : resolveDevelopmentPython(root),
    frontendPath: configuredFrontend ? path.resolve(configuredFrontend) : options.isPackaged ? path.join(root, "frontend") : path.join(root, "src", "backend", "base", "langflow", "frontend"),
    workingDirectory: root,
  });
}

function validate(paths: RuntimePaths): RuntimePaths {
  for (const [label, value] of Object.entries(paths)) {
    if (!existsSync(value)) throw new DesktopError("RUNTIME_NOT_FOUND", `${label} was not found at ${value}.`);
  }
  return paths;
}
