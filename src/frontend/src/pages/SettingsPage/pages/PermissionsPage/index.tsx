import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  getIdentitySummary,
  getRbacStatus,
  getRoles,
  type IdentitySummary,
  type RbacRole,
  type RbacStatus,
} from "@/controllers/API/queries/authz";
import { useRbacAccess } from "@/hooks/use-rbac-access";
import useAlertStore from "@/stores/alertStore";
import { AuditTab } from "./components/AuditTab";
import { OverviewTab } from "./components/OverviewTab";
import { RolesTab } from "./components/RolesTab";
import { SharesTab } from "./components/SharesTab";
import { TeamsTab } from "./components/TeamsTab";
import { UserPermissionsTab } from "./components/UserPermissionsTab";

const ALL_TABS = ["overview", "users", "roles", "teams", "shares", "audit"] as const;
type Tab = (typeof ALL_TABS)[number];

type ApiError = {
  response?: { data?: { detail?: string | Array<{ msg?: string }> } };
  message?: string;
};

function errorMessage(error: unknown): string {
  const candidate = error as ApiError;
  const detail = candidate?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => item.msg)
      .filter(Boolean)
      .join("; ");
  }
  return candidate?.message || "Unknown error";
}

export default function PermissionsPage() {
  const { t } = useTranslation();
  const setSuccessData = useAlertStore((state) => state.setSuccessData);
  const setErrorData = useAlertStore((state) => state.setErrorData);
  const {
    isAdmin,
    canReadRbac,
    canAssignRbac,
    canReadAudit,
    canReadShares,
    canCreateShares,
  } = useRbacAccess();

  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<RbacStatus | null>(null);
  const [summary, setSummary] = useState<IdentitySummary | null>(null);
  const [roles, setRoles] = useState<RbacRole[]>([]);

  const notifySuccess = useCallback(
    () => setSuccessData({ title: t("rbac.success") }),
    [setSuccessData, t],
  );
  const notifyError = useCallback(
    (error: unknown) =>
      setErrorData({
        title: t("rbac.error"),
        list: [errorMessage(error)],
      }),
    [setErrorData, t],
  );

  const reloadRoles = useCallback(async () => {
    setRoles(await getRoles());
  }, []);

  const loadBase = useCallback(async () => {
    setLoading(true);
    try {
      // Status performs the idempotent system-role/default-member bootstrap.
      const nextStatus = await getRbacStatus();
      const [nextSummary, nextRoles] = await Promise.all([
        getIdentitySummary(),
        getRoles(),
      ]);
      setStatus(nextStatus);
      setSummary(nextSummary);
      setRoles(nextRoles);
    } catch (error) {
      notifyError(error);
    } finally {
      setLoading(false);
    }
  }, [notifyError]);

  useEffect(() => {
    void loadBase();
  }, [loadBase]);

  const visibleTabs = useMemo<Tab[]>(() => {
    const tabs: Tab[] = ["overview"];
    if (canAssignRbac || isAdmin) tabs.push("users");
    tabs.push("roles");
    if (isAdmin) tabs.push("teams");
    if (canReadShares || isAdmin) tabs.push("shares");
    if (canReadAudit || isAdmin) tabs.push("audit");
    return tabs;
  }, [canAssignRbac, canReadAudit, canReadShares, isAdmin]);

  useEffect(() => {
    if (!visibleTabs.includes(activeTab)) setActiveTab("overview");
  }, [activeTab, visibleTabs]);

  const auditScope = useMemo(() => {
    const assignment = summary?.assignments.find(
      (item) =>
        item.domain_type === "global" ||
        (item.domain_type !== "global" && item.domain_id),
    );
    return assignment
      ? {
          domainType: assignment.domain_type,
          domainId: assignment.domain_id,
        }
      : undefined;
  }, [summary]);

  if (loading && (!status || !summary)) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        {t("rbac.loading")}
      </div>
    );
  }

  if (!canReadRbac || !status || !summary) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        {t("rbac.accessDenied")}
      </div>
    );
  }

  return (
    <div className="flex h-full min-w-0 flex-col overflow-hidden px-5 pb-6">
      <div className="flex flex-wrap items-start justify-between gap-3 pb-4">
        <div>
          <h1 className="text-xl font-semibold">{t("rbac.title")}</h1>
          <p className="mt-1 max-w-4xl text-sm text-muted-foreground">
            {t("rbac.description")}
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => void loadBase()}
          loading={loading}
          ignoreTitleCase
        >
          {t("rbac.refresh")}
        </Button>
      </div>

      <div className="flex flex-wrap gap-2 border-b pb-3">
        {visibleTabs.map((tab) => (
          <Button
            key={tab}
            variant={activeTab === tab ? "secondary" : "ghost"}
            size="sm"
            onClick={() => setActiveTab(tab)}
            ignoreTitleCase
          >
            {t(`rbac.tabs.${tab}`)}
          </Button>
        ))}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto pt-4 custom-scroll">
        {activeTab === "overview" && (
          <OverviewTab status={status} summary={summary} />
        )}
        {activeTab === "users" && (
          <UserPermissionsTab
            roles={roles}
            selfSummary={summary}
            isSuperuser={isAdmin}
            canAssign={canAssignRbac || isAdmin}
            onSuccess={notifySuccess}
            onError={notifyError}
          />
        )}
        {activeTab === "roles" && (
          <RolesTab
            roles={roles}
            // Role catalog CRUD is global and remains superuser-only. Scoped
            // administrators can inspect roles and delegate allowed roles.
            canManage={isAdmin}
            onReload={reloadRoles}
            onSuccess={notifySuccess}
            onError={notifyError}
          />
        )}
        {activeTab === "teams" && isAdmin && (
          <TeamsTab
            roles={roles}
            onSuccess={notifySuccess}
            onError={notifyError}
          />
        )}
        {activeTab === "shares" && (
          <SharesTab
            canCreate={canCreateShares || isAdmin}
            onSuccess={notifySuccess}
            onError={notifyError}
          />
        )}
        {activeTab === "audit" && (
          <AuditTab
            isSuperuser={isAdmin}
            defaultDomainType={auditScope?.domainType}
            defaultDomainId={auditScope?.domainId}
            onError={notifyError}
          />
        )}
      </div>
    </div>
  );
}
