import { existsSync } from "node:fs";
import path from "node:path";
import { DesktopError } from "./errors.js";

export interface RuntimePaths { pythonExecutable: string; frontendPath: string; workingDirectory: string }
type ResolveOptions = { isPackaged: boolean; resourcesPath: string; appPath: string };

export function resolveRuntimePaths(o: ResolveOptions): RuntimePaths {
  const configuredPython = process.env.OPENXFLOW_DESKTOP_PYTHON;
  const configuredFrontend = process.env.OPENXFLOW_DESKTOP_FRONTEND;
  if (o.isPackaged) {
    const root = path.join(o.resourcesPath, "runtime");
    return validate({
      pythonExecutable: configuredPython ? path.resolve(configuredPython) : venvPython(path.join(root, "python")),
      frontendPath: configuredFrontend ? path.resolve(configuredFrontend) : path.join(root, "frontend"),
      workingDirectory: root,
    });
  }
  const root = path.resolve(o.appPath, "..");
  return validate({
    pythonExecutable: configuredPython ? path.resolve(configuredPython) : developmentPython(root),
    frontendPath: configuredFrontend ? path.resolve(configuredFrontend) : path.join(root, "src", "backend", "base", "langflow", "frontend"),
    workingDirectory: root,
  });
}

export function venvPython(root: string, platform: NodeJS.Platform = process.platform): string {
  return platform === "win32" ? path.join(root, "Scripts", "python.exe") : path.join(root, "bin", "python");
}

export function developmentPython(root: string, platform: NodeJS.Platform = process.platform): string {
  const names = platform === "win32" ? [".venv-win", ".venv"] : [".venv"];
  const candidates = names.map((name) => venvPython(path.join(root, name), platform));
  return candidates.find(existsSync) ?? candidates[0]!;
}

function validate(p: RuntimePaths): RuntimePaths {
  if (!existsSync(p.pythonExecutable)) throw new DesktopError("RUNTIME_NOT_FOUND", `Python runtime was not found at ${p.pythonExecutable}.`);
  if (!existsSync(p.frontendPath)) throw new DesktopError("RUNTIME_NOT_FOUND", `Frontend assets were not found at ${p.frontendPath}.`);
  if (!existsSync(p.workingDirectory)) throw new DesktopError("RUNTIME_NOT_FOUND", `Runtime working directory was not found at ${p.workingDirectory}.`);
  return p;
}
