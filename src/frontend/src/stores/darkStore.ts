import { create } from "zustand";
import { DEFAULT_THEME_PRESET, isThemePreset } from "@/types/theme";
import { getDiscordCount, getRepoStars } from "../controllers/API";
import type { DarkStoreType } from "../types/zustand/dark";

const getStoredValue = (key: string): string | null => {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
};

const setStoredValue = (key: string, value: string) => {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Theme state still works for the current session when storage is blocked.
  }
};

const startedStars = Number(getStoredValue("githubStars")) || 0;
const storedThemePreset = getStoredValue("themePreset");

export const useDarkStore = create<DarkStoreType>((set, get) => ({
  dark: (() => {
    const stored = getStoredValue("isDark");
    if (stored !== null) return JSON.parse(stored);
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  })(),
  themePreset: isThemePreset(storedThemePreset)
    ? storedThemePreset
    : DEFAULT_THEME_PRESET,
  stars: startedStars,
  version: "",
  latestVersion: "",
  refreshLatestVersion: (v: string) => {
    set(() => ({ latestVersion: v }));
  },
  setDark: (dark) => {
    set(() => ({ dark }));
    setStoredValue("isDark", dark.toString());
  },
  setThemePreset: (themePreset) => {
    set(() => ({ themePreset }));
    setStoredValue("themePreset", themePreset);
  },
  refreshVersion: (v) => {
    set(() => ({ version: v }));
  },
  refreshStars: () => {
    if (import.meta.env.CI) {
      setStoredValue("githubStars", "0");
      set(() => ({ stars: 0, lastUpdated: new Date() }));
      return;
    }
    const lastUpdated = getStoredValue("githubStarsLastUpdated");
    let diff = 0;
    if (lastUpdated !== null) {
      diff = Math.abs(new Date().getTime() - new Date(lastUpdated).getTime());
    }
    if (lastUpdated === null || diff > 7200000) {
      getRepoStars("lien0219", "openxflow").then((res) => {
        setStoredValue("githubStars", res?.toString() ?? "0");
        setStoredValue("githubStarsLastUpdated", new Date().toString());
        set(() => ({ stars: res, lastUpdated: new Date() }));
      });
    }
  },
  discordCount: 0,
  refreshDiscordCount: () => {
    getDiscordCount().then((res) => {
      set(() => ({ discordCount: res }));
    });
  },
}));
