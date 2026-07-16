// Custom Hook to manage theme logic

import { useEffect, useState } from "react";
import type { ThemePreference } from "@/types/theme";
import { useDarkStore } from "@/stores/darkStore";

const useTheme = () => {
  const [systemTheme, setSystemTheme] = useState(false);
  const { setDark, dark, themePreset, setThemePreset } = useDarkStore(
    (state) => ({
      setDark: state.setDark,
      dark: state.dark,
      themePreset: state.themePreset,
      setThemePreset: state.setThemePreset,
    }),
  );

  const handleSystemTheme = () => {
    if (typeof window !== "undefined") {
      const systemDarkMode = window.matchMedia(
        "(prefers-color-scheme: dark)",
      ).matches;
      setDark(systemDarkMode);
    }
  };

  useEffect(() => {
    const themePreference = localStorage.getItem(
      "themePreference",
    ) as ThemePreference | null;
    if (themePreference === "light") {
      setDark(false);
      setSystemTheme(false);
    } else if (themePreference === "dark") {
      setDark(true);
      setSystemTheme(false);
    } else {
      setSystemTheme(true);
      handleSystemTheme();
    }
  }, []);

  useEffect(() => {
    if (systemTheme && typeof window !== "undefined") {
      const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
      const handleChange = (event: MediaQueryListEvent) => {
        setDark(event.matches);
      };
      mediaQuery.addEventListener("change", handleChange);
      return () => {
        mediaQuery.removeEventListener("change", handleChange);
      };
    }
  }, [systemTheme, setDark]);

  const setThemePreference = (theme: ThemePreference) => {
    if (theme === "light") {
      setDark(false);
      setSystemTheme(false);
    } else if (theme === "dark") {
      setDark(true);
      setSystemTheme(false);
    } else {
      setSystemTheme(true);
      handleSystemTheme();
    }
    localStorage.setItem("themePreference", theme);
  };

  return {
    systemTheme,
    dark,
    themePreset,
    setThemePreset,
    setThemePreference,
  };
};

export default useTheme;
