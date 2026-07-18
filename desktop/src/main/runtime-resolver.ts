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
  const configuredPython = process.env.OPENXFLOW