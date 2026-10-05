import { renderHook } from "@testing-library/react";
import { formatDocumentTitle, useDocumentTitle } from "../use-document-title";

describe("formatDocumentTitle", () => {
  it("brands the page title", () => {
    expect(formatDocumentTitle("Flows")).toBe("Flows | OpenXFlow");
  });

  it("does not double-brand a title that already names the product", () => {
    expect(formatDocumentTitle("OpenXFlow API Keys")).toBe(
      "OpenXFlow API Keys",
    );
  });

  it("falls back to the product name for an empty title", () => {
    expect(formatDocumentTitle(undefined)).toBe("OpenXFlow");
    expect(formatDocumentTitle(null)).toBe("OpenXFlow");
    expect(formatDocumentTitle("   ")).toBe("OpenXFlow");
  });
});

describe("useDocumentTitle", () => {
  it("sets the document title while mounted and resets it on unmount", () => {
    const { unmount } = renderHook(() => useDocumentTitle("Global Variables"));
    expect(document.title).toBe("Global Variables | OpenXFlow");

    unmount();
    expect(document.title).toBe("OpenXFlow");
  });

  it("follows a title that resolves after the first render", () => {
    const { rerender } = renderHook(
      ({ title }: { title?: string }) => useDocumentTitle(title),
      { initialProps: { title: undefined } },
    );
    expect(document.title).toBe("OpenXFlow");

    rerender({ title: "My Flow" });
    expect(document.title).toBe("My Flow | OpenXFlow");
  });
});
