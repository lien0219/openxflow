import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { type AuditPage, getAuditPage } from "@/controllers/API/queries/authz";
import { translateRbacValue } from "../rbac-i18n";

const PANEL_CLASS = "rounded-lg border bg-card p-4";
const SELECT_CLASS =
  "h-10 rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring";

export function AuditTab({
  isSuperuser,
  defaultDomainType,
  defaultDomainId,
  onError,
}: {
  isSuperuser: boolean;
  defaultDomainType?: string;
  defaultDomainId?: string | null;
  onError: (error: unknown) => void;
}) {
  const { t } = useTranslation();
  const [audit, setAudit] = useState<AuditPage>({
    items: [],
    total: 0,
    page: 1,
    size: 50,
    pages: 0,
  });
  const [action, setAction] = useState("");
  const [result, setResult] = useState("");
  const [resourceType, setResourceType] = useState("");
  const [domainType, setDomainType] = useState(
    isSuperuser ? "global" : defaultDomainType || "channel",
  );
  const [domainId, setDomainId] = useState(
    isSuperuser ? "" : defaultDomainId || "",
  );
  const [loading, setLoading] = useState(false);
  const initialLoadStarted = useRef(false);

  const load = useCallback(
    async (page = 1) => {
      if (!isSuperuser && domainType !== "global" && !domainId) return;
      setLoading(true);
      try {
        const next = await getAuditPage({
          page,
          size: 50,
          action: action || undefined,
          result: result || undefined,
          resource_type: resourceType || undefined,
          domain_type: isSuperuser ? undefined : domainType,
          domain_id:
            !isSuperuser && domainType !== "global"
              ? domainId || undefined
              : undefined,
        });
        setAudit(next);
      } catch (error) {
        onError(error);
      } finally {
        setLoading(false);
      }
    },
    [action, domainId, domainType, isSuperuser, onError, resourceType, result],
  );

  useEffect(() => {
    if (initialLoadStarted.current) return;
    if (isSuperuser || domainType === "global" || domainId) {
      initialLoadStarted.current = true;
      void load(1);
    }
  }, [domainId, domainType, isSuperuser, load]);

  const domains = [
    "global",
    "organization",
    "workspace",
    "project",
    "channel",
  ];
  const auditResults = ["allow", "deny", "owner_override"];

  return (
    <section className={PANEL_CLASS}>
      <div className="flex flex-wrap gap-2">
        {!isSuperuser && (
          <>
            <select
              className={SELECT_CLASS}
              value={domainType}
              onChange={(event) => {
                setDomainType(event.target.value);
                if (event.target.value === "global") setDomainId("");
              }}
            >
              {domains.map((domain) => (
                <option key={domain} value={domain}>
                  {translateRbacValue(t, "domain", domain)}
                </option>
              ))}
            </select>
            <Input
              className="max-w-80"
              disabled={domainType === "global"}
              placeholder={t("rbac.users.domainId")}
              value={domainId}
              onChange={(event) => setDomainId(event.target.value.trim())}
            />
          </>
        )}
        <Input
          className="max-w-64"
          placeholder={t("rbac.audit.action")}
          value={action}
          onChange={(event) => setAction(event.target.value)}
        />
        <Input
          className="max-w-48"
          placeholder={t("rbac.audit.resource")}
          value={resourceType}
          onChange={(event) => setResourceType(event.target.value)}
        />
        <select
          className={SELECT_CLASS}
          value={result}
          onChange={(event) => setResult(event.target.value)}
        >
          <option value="">{t("rbac.audit.result")}</option>
          {auditResults.map((item) => (
            <option key={item} value={item}>
              {translateRbacValue(t, "auditResult", item)}
            </option>
          ))}
        </select>
        <Button
          variant="outline"
          onClick={() => void load(1)}
          loading={loading}
          disabled={!isSuperuser && domainType !== "global" && !domainId}
          ignoreTitleCase
        >
          {t("rbac.refresh")}
        </Button>
      </div>

      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[900px] text-sm">
          <thead>
            <tr className="border-b text-left">
              <th className="p-2">{t("rbac.audit.time")}</th>
              <th className="p-2">{t("rbac.audit.user")}</th>
              <th className="p-2">{t("rbac.audit.action")}</th>
              <th className="p-2">{t("rbac.audit.resource")}</th>
              <th className="p-2">{t("rbac.audit.result")}</th>
            </tr>
          </thead>
          <tbody>
            {audit.items.map((entry) => (
              <tr key={entry.id} className="border-b">
                <td className="whitespace-nowrap p-2">
                  {new Date(entry.timestamp).toLocaleString()}
                </td>
                <td className="p-2 font-mono text-xs">
                  {entry.user_id || "—"}
                </td>
                <td className="p-2">{entry.action}</td>
                <td className="p-2 font-mono text-xs">
                  {entry.resource_type
                    ? translateRbacValue(
                        t,
                        "resourceType",
                        entry.resource_type,
                      )
                    : "—"}
                  {entry.resource_id ? `:${entry.resource_id}` : ""}
                </td>
                <td className="p-2">
                  <span
                    className={`rounded px-2 py-1 text-xs ${
                      entry.result === "deny"
                        ? "bg-destructive/10 text-destructive"
                        : "bg-primary/10 text-primary"
                    }`}
                  >
                    {translateRbacValue(t, "auditResult", entry.result)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {audit.items.length === 0 && (
          <div className="py-8 text-center text-sm text-muted-foreground">
            {t("rbac.empty")}
          </div>
        )}
      </div>

      <div className="mt-4 flex items-center justify-between">
        <span className="text-sm text-muted-foreground">
          {audit.total} · {audit.page}/{Math.max(audit.pages, 1)}
        </span>
        <div className="flex gap-2">
          <Button
            variant="outline"
            disabled={audit.page <= 1 || loading}
            onClick={() => void load(audit.page - 1)}
            ignoreTitleCase
          >
            {t("rbac.audit.previous")}
          </Button>
          <Button
            variant="outline"
            disabled={audit.pages === 0 || audit.page >= audit.pages || loading}
            onClick={() => void load(audit.page + 1)}
            ignoreTitleCase
          >
            {t("rbac.audit.next")}
          </Button>
        </div>
      </div>
    </section>
  );
}
