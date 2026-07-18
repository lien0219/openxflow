import path from "node:path";
import { dialog, ipcMain, shell, type App } from "electron";
import { IPC_CHANNELS } from "../shared/contracts.js";
import type { BackendManager } from "./backend-manager.js";
import { DesktopError } from "./errors.js";
import { isAllowedExternalUrl } from "./security.js";

export interface IpcDependencies {
  app: App;
  backendManager: BackendManager;
  logsDirectory: string;
}

export function registerIpcHandlers(dependencies: IpcDependencies): () => void {
  ipcMain.handle(IPC_CHANNELS.appVersion, () => dependencies.app.getVersion());
  ipcMain.handle(IPC_CHANNELS.runtimeStatus, () => dependencies.backendManager.getStatus());
  ipcMain.handle(IPC_CHANNELS.runtimeRestart, async () => await dependencies.backendManager.restart());
  ipcMain.handle(IPC_CHANNELS.selectFiles, async () => {
    const result = await dialog.showOpenDialog({ properties: ["openFile", "multiSelections"] });
    return result.canceled ? [] : result.filePaths;
  });
  ipcMain.handle(IPC_CHANNELS.selectDirectory, async () => {
    const result = await dialog.showOpenDialog({ properties: ["openDirectory", "createDirectory"] });
    return result.canceled ? null : (result.filePaths[0] ?? null);
  });
  ipcMain.handle(IPC_CHANNELS.showItemInFolder, (_event, targetPath: unknown) => {
    const safePath = requireAbsolutePath(targetPath);
    shell.showItemInFolder(safePath);
  });
  ipcMain.handle(IPC_CHANNELS.openExternal, async (_event, rawUrl: unknown) => {
    if (typeof rawUrl !== "string" || !isAllowedExternalUrl(rawUrl)) {
      throw new DesktopError("IPC_VALIDATION_FAILED", "Only HTTPS and mailto links are allowed.");
    }
    await shell.openExternal(rawUrl);
  });
  ipcMain.handle(IPC_CHANNELS.openLogsDirectory, async () => {
    await shell.openPath(dependencies.logsDirectory);
  });

  return () => {
    for (const channel of Object.values(IPC_CHANNELS)) {
      ipcMain.removeHandler(channel);
    }
  };
}

function requireAbsolutePath(value: unknown): string {
  if (typeof value !== "string" || value.length === 0 || !path.isAbsolute(value)) {
    throw new DesktopError("IPC_VALIDATION_FAILED", "An absolute file system path is required.");
  }
  return path.normalize(value);
}
