import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { expect, test } from "../../fixtures";
import { cleanAllFlows } from "../../utils/clean-all-flows";

const INVENTORY_PATH =
  "/api/v1/flows/?get_all=true&header_flows=true&remove_example_flows=true";

for (const scenario of [
  "flows and saved components",
  "saved components only",
  "already empty",
  "inventory failure",
  "malformed inventory",
  "delete failure",
  "incomplete deletion",
] as const) {
  test(
    `flow cleanup handles ${scenario}`,
    { tag: ["@release", "@api"] },
    async ({ browser }) => {
      const component = { id: "saved-component", is_component: true };
      const flow = { id: "user-flow", is_component: false };
      let inventory =
        scenario === "already empty"
          ? []
          : scenario === "saved components only"
            ? [component]
            : [flow, component];
      const deleted: string[][] = [];
      let inventoryReads = 0;
      let navigations = 0;
      const server = createServer(async (request, response) => {
        if (request.method === "GET" && request.url === INVENTORY_PATH) {
          inventoryReads++;
          response.writeHead(scenario === "inventory failure" ? 503 : 200, {
            "Content-Type": "application/json",
          });
          response.end(
            JSON.stringify(
              scenario === "malformed inventory"
                ? { flows: inventory }
                : inventory,
            ),
          );
          return;
        }
        if (request.method === "DELETE" && request.url === "/api/v1/flows/") {
          let body = "";
          for await (const chunk of request) body += chunk;
          const ids: string[] = JSON.parse(body);
          deleted.push(ids);
          response.writeHead(scenario === "delete failure" ? 500 : 200, {
            "Content-Type": "application/json",
          });
          if (scenario !== "incomplete deletion") {
            inventory = inventory.filter((item) => !ids.includes(item.id));
          }
          response.end(JSON.stringify({ deleted: ids.length }));
          return;
        }
        if (request.url !== "/flows") {
          response.writeHead(404);
          response.end();
          return;
        }
        navigations++;
        response.writeHead(200, { "Content-Type": "text/html" });
        response.end('<h1 data-testid="mainpage_title">Flows</h1>');
      });
      await new Promise<void>((resolve) =>
        server.listen(0, "127.0.0.1", resolve),
      );
      const { port } = server.address() as AddressInfo;
      const context = await browser.newContext({
        baseURL: `http://127.0.0.1:${port}`,
      });
      const page = await context.newPage();
      try {
        await page.goto("/flows");
        const failures: Partial<Record<typeof scenario, RegExp>> = {
          "inventory failure": /503/,
          "malformed inventory": /array/i,
          "delete failure": /500/,
          "incomplete deletion": /remain|empty|length/i,
        };
        const failure = failures[scenario];
        if (failure) {
          await expect(cleanAllFlows(page)).rejects.toThrow(failure);
          expect(navigations).toBe(1);
          if (
            scenario === "inventory failure" ||
            scenario === "malformed inventory"
          ) {
            expect(deleted).toEqual([]);
          }
        } else {
          await cleanAllFlows(page);
          expect(inventory).toEqual([]);
          expect(deleted).toEqual(
            scenario === "already empty"
              ? []
              : scenario === "saved components only"
                ? [["saved-component"]]
                : [["user-flow", "saved-component"]],
          );
          expect(inventoryReads).toBe(scenario === "already empty" ? 1 : 2);
          expect(navigations).toBe(2);
        }
      } finally {
        await context.close();
        await new Promise<void>((resolve, reject) =>
          server.close((error) => (error ? reject(error) : resolve())),
        );
      }
    },
  );
}
