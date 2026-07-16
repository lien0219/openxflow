export const THEME_PRESETS = ["classic", "nebula"] as const;

export type ThemePreset = (typeof THEME_PRESETS)[number];
export type ThemePreference = "light" | "dark" | "system";

export const DEFAULT_THEME_PRESET: ThemePreset = "classic";
export const DEFAULT_THEME_PREFERENCE: ThemePreference = "system";

export const isThemePreset = (value: unknown): value is ThemePreset =>
  typeof value === "string" && THEME_PRESETS.includes(value as ThemePreset);
