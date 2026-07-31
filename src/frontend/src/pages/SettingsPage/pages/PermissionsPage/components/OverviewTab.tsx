import { useTranslation } from "react-i18next";
import type {
  IdentitySummary,
  RbacStatus,
} from "@/controllers/API/queries/authz";
import { translateRbacWarning } from "../rbac-i18n";

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
          {[
            [t("rbac.status.enforcement"), status.authz_enabled],
            [t("rbac.status.audit"), status.audit_enabled],
            [t("rbac.status.autoLogin"), status.auto_login],
            [t("rbac.status.superuserBypass"), status.superuser_bypass],
          ].map(([label, enabled]) => (
            <div
              key={String(label)}
              className="flex items-center justify-between rounded-md border p-3"
            >
              <span className="text-sm">{label}</span>
              <StatusBadge enabled={Boolean(enabled)} />
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
      </section>

      <section className={PANEL_CLASS}>
        <h2 className="font-semibold">{t("rbac.users.effective")}</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          {summary?.username || "—"}
        </p>
        <div className="mt-3 flex max-h-80 flex-wrap gap-2 overflow-y-auto custom-scroll">
          {summary?.effective_permissions.map((permission) => (
            <code
              key={permission}
              className="rounded bg-muted px-2 py-1 text-xs"
            >
              {permission}
            </code>
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
