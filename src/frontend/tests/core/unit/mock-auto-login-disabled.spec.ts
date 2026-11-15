import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { expect, test } from "../../fixtures";
import { mockAutoLoginDisabled } from "../../utils/auth/mock-auto-login-disabled";

test(
  "manual-login setup survives reloads without restoring a forced redirect",
  { tag: ["@release", "@api"] },
  async ({ page }) => {
    const server = createServer((_request, response) => {
      response.writeHead(200, { "Content-Type": "text/html" });
      response.end("<h1>Manual login fixture</h1>");
    });
    await new Promise<void>((resolve) =>
      server.listen(0, "127.0.0.1", resolve),
    );
    const { port } = server.address() as AddressInfo;
    const origin = `http://127.0.0.1:${port}`;
    try {
      await mockAutoLoginDisabled(page);
      await page.goto(`${origin}/flows`);
      // The caller clears this temporary flag after signing in. The init
      // script must not restore it on the next document.
      await page.evaluate(() => {
        sessionStorage.removeItem("testMockAutoLogin");
      });
      for (const navigation of ["reload", "new document"] as const) {
        if (navigation === "reload") await page.reload();
        else await page.goto(`${origin}/flows?after-login=true`);
        expect(
          await page.evaluate(() =>
            sessionStorage.getItem("testMockAutoLogin"),
          ),
          `Forced-login redirect must remain cleared after ${navigation}`,
        ).toBeNull();
        expect(
          await page.evaluate(() => window.process.env.LANGFLOW_AUTO_LOGIN),
        ).toBe("false");
        const autoLogin = await page.evaluate(async () => {
          const response = await fetch("/api/v1/auto_login");
          return { status: response.status, body: await response.json() };
        });
        expect(autoLogin.status).toBe(403);
        expect(autoLogin.body.detail.auto_login).toBe(false);
      }
    } finally {
      await page.goto("about:blank");
      await new Promise<void>((resolve, reject) =>
        server.close((error) => (error ? reject(error) : resolve())),
      );
    }
  },
);
