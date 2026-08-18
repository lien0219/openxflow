import { useTranslation } from "react-i18next";
import type {
  IdentitySummary,
  RbacStatus,
} from "@/controllers/API/queries/authz";
import { translateRbacWarning } from "../rbac-i18n";
import { PermissionBadge } from "./PermissionBadge";

const PANEL_CLASS = "rounded-lg border bg-card p-4";

function StatusBadge({ enabled }: { enabled: boolean }) {
  const { t } = useTranslation();
  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${
        enabled
          ? "bg-primary/10 text-primary"
          : "bg-muted text-muted-foreground"
      }`}
    >
      {enabled ? t("rbac.enabled") : t("rbac.disabled")}
    </span>
  );
}

export function OverviewTab({
  status,
  summary,
}: {
  status: RbacStatus;
  summary: IdentitySummary | null;
}) {
  const { t } = useTranslation();
  const settings = [
    {
      label: t("rbac.status.enforcement"),
      enabled: status.authz_enabled,
      variable: "LANGFLOW_AUTHZ_ENABLED",
    },
    {
      label: t("rbac.status.audit"),
      enabled: status.audit_enabled,
      variable: "LANGFLOW_AUTHZ_AUDIT_ENABLED",
    },
    {
      label: t("rbac.status.autoLogin"),
      enabled: status.auto_login,
      variable: "LANGFLOW_AUTO_LOGIN",
    },
    {
      label: t("rbac.status.superuserBypass"),
      enabled: status.superuser_bypass,
      variable: "LANGFLOW_AUTHZ_SUPERUSER_BYPASS",
    },
  ];
  const productionConfiguration = [
    "LANGFLOW_AUTO_LOGIN=false",
    "LANGFLOW_SUPERUSER=admin",
    "LANGFLOW_SUPERUSER_PASSWORD=<set-a-strong-password>",
    "LANGFLOW_AUTHZ_ENABLED=true",
    "LANGFLOW_AUTHZ_AUDIT_ENABLED=true",
    "LANGFLOW_AUTHZ_SUPERUSER_BYPASS=true",
  ].join("\n");

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <section className={PANEL_CLASS}>
        <div className="flex items-center justify-between gap-3">
          <h2 className="font-semibold">
            {status.production_ready
              ? t("rbac.status.ready")
              : t("rbac.status.notReady")}
          </h2>
          <StatusBadge enabled={status.production_ready} />
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {settings.map((setting) => (
            <div
              key={setting.variable}
              className="flex min-w-0 items-center justify-between gap-3 rounded-md border p-3"
            >
              <div className="min-w-0">
                <div className="text-sm">{setting.label}</div>
                <code className="mt-1 block truncate text-[10px] text-muted-foreground">
                  {setting.variable}={String(setting.enabled).toLowerCase()}
                </code>
              </div>
              <StatusBadge enabled={setting.enabled} />
            </div>
          ))}
        </div>
        {status.warnings.length > 0 && (
          <div className="mt-4 rounded-md border border-border bg-muted/50 p-3 text-sm">
            {status.warnings.map((warning) => (
              <p key={warning}>• {translateRbacWarning(t, warning)}</p>
            ))}
          </div>
        )}

        <div className="mt-4 rounded-md border bg-muted/20 p-4">
          <h3 className="font-medium">{t("rbac.status.configurationTitle")}</h3>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            {t("rbac.status.configurationHelp")}
          </p>
          <div className="mt-3 text-xs font-medium">
            {t("rbac.status.productionExample")}
          </div>
          <pre className="mt-2 overflow-x-auto rounded-md bg-muted p-3 text-xs leading-5">
            {productionConfiguration}
          </pre>
          <p className="mt-3 text-xs leading-5 text-muted-foreground">
            {t("rbac.status.restartRequired")}
          </p>
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            {t("rbac.status.sqliteAuditNote")}
          </p>
        </div>
      </section>

      <section className={PANEL_CLASS}>
        <h2 className="font-semibold">{t("rbac.users.effective")}</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          {summary?.username || "—"}
        </p>
        <div className="mt-3 flex max-h-80 flex-wrap gap-2 overflow-y-auto custom-scroll">
          {summary?.effective_permissions.map((permission) => (
            <PermissionBadge key={permission} permission={permission} />
          ))}
          {!summary?.effective_permissions.length && (
            <div className="py-8 text-sm text-muted-foreground">
              {t("rbac.empty")}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
