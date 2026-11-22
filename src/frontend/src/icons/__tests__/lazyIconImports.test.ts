const mockVllmIcon = jest.fn();
const mockOpenRAGIcon = jest.fn();
const mockFigraniumIcon = jest.fn();
const mockModuRelayIcon = jest.fn();

jest.mock("@/icons/vLLM", () => ({
  VllmIcon: mockVllmIcon,
}));

jest.mock("@/icons/OpenRAG", () => ({
  OpenRAGIcon: mockOpenRAGIcon,
}));

jest.mock("@/icons/Figranium", () => ({
  FigraniumIcon: mockFigraniumIcon,
}));

jest.mock("@/icons/ModuRelay", () => ({
  ModuRelayIcon: mockModuRelayIcon,
}));

import { lazyIconsMapping } from "../lazyIconImports";

describe("lazyIconsMapping", () => {
  it("loads the vLLM provider icon", async () => {
    const { default: icon } = await lazyIconsMapping.vLLM();

    expect(icon).toBe(mockVllmIcon);
  });

  it("loads the OpenRAG icon", async () => {
    const { default: icon } = await lazyIconsMapping.OpenRAG();

    expect(icon).toBe(mockOpenRAGIcon);
  });

  it("loads the Figranium bundle icon", async () => {
    const { default: icon } = await lazyIconsMapping.Figranium();

    expect(icon).toBe(mockFigraniumIcon);
  });

  it("loads the ModuRelay provider icon", async () => {
    expect(lazyIconsMapping).toHaveProperty("ModuRelay");
    const { default: icon } = await lazyIconsMapping.ModuRelay();

    expect(icon).toBe(mockModuRelayIcon);
  });
});
