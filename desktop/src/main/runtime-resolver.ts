import { existsSync } from "node:fs";
import path from "node:path";
import { DesktopError } from "./errors.js";

export interface RuntimePaths {
  pythonExecutable: string;
  frontendPath: string;
  workingDirectory: string;
}

type ResolveOptions = {
  isPackaged: boolean;
  resourcesPath: string;
  appPath: string;
};

export function resolveRuntimePaths(options: Resolve