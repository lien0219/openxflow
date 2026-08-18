import { useCallback, useEffect, useMemo, useState } from "react";
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

  const permissionSet = useMemo(() => new Set(permissions), [permissions]);
  const hasPermission = useCallback(
    (permission: string) => {
      if (isAdmin) return true;
      const normalized = permission.trim().toLowerCase();
      const [resource] = normalized.split(":", 1);
      return (
        permissionSet.has(normalized) ||
        permissionSet.has(`${resource}:*`) ||
        permissionSet.has("*:*")
      );
    },
    [isAdmin, permissionSet],
  );

  return useMemo(
    () => ({
      permissions,
      isAdmin,
      isLoading,
      hasPermission,
      canReadRbac: hasPermission("rbac:read"),
      canManageRbac: hasPermission("rbac:manage"),
      canAssignRbac: hasPermission("rbac:assign"),
      canReadAudit: hasPermission("audit:read"),
      canManageTeams: hasPermission("team:manage"),
      canReadShares: hasPermission("share:read"),
      canCreateShares: hasPermission("share:create"),
    }),
    [hasPermission, isAdmin, isLoading, permissions],
  );
}
