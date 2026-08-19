import { Outlet } from "react-router-dom";
import AppHeader from "@/components/core/appHeaderComponent";
import { PermissionsProvider } from "@/contexts/permissionsContext";
import useTheme from "@/customization/hooks/use-custom-theme";
import useFlowStore from "@/stores/flowStore";

export function DashboardWrapperPage() {
  useTheme();
  const currentFlow = useFlowStore((state) => state.currentFlow);

  return (
    <PermissionsProvider
      resourceType="flow"
      resourceIds={currentFlow?.id ? [currentFlow.id] : []}
      domain={
        currentFlow?.folder_id ? `project:${currentFlow.folder_id}` : undefined
      }
    >
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
    </PermissionsProvider>
  );
}
