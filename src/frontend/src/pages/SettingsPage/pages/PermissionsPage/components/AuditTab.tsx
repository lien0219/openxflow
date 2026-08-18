import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { type AuditPage, getAuditPage } from "@/controllers/API/queries/authz";
import { translateRbacValue } from "../rbac-i18n";

const PANEL_CLASS = "rounded-lg border bg-card p-4";
const FIELD_CLASS = "flex min-w-0 flex-col gap-1.5";
const SELECT_CLASS =
  "h-10 w-full rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring";

type AuditFilters = {
  action: string;
  result: string;
  resourceType: string;
  domainType: string;
  domainId: string;
};

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
  const initialDomainType = isSuperuser
    ? "global"
    : defaultDomainType || "channel";
  const initialDomainId = isSuperuser ? "" : defaultDomainId || "";
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
  const [domainType, setDomainType] = useState(initialDomainType);
  const [domainId, setDomainId] = useState(initialDomainId);
  const [loading, setLoading] = useState(false);
  const initialLoadStarted = useRef(false);

  const load = useCallback(
    async (page = 1, overrides: Partial<AuditFilters> = {}) => {
      const nextAction = overrides.action ?? action;
      const nextResult = overrides.result ?? result;
      const nextResourceType = overrides.resourceType ?? resourceType;
      const nextDomainType = overrides.domainType ?? domainType;
      const nextDomainId = overrides.domainId ?? domainId;

      if (!isSuperuser && nextDomainType !== "global" && !nextDomainId) {
        return;
      }

      setLoading(true);
      try {
        const next = await getAuditPage({
          page,
          size: 50,
          action: nextAction || undefined,
          result: nextResult || undefined,
          resource_type: nextResourceType || undefined,
          domain_type: isSuperuser ? undefined : nextDomainType,
          domain_id:
            !isSuperuser && nextDomainType !== "global"
              ? nextDomainId || undefined
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

  const resetFilters = () => {
    setAction("");
    setResult("");
    setResourceType("");
    setDomainType(initialDomainType);
    setDomainId(initialDomainId);
    void load(1, {
      action: "",
      result: "",
      resourceType: "",
      domainType: initialDomainType,
      domainId: initialDomainId,
    });
  };

  const domains = ["global", "organization", "workspace", "project", "channel"];
  const auditResults = ["allow", "deny", "owner_override"];
  const resourceTypes = [
    "audit",
    "channel",
    "component",
    "deployment",
    "file",
    "flow",
    "knowledge_base",
    "project",
    "rbac",
    "share",
    "team",
    "user",
    "variable",
  ];

  return (
    <section className={PANEL_CLASS}>
      <form
        className="rounded-lg border bg-muted/20 p-4"
        onSubmit={(event) => {
          event.preventDefault();
          void load(1);
        }}
      >
        <div>
          <h2 className="font-semibold">{t("rbac.audit.filters")}</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            {t("rbac.audit.filterHelp")}
          </p>
        </div>

        <div
          className={`mt-4 grid gap-3 md:grid-cols-2 ${
            isSuperuser ? "xl:grid-cols-3" : "xl:grid-cols-5"
          }`}
        >
          {!isSuperuser && (
            <>
              <div className={FIELD_CLASS}>
                <label className="text-sm font-medium">
                  {t("rbac.audit.scope")}
                </label>
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
              </div>
              <div className={FIELD_CLASS}>
                <label className="text-sm font-medium">
                  {t("rbac.users.domainId")}
                </label>
                <Input
                  disabled={domainType === "global"}
                  placeholder={t("rbac.users.domainIdHelp")}
                  value={domainId}
                  onChange={(event) => setDomainId(event.target.value.trim())}
                />
              </div>
            </>
          )}

          <div className={FIELD_CLASS}>
            <label className="text-sm font-medium">
              {t("rbac.audit.action")}
            </label>
            <Input
              placeholder={t("rbac.audit.actionPlaceholder")}
              value={action}
              onChange={(event) => setAction(event.target.value)}
            />
          </div>

          <div className={FIELD_CLASS}>
            <label className="text-sm font-medium">
              {t("rbac.audit.resourceType")}
            </label>
            <select
              className={SELECT_CLASS}
              value={resourceType}
              onChange={(event) => setResourceType(event.target.value)}
            >
              <option value="">{t("rbac.audit.allResources")}</option>
              {resourceTypes.map((item) => (
                <option key={item} value={item}>
                  {translateRbacValue(t, "resourceType", item)}
                </option>
              ))}
            </select>
          </div>

          <div className={FIELD_CLASS}>
            <label className="text-sm font-medium">
              {t("rbac.audit.result")}
            </label>
            <select
              className={SELECT_CLASS}
              value={result}
              onChange={(event) => setResult(event.target.value)}
            >
              <option value="">{t("rbac.audit.allResults")}</option>
              {auditResults.map((item) => (
                <option key={item} value={item}>
                  {translateRbacValue(t, "auditResult", item)}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap justify-end gap-2 border-t pt-4">
          <Button
            type="button"
            variant="outline"
            onClick={resetFilters}
            disabled={loading}
            ignoreTitleCase
          >
            {t("rbac.audit.reset")}
          </Button>
          <Button
            type="submit"
            loading={loading}
            disabled={!isSuperuser && domainType !== "global" && !domainId}
            ignoreTitleCase
          >
            {t("rbac.audit.search")}
          </Button>
        </div>
      </form>

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
                <td className="p-2 text-xs">
                  {entry.resource_type
                    ? translateRbacValue(t, "resourceType", entry.resource_type)
                    : "—"}
                  {entry.resource_id ? (
                    <code className="ml-1 text-muted-foreground">
                      {entry.resource_id}
                    </code>
                  ) : null}
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
