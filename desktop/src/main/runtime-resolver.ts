import { existsSync } from "node:fs";
import path from "node:path";
import { DesktopError } from "./errors.js";

export interface RuntimePaths {
  pythonExecutable: string;
  frontendPath: string;
}

export function resolveRuntimePaths(options: {
  isPackaged: boolean;
  resourcesPath: string;
  appPath: string;
}): RuntimePaths {
  const configuredPython = process.env.OPENXFLOW_DESKTOP_PYTHON;
  const configuredFrontend = process.env.OPENXFLOW_DESKTOP_FRONTEND;

  if (configuredPython && configuredFrontend) {
    return validateRuntimePaths({
      pythonExecutable: path.resolve(configuredPython),
      frontendPath: path.resolve(configuredFrontend),
    });
  }

  if (options.isPackaged) {
    const runtimeRoot = path.join(options.resourcesPath, "runtime");
    return validateRuntimePaths({
      pythonExecutable: resolveVirtualEnvironmentPython(path.join(runtimeRoot, "python")),
      frontendPath: path.join(runtimeRoot, "frontend"),
    });
  }

  const repositoryRoot = path.resolve(options.appPath, "..");
  return validateRuntimePaths({
    pythonExecutable: resolveVirtualEnvironmentPython(path.join(repositoryRoot, ".venv")),
    frontendPath: path.join(repositoryRoot, "src", "backend", "base", "langflow", "frontend"),
  });
}

export function resolveVirtualEnvironmentPython(environmentRoot: string): string {
  return process.platform === "win32"
    ? path.join(environmentRoot, "Scripts", "python.exe")
    : path.join(environmentRoot, "bin", "python");
}

function validateRuntimePaths(paths: RuntimePaths): RuntimePaths {
  if (!existsSync(paths.pythonExecutable)) {
    throw new DesktopError(
      "RUNTIME_NOT_FOUND",
      `Python runtime was not found at ${paths.pythonExecutable}. Run the desktop runtime build first.`,
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
