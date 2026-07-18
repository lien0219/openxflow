import { constants } from "node:fs";
import { access, mkdir } from "node:fs/promises";
import path from "node:path";

export interface DesktopPaths {
  root: string;
  config: string;
  database: string;
  files: string;
  components: string;
  plugins: string;
  logs: string;
  cache: string;
  backups: string;
}

export function createDesktopPaths(userDataPath: string): DesktopPaths {
  const root = path.resolve(userDataPath);
  return {
    root,
    config: path.join(root, "config"),
    database: path.join(root, "database"),
    files: path.join(root, "files"),
    components: path.join(root, "components"),
    plugins: path.join(root, "plugins"),
    logs: path.join(root, "logs"),
    cache: path.join(root, "cache"),
    backups: path.join(root, "backups"),
  };
}

export async function ensureDesktopPaths(paths: DesktopPaths): Promise<void> {
  const directories = Object.values(paths);
  await Promise.all(directories.map((directory) => mkdir(directory, { recursive: true })));
  await Promise.all(directories.map((directory) => access(directory, constants.R_OK | constants.W_OK)));
}

export function createBackendEnvironment(paths: DesktopPaths): NodeJS.ProcessEnv {
  return {
    PYTHONSAFEPATH: "1",
    LANGFLOW_CONFIG_DIR: paths.config,
    LANGFLOW_CACHE_DIR: paths.cache,
    LANGFLOW_DATABASE_URL: `sqlite:///${path.join(paths.database, "openxflow.db")}`,
    LANGFLOW_LOG_FILE: path.join(paths.logs, "openxflow.log"),
    LANGFLOW_LOG_LEVEL: process.env.OPENXFLOW_DESKTOP_LOG_LEVEL ?? "info",
    LANGFLOW_AUTO_LOGIN: process.env.LANGFLOW_AUTO_LOGIN ?? "true",
    OPENXFLOW_DESKTOP: "true",
  };
}
