import type { ThemePreset } from "@/types/theme";

export type DarkStoreType = {
  dark: boolean;
  themePreset: ThemePreset;
  stars: number;
  version: string;
  imageVersion: string | null;
  latestVersion: string;
  setDark: (dark: boolean) => void;
  setThemePreset: (themePreset: ThemePreset) => void;
  refreshVersion: (v: string) => void;
  refreshImageVersion: (v: string | null) => void;
  refreshLatestVersion: (v: string) => void;
  refreshStars: () => void;
  discordCount: number;
  refreshDiscordCount: () => void;
};
