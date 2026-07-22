import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactFlowProvider } from "@xyflow/react";
import { type ReactNode, useEffect } from "react";
import { useLocation } from "react-router-dom";
import { GradientWrapper } from "@/components/common/GradientWrapper";
import { CustomWrapper } from "@/customization/custom-wrapper";
import { ENABLE_CUSTOM_PARAM } from "@/customization/feature-flags";
import { TooltipProvider } from "../components/ui/tooltip";
import { ApiInterceptor } from "../controllers/API/api";
import { AuthProvider } from "./authContext";

export const queryClient = new QueryClient();

type ThemeScene =
  | "auth"
  | "collection"
  | "editor"
  | "playground"
  | "settings"
  | "admin"
  | "library"
  | "viewer";

const ROUTE_ROOTS = new Set([
  "account",
  "admin",
  "all",
  "assets",
  "components",
  "flow",
  "flows",
  "login",
  "mcp",
  "playground",
  "settings",
  "signup",
]);

const normalizeThemePath = (pathname: string): string => {
  const segments = pathname.toLowerCase().split("/").filter(Boolean);

  if (
    ENABLE_CUSTOM_PARAM &&
    segments.length > 0 &&
    !ROUTE_ROOTS.has(segments[0])
  ) {
    segments.shift();
  }

  return `/${segments.join("/")}`;
};

const resolveThemeScene = (pathname: string): ThemeScene => {
  const path = normalizeThemePath(pathname);

  if (path.startsWith("/playground/")) return "playground";
  if (path.startsWith("/flow/")) {
    return path.endsWith("/view") ? "viewer" : "editor";
  }
  if (path.startsWith("/settings")) return "settings";
  if (path.startsWith("/admin")) return "admin";
  if (
    path.startsWith("/login") ||
    path.startsWith("/signup") ||
    path.startsWith("/account/delete")
  ) {
    return "auth";
  }
  if (
    path.startsWith("/assets/") ||
    path.includes("knowledge-bases") ||
    path.includes("/files")
  ) {
    return "library";
  }

  return "collection";
};

function ThemeSceneController() {
  const { pathname } = useLocation();

  useEffect(() => {
    document.documentElement.dataset.themeScene = resolveThemeScene(pathname);
  }, [pathname]);

  return null;
}

export default function ContextWrapper({ children }: { children: ReactNode }) {
  return (
    <CustomWrapper>
      <GradientWrapper>
        <QueryClientProvider client={queryClient}>
          <AuthProvider>
            <TooltipProvider skipDelayDuration={0}>
              <ReactFlowProvider>
                <ApiInterceptor />
                <ThemeSceneController />
                {children}
              </ReactFlowProvider>
            </TooltipProvider>
          </AuthProvider>
        </QueryClientProvider>
      </GradientWrapper>
    </CustomWrapper>
  );
}
