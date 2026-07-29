import type { ReactNode } from "react";
import { CustomNavigate } from "@/customization/components/custom-navigate";
import { useRbacAccess } from "@/hooks/use-rbac-access";
import { LoadingPage } from "@/pages/LoadingPage";

export function ProtectedPermissionRoute({ children }: { children: ReactNode }) {
  const { canReadRbac, isLoading } = useRbacAccess();

  if (isLoading) return <LoadingPage />;
  if (!canReadRbac) return <CustomNavigate to="/" replace />;
  return children;
}
