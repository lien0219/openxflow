import { useEffect, useMemo, useState } from "react";
import { getIdentitySummary } from "@/controllers/API/queries/authz";
import useAuthStore from "@/stores/authStore";

export function useRbacAccess() {
  const isAdmin = useAuthStore((state) => state.isAdmin);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const autoLogin = useAuthStore((state) => state.autoLogin);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    if (!isAuthenticated || autoLogin) {
      setPermissions([]);
      setIsLoading(false);
      return () => {
        cancelled = true;
      };
    }

    setIsLoading(true);
    getIdentitySummary()
      .then((summary) => {
        if (!cancelled) setPermissions(summary.effective_permissions);
      })
      .catch(() => {
        if (!cancelled) setPermissions([]);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [autoLogin, isAuthenticated]);

  return useMemo(() => {
    const permissionSet = new Set(permissions);
    const canReadRbac =
      isAdmin || permissionSet.has("rbac:read") || permissionSet.has("rbac:*");
    const canManageRbac =
      isAdmin || permissionSet.has("rbac:manage") || permissionSet.has("rbac:*");
    const canAssignRbac =
      isAdmin || permissionSet.has("rbac:assign") || permissionSet.has("rbac:*");
    return {
      permissions,
      isLoading,
      canReadRbac,
      canManageRbac,
      canAssignRbac,
    };
  }, [isAdmin, isLoading, permissions]);
}
