import type { BrowserWindow, WebContents } from "electron";

export function isAllowedExternalUrl(rawUrl: string): boolean {
  try {
    const url = new URL(rawUrl);
    return url.protocol === "https:" || url.protocol === "mailto:";
  } catch {
    return false;
  }
}

export function installNavigationGuards(
  window: BrowserWindow,
  applicationOrigin: string,
  openExternal: (url: string) => Promise<void>,
): void {
  const allowedOrigin = new URL(applicationOrigin).origin;
  const contents = window.webContents;

  contents.on("will-navigate", (event, targetUrl) => {
    const target = new URL(targetUrl);
    if (target.origin !== allowedOrigin) {
      event.preventDefault();
      if (isAllowedExternalUrl(targetUrl)) {
        void openExternal(targetUrl);
      }
    }
  });

  contents.setWindowOpenHandler(({ url }) => {
    if (isAllowedExternalUrl(url)) {
      void openExternal(url);
    }
    return { action: "deny" };
  });

  contents.on("will-attach-webview", (event) => event.preventDefault());
}

export function disableUntrustedPermissions(contents: WebContents): void {
  contents.session.setPermissionRequestHandler((_webContents, _permission, callback) => {
    callback(false);
  });
}
