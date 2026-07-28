import {
  type ModelProviderInfo,
  normalizeModelProviderStatus,
} from "../use-get-model-providers";

const buildProvider = (
  overrides: Partial<ModelProviderInfo> = {},
): ModelProviderInfo => ({
  provider: "OpenAI",
  models: [],
  is_enabled: false,
  is_configured: false,
  ...overrides,
});

describe("normalizeModelProviderStatus", () => {
  it("keeps configured providers available to model pickers", () => {
    const provider = normalizeModelProviderStatus(
      buildProvider({ is_enabled: false, is_configured: true }),
    );

    expect(provider.is_enabled).toBe(true);
  });

  it("keeps unconfigured and disabled providers unavailable", () => {
    const provider = normalizeModelProviderStatus(buildProvider());

    expect(provider.is_enabled).toBe(false);
  });

  it("preserves explicitly enabled providers", () => {
    const provider = normalizeModelProviderStatus(
      buildProvider({ is_enabled: true, is_configured: false }),
    );

    expect(provider.is_enabled).toBe(true);
  });

  it("adds the provider icon fallback", () => {
    const provider = normalizeModelProviderStatus(
      buildProvider({ provider: "Google Generative AI", icon: undefined }),
    );

    expect(provider.icon).toBe("GoogleGenerativeAI");
  });
});
