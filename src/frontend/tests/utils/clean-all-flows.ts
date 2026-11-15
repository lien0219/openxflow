import { expect, type Page } from "@playwright/test";
import { TIMEOUTS } from "./constants/timeouts";

export const cleanAllFlows = async (page: Page) => {
  // The flow-card list excludes saved components. A leftover component keeps
  // the project shell visible even after its last flow card has been deleted.
  // Read the complete user inventory and preserve the global starter examples.
  const readInventory = async (): Promise<Array<{ id: string }>> => {
    const response = await page.request.get(
      "/api/v1/flows/?get_all=true&header_flows=true&remove_example_flows=true",
    );
    expect(
      response.ok(),
      `Reading cleanup inventory returned ${response.status()}`,
    ).toBe(true);
    const inventory = await response.json();
    expect(Array.isArray(inventory), "Cleanup inventory must be an array").toBe(
      true,
    );
    for (const item of inventory) {
      expect(typeof item?.id, "Cleanup inventory must contain flow ids").toBe(
        "string",
      );
      expect(item.id.length).toBeGreaterThan(0);
    }
    return inventory;
  };
  const inventory = await readInventory();
  if (inventory.length > 0) {
    const response = await page.request.delete("/api/v1/flows/", {
      data: inventory.map(({ id }) => id),
    });
    expect(
      response.ok(),
      `Deleting cleanup inventory returned ${response.status()}`,
    ).toBe(true);
    await response.body();
    expect(
      await readInventory(),
      "Flows or saved components remain after cleanup",
    ).toHaveLength(0);
  }

  // API cleanup bypasses the React mutation callbacks; reload their stores.
  await page.reload();
  await expect(page.getByTestId("mainpage_title").last()).toBeVisible({
    timeout: TIMEOUTS.standard,
  });
};
