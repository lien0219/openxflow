import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  createRoleAssignment,
  deleteRoleAssignment,
  getIdentitySummary,
  getUsers,
  type IdentitySummary,
  type RbacRole,
  type RbacUser,
} from "@/controllers/API/queries/authz";
import {
  translateRbacRoleName,
  translateRbacValue,
} from "../rbac-i18n";

const PANEL_CLASS = "rounded-lg border bg-card p-4";
const FIELD_CLASS = "flex min-w-0 flex-col gap-1.5";
const SELECT_CLASS =
  "h-10 rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring";

export function UserPermissionsTab({
  roles,
  selfSummary,
  isSuperuser,
  canAssign,
  onSuccess,
  onError,
}: {
  roles: RbacRole[];
  selfSummary: IdentitySummary;
  isSuperuser: boolean;
  canAssign: boolean;
  onSuccess: () => void;
  onError: (error: unknown) => void;
}) {
  const { t } = useTranslation();
  const [users, setUsers] = useState<RbacUser[]>([]);
  const [search, setSearch] = useState("");
  const [targetUserId, setTargetUserId] = useState(selfSummary.user_id);
  const [summary, setSummary] = useState<IdentitySummary>(selfSummary);
  const [loadingTarget, setLoadingTarget] = useState(false);
  const [roleId, setRoleId] = useState(
    roles.find((role) => role.name === "member")?.id || roles[0]?.id || "",
  );
  const firstScopedAssignment = selfSummary.assignments.find(
    (assignment) => assignment.domain_type !== "global" && assignment.domain_id,
  );
  const [domainType, setDomainType] = useState(
    isSuperuser ? "global" : firstScopedAssignment?.domain_type || "channel",
  );
  const [domainId, setDomainId] = useState(
    isSuperuser ? "" : firstScopedAssignment?.domain_id || "",
  );

  useEffect(() => {
    if (!isSuperuser) return;
    getUsers(0, 200, search || undefined)
      .then((page) => setUsers(page.users))
      .catch(onError);
  }, [isSuperuser, onError, search]);

  const scope = useMemo(
    () => ({
      domain_type: domainType,
      domain_id: domainType === "global" ? null : domainId,
    }),
    [domainId, domainType],
  );

  const loadTarget = async (userId = targetUserId) => {
    if (!userId) return;
    setLoadingTarget(true);
    try {
      const nextSummary = await getIdentitySummary(
        userId,
        !isSuperuser && userId !== selfSummary.user_id ? scope : undefined,
      );
      setSummary(nextSummary);
      setTargetUserId(userId);
    } catch (error) {
      onError(error);
    } finally {
      setLoadingTarget(false);
    }
  };

  const assignRole = async () => {
    if (!targetUserId || !roleId) return;
    try {
      await createRoleAssignment({
        user_id: targetUserId,
        role_id: roleId,
        domain_type: domainType,
        domain_id: domainType === "global" ? null : domainId,
      });
      await loadTarget(targetUserId);
      onSuccess();
    } catch (error) {
      onError(error);
    }
  };

  const revokeRole = async (assignmentId: string) => {
    try {
      await deleteRoleAssignment(assignmentId);
      await loadTarget(targetUserId);
      onSuccess();
    } catch (error) {
      onError(error);
    }
  };

  const domainOptions = isSuperuser
    ? ["global", "organization", "workspace", "project", "channel"]
    : ["organization", "workspace", "project", "channel"];

  return (
    <div className="grid gap-4 xl:grid-cols-[340px_minmax(0,1fr)]">
      <section className={PANEL_CLASS}>
        {isSuperuser && (
          <div className={FIELD_CLASS}>
            <label className="text-sm font-medium">
              {t("rbac.users.search")}
            </label>
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
        )}

        <div className={`${FIELD_CLASS} ${isSuperuser ? "mt-4" : ""}`}>
          <label className="text-sm font-medium">
            {t("rbac.users.targetId")}
          </label>
          <div className="flex gap-2">
            <Input
              value={targetUserId}
              onChange={(event) => setTargetUserId(event.target.value.trim())}
              placeholder="UUID"
            />
            <Button
              variant="outline"
              onClick={() => void loadTarget()}
              loading={loadingTarget}
              disabled={!targetUserId}
              ignoreTitleCase
            >
              {t("rbac.users.inspect")}
            </Button>
          </div>
          {!isSuperuser && (
            <p className="text-xs text-muted-foreground">
              {t("rbac.users.scopedDirectoryHelp")}
            </p>
          )}
        </div>

        {isSuperuser && (
          <div className="mt-4 max-h-[500px] space-y-1 overflow-y-auto custom-scroll">
            {users.map((user) => (
              <button
                type="button"
                key={user.id}
                onClick={() => void loadTarget(user.id)}
                className={`w-full rounded-md border px-3 py-2 text-left text-sm ${
                  targetUserId === user.id
                    ? "border-primary bg-muted"
                    : "hover:bg-muted/60"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate font-medium">{user.username}</span>
                  <span className="text-xs text-muted-foreground">
                    {translateRbacValue(
                      t,
                      "userType",
                      user.is_superuser ? "superuser" : "user",
                    )}
                  </span>
                </div>
                <div className="truncate text-xs text-muted-foreground">
                  {user.id}
                </div>
              </button>
            ))}
          </div>
        )}
      </section>

      <div className="space-y-4">
        {canAssign && (
          <section className={PANEL_CLASS}>
            <h2 className="font-semibold">{t("rbac.users.assign")}</h2>
            <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <div className={FIELD_CLASS}>
                <label className="text-sm">{t("rbac.roles.name")}</label>
                <select
                  className={SELECT_CLASS}
                  value={roleId}
                  onChange={(event) => setRoleId(event.target.value)}
                >
                  {roles.map((role) => (
                    <option key={role.id} value={role.id}>
                      {translateRbacRoleName(t, role.name, role.is_system)}
                    </option>
                  ))}
                </select>
              </div>
              <div className={FIELD_CLASS}>
                <label className="text-sm">{t("rbac.users.domain")}</label>
                <select
                  className={SELECT_CLASS}
                  value={domainType}
                  onChange={(event) => {
                    setDomainType(event.target.value);
                    if (event.target.value === "global") setDomainId("");
                  }}
                >
                  {domainOptions.map((domain) => (
                    <option key={domain} value={domain}>
                      {translateRbacValue(t, "domain", domain)}
                    </option>
                  ))}
                </select>
              </div>
              <div className={`${FIELD_CLASS} xl:col-span-2`}>
                <label className="text-sm">{t("rbac.users.domainId")}</label>
                <Input
                  disabled={domainType === "global"}
                  value={domainId}
                  onChange={(event) => setDomainId(event.target.value.trim())}
                  placeholder={t("rbac.users.domainIdHelp")}
                />
              </div>
            </div>
            <Button
              className="mt-3"
              onClick={() => void assignRole()}
              disabled={
                !targetUserId ||
                !roleId ||
                (domainType !== "global" && !domainId)
              }
              ignoreTitleCase
            >
              {t("rbac.users.assign")}
            </Button>
          </section>
        )}

        <section className={PANEL_CLASS}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="font-semibold">{t("rbac.users.roles")}</h2>
              <p className="text-xs text-muted-foreground">
                {summary.username} · {summary.user_id}
              </p>
            </div>
          </div>
          <div className="mt-3 space-y-2">
            {summary.assignments.map((assignment) => (
              <div
                key={assignment.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-3"
              >
                <div>
                  <div className="font-medium">
                    {translateRbacRoleName(t, assignment.role_name)}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {translateRbacValue(
                      t,
                      "domain",
                      assignment.domain_type,
                    )}
                    {assignment.domain_id ? ` · ${assignment.domain_id}` : ""}
                  </div>
                </div>
                {canAssign && (
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => void revokeRole(assignment.id)}
                    ignoreTitleCase
                  >
                    {t("rbac.remove")}
                  </Button>
                )}
              </div>
            ))}
            {summary.assignments.length === 0 && (
              <div className="py-8 text-center text-sm text-muted-foreground">
                {t("rbac.empty")}
              </div>
            )}
          </div>
        </section>

        <div className="grid gap-4 lg:grid-cols-2">
          <section className={PANEL_CLASS}>
            <h2 className="font-semibold">{t("rbac.users.effective")}</h2>
            <div className="mt-3 flex max-h-64 flex-wrap gap-2 overflow-y-auto custom-scroll">
              {summary.effective_permissions.map((permission) => (
                <code
                  key={permission}
                  className="rounded bg-muted px-2 py-1 text-xs"
                >
                  {permission}
                </code>
              ))}
              {summary.effective_permissions.length === 0 && (
                <span className="text-sm text-muted-foreground">
                  {t("rbac.empty")}
                </span>
              )}
            </div>
          </section>
          <section className={PANEL_CLASS}>
            <h2 className="font-semibold">{t("rbac.users.teams")}</h2>
            <div className="mt-3 space-y-2">
              {summary.teams.map((team) => (
                <div key={team.id} className="rounded-md border p-3 text-sm">
                  <div className="font-medium">{team.team_name}</div>
                  <div className="text-xs text-muted-foreground">
                    {team.adom_name} ·{" "}
                    {translateRbacValue(t, "memberSource", team.source)}
                  </div>
                </div>
              ))}
              {summary.teams.length === 0 && (
                <span className="text-sm text-muted-foreground">
                  {t("rbac.empty")}
                </span>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
