import { contextBridge, ipcRenderer } from "electron";
import {
  IPC_CHANNELS,
  type DesktopBridge,
  type DesktopPlatform,
  type RuntimeStatus,
} from "../shared/contracts.js";

const platform: DesktopPlatform =
  process.platform === "win32" ? "windows" : process.platform === "darwin" ? "macos" : "linux";

const bridge: DesktopBridge = Object.freeze({
  platform,
  getAppVersion: async (): Promise<string> => await ipcRenderer.invoke(IPC_CHANNELS.appVersion),
  getRuntimeStatus: async (): Promise<RuntimeStatus> =>
    await ipcRenderer.invoke(IPC_CHANNELS.runtimeStatus),
  restartRuntime: async (): Promise<RuntimeStatus> =>
    await ipcRenderer.invoke(IPC_CHANNELS.runtimeRestart),
  selectFiles: async (): Promise<string[]> => await ipcRenderer.invoke(IPC_CHANNELS.selectFiles),
  selectDirectory: async (): Promise<string | null> =>
    await ipcRenderer.invoke(IPC_CHANNELS.selectDirectory),
  showItemInFolder: async (targetPath: string): Promise<void> =>
    await ipcRenderer.invoke(IPC_CHANNELS.showItemInFolder, targetPath),
  openExternal: async (url: string): Promise<void> =>
    await ipcRenderer.invoke(IPC_CHANNELS.openExternal, url),
  openLogsDirectory: async (): Promise<void> =>
    await ipcRenderer.invoke(IPC_CHANNELS.openLogsDirectory),
});

contextBridge.exposeInMainWorld("openxflowDesktop", bridge);
