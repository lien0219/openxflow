import { existsSync } from "node:fs";
import path from "node:path";
import { DesktopError } from "./errors.js";

export interface RuntimePaths {
  pythonExecutable: string;
  frontendPath: string;
}

type ResolveOptions = {
  isPackaged: boolean;
  resourcesPath: string;
  appPath: string;
};

export function resolveRuntimePaths(options: ResolveOptions): RuntimePaths {
  const configuredPython = process.env.OPENXFLOW_DESKTOP_PYTHON;
  const configuredFrontend = process.env.OPENXFLOW_DESKTOP_FRONTEND;

  if (options.isPackaged) {
    const runtimeRoot = path.join(options.resourcesPath, "runtime");
    return validateRuntimePaths({
      pythonExecutable: configuredPython
        ? path.resolve(configuredPython)
        : resolveVirtualEnvironmentPython(path.join(runtimeRoot, "python")),
      frontendPath: configuredFrontend
        ? path.resolve(configuredFrontend)
        : path.join(runtimeRoot, "frontend"),
    });
  }

  const repositoryRoot = path.resolve(options.appPath, "..");
  return validateRuntimePaths({
    pythonExecutable: configuredPython
      ? path.resolve(configuredPython)
      : resolveDevelopmentPython(repositoryRoot),
    frontendPath: configuredFrontend
      ? path.resolve(configuredFrontend)
      : path.join(repositoryRoot, "src", "backend", "base", "langflow", "frontend"),
  });
}

export function resolveVirtualEnvironmentPython(
  environmentRoot: string,
  platform: NodeJS.Platform = process.platform,
): string {
  return platform === "win32"
    ? path.join(environmentRoot, "Scripts", "python.exe")
    : path.join(environmentRoot, "bin", "python");
}

export function resolveDevelopmentPython(
  repositoryRoot: string,
  platform: NodeJS.Platform = process.platform,
): string {
  const names = platform === "win32" ? [".venv-win", ".venv"] : [".venv"];
  const candidates = names.map((name) =>
    resolveVirtualEnvironmentPython(path.join(repositoryRoot, name), platform),
  );
  const existing = candidates.find((candidate) => existsSync(candidate));
  return existing ?? candidates[0]!;
}

function validateRuntimePaths(paths: RuntimePaths): RuntimePaths {
  if (!existsSync(paths.pythonExecutable)) {
    throw new DesktopError(
      "RUNTIME_NOT_FOUND",
      `Python runtime was not found at ${paths.pythonExecutable}. Create a platform-native development environment or set OPENXFLOW_DESKTOP_PYTHON.`,
    );
  }
  if (!existsSync(paths.frontendPath)) {
    throw new DesktopError(
      "RUNTIME_NOT_FOUND",
      `Frontend assets were not found at ${paths.frontendPath}. Build the OpenXFlow frontend first.`,
    );
  }
  return paths;
}
