import type { ThemePreset } from "@/types/theme";

export type DarkStoreType = {
  dark: boolean;
  themePreset: ThemePreset;
  stars: number;
  version: string;
  latestVersion: string;
  setDark: (dark: boolean) => void;
  setThemePreset: (themePreset: ThemePreset) => void;
  refreshVersion: (v: string) => void;
  refreshLatestVersion: (v: string) => void;
  refreshStars: () => void;
  discordCount: number;
  refreshDiscordCount: () => void;
};
