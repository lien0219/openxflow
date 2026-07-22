import { Outlet } from "react-router-dom";
import AppHeader from "@/components/core/appHeaderComponent";
import useTheme from "@/customization/hooks/use-custom-theme";

export function DashboardWrapperPage() {
  useTheme();

  return (
    <div
      className="flex h-screen w-full flex-col overflow-hidden"
      data-theme-shell="dashboard"
    >
      <div data-theme-region="header">
        <AppHeader />
      </div>
      <div
        className="flex w-full flex-1 flex-row overflow-hidden"
        data-theme-region="workspace"
      >
        <Outlet />
      </div>
    </div>
  );
}
