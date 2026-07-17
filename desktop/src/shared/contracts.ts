export type DesktopPlatform = "windows" | "macos" | "linux";

export type BackendStatus =
  | "idle"
  | "starting"
  | "ready"
  | "stopping"
  | "stopped"
  | "failed";

export interface RuntimeStatus {
  status: BackendStatus;
  port: number | null;
  pid: number | null;
  startedAt: string | null;
  lastError: string | null;
}

export interface DesktopBridge {
  readonly platform: DesktopPlatform;
  getAppVersion(): Promise<string>;
  getRuntimeStatus(): Promise<RuntimeStatus>;
  restartRuntime(): Promise<RuntimeStatus>;
  selectFiles(): Promise<string[]>;
  selectDirectory(): Promise<string | null>;
  showItemInFolder(path: string): Promise<void>;
  openExternal(url: string): Promise<void>;
  openLogsDirectory(): Promise<void>;
}

export const IPC_CHANNELS = {
  appVersion: "desktop:app-version",
  runtimeStatus: "desktop:runtime-status",
  runtimeRestart: "desktop:runtime-restart",
  selectFiles: "desktop:select-files",
  selectDirectory: "desktop:select-directory",
  showItemInFolder: "desktop:show-item-in-folder",
  openExternal: "desktop:open-external",
  openLogsDirectory: "desktop:open-logs-directory",
} as const;
