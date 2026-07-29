import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  addTeamMember,
  createRole,
  createRoleAssignment,
  createShare,
  createTeam,
  deleteRole,
  deleteRoleAssignment,
  deleteShare,
  deleteTeam,
  getAuditPage,
  getIdentitySummary,
  getRbacStatus,
  getRoles,
  getShares,
  getTeamMembers,
  getTeams,
  getUsers,
  removeTeamMember,
  updateRole,
  updateShare,
  updateTeam,
  type AuditPage,
  type IdentitySummary,
  type RbacRole,
  type RbacStatus,
  type RbacUser,
  type ResourceShare,
  type Team,
  type TeamMember,
} from "@/controllers/API/queries/authz";
import useAlertStore from "@/stores/alertStore";

const TABS = ["overview", "users", "roles", "teams", "shares", "audit"] as const;
type Tab = (typeof TABS)[number];

const SELECT_CLASS =
  "h-10 rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring";
const PANEL_CLASS = "rounded-lg border bg-card p-4";
const FIELD_CLASS = "flex min-w-0 flex-col gap-1.5";

function errorMessage(error: unknown): string {
  const candidate = error as {
    response?: { data?: { detail?: string | Array<{ msg?: string }> } };
    message?: string;
  };
  const detail = candidate?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg).filter(Boolean).join("; ");
  }
  return candidate?.message || "Unknown error";
}

function StatusBadge({ enabled }: { enabled: boolean }) {
  const { t } = useTranslation();
  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${
        enabled
          ? "bg-green-500/10 text-green-700 dark:text-green-300"
          : "bg-amber-500/10 text-amber-700 dark:text-amber-300"
      }`}
    >
      {enabled ? t("rbac.enabled") : t("rbac.disabled")}
    </span>
  );
}

function EmptyState() {
  const { t } = useTranslation();
  return <div className="py-8 text-center text-sm text-muted-foreground">{t("rbac.empty")}</div>;
}

export default function PermissionsPage() {
  const { t } = useTranslation();
  const setSuccessData = useAlertStore((state) => state.setSuccessData);
  const setErrorData = useAlertStore((state) => state.setErrorData);

  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<RbacStatus | null>(null);
  const [users, setUsers] = useState<RbacUser[]>([]);
  const [roles, setRoles] = useState<RbacRole[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [shares, setShares] = useState<ResourceShare[]>([]);
  const [audit, setAudit] = useState<AuditPage>({ items: [], total: 0, page: 1, size: 50, pages: 0 });

  const [userSearch, setUserSearch] = useState("");
  const [selectedUserId, setSelectedUserId] = useState("");
  const [selectedSummary, setSelectedSummary] = useState<IdentitySummary | null>(null);
  const [assignmentRoleId, setAssignmentRoleId] = useState("");
  const [assignmentDomainType, setAssignmentDomainType] = useState("global");
  const [assignmentDomainId, setAssignmentDomainId] = useState("");

  const [editingRoleId, setEditingRoleId] = useState("");
  const [roleName, setRoleName] = useState("");
  const [roleDescription, setRoleDescription] = useState("");
  const [rolePermissions, setRolePermissions] = useState("");
  const [roleParentId, setRoleParentId] = useState("");

  const [selectedTeamId, setSelectedTeamId] = useState("");
  const [teamMembers, setTeamMembers] = useState<TeamMember[]>([]);
  const [teamName, setTeamName] = useState("");
  const [teamSlug, setTeamSlug] = useState("");
  const [teamDescription, setTeamDescription] = useState("");
  const [teamMemberUserId, setTeamMemberUserId] = useState("");

  const [shareResourceType, setShareResourceType] = useState("flow");
  const [shareResourceId, setShareResourceId] = useState("");
  const [shareScope, setShareScope] = useState<ResourceShare["scope"]>("user");
  const [shareTargetId, setShareTargetId] = useState("");
  const [shareLevel, setShareLevel] = useState<ResourceShare["permission_level"]>("read");

  const [auditAction, setAuditAction] = useState("");
  const [auditResult, setAuditResult] = useState("");
  const [auditResourceType, setAuditResourceType] = useState("");

  const notifySuccess = useCallback(
    (title = t("rbac.success")) => setSuccessData({ title }),
    [setSuccessData, t],
  );
  const notifyError = useCallback(
    (error: unknown) =>
      setErrorData({ title: t("rbac.error"), list: [errorMessage(error)] }),
    [setErrorData, t],
  );

  const loadAudit = useCallback(
    async (page = 1) => {
      const result = await getAuditPage({
        page,
        size: 50,
        action: auditAction || undefined,
        result: auditResult || undefined,
        resource_type: auditResourceType || undefined,
      });
      setAudit(result);
    },
    [auditAction, auditResourceType, auditResult],
  );

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      // Status performs the idempotent RBAC catalog/default-role bootstrap.
      const nextStatus = await getRbacStatus();
      setStatus(nextStatus);
      const [usersPage, nextRoles, nextTeams, nextShares, nextAudit] = await Promise.all([
        getUsers(0, 200, userSearch || undefined),
        getRoles(),
        getTeams(),
        getShares(),
        getAuditPage({ page: 1, size: 50 }),
      ]);
      setUsers(usersPage.users);
      setRoles(nextRoles);
      setTeams(nextTeams);
      setShares(nextShares);
      setAudit(nextAudit);
      setSelectedUserId((current) => current || usersPage.users[0]?.id || "");
      setAssignmentRoleId((current) => current || nextRoles.find((role) => role.name === "member")?.id || nextRoles[0]?.id || "");
      setSelectedTeamId((current) => current || nextTeams[0]?.id || "");
    } catch (error) {
      notifyError(error);
    } finally {
      setLoading(false);
    }
  }, [notifyError, userSearch]);

  useEffect(() => {
    void loadAll();
  }, []);

  useEffect(() => {
    if (!selectedUserId) {
      setSelectedSummary(null);
      return;
    }
    getIdentitySummary(selectedUserId).then(setSelectedSummary).catch(notifyError);
  }, [notifyError, selectedUserId]);

  useEffect(() => {
    if (!selectedTeamId) {
      setTeamMembers([]);
      return;
    }
    getTeamMembers(selectedTeamId).then(setTeamMembers).catch(notifyError);
  }, [notifyError, selectedTeamId]);

  const usersById = useMemo(() => new Map(users.map((user) => [user.id, user])), [users]);
  const rolesById = useMemo(() => new Map(roles.map((role) => [role.id, role])), [roles]);
  const teamsById = useMemo(() => new Map(teams.map((team) => [team.id, team])), [teams]);

  const resetRoleForm = useCallback(() => {
    setEditingRoleId("");
    setRoleName("");
    setRoleDescription("");
    setRolePermissions("");
    setRoleParentId("");
  }, []);

  const editRole = useCallback((role: RbacRole) => {
    setEditingRoleId(role.id);
    setRoleName(role.name);
    setRoleDescription(role.description || "");
    setRolePermissions(role.permissions.join("\n"));
    setRoleParentId(role.parent_role_id || "");
  }, []);

  const parsedPermissions = useMemo(
    () =>
      Array.from(
        new Set(
          rolePermissions
            .split(/[\n,]/)
            .map((item) => item.trim().toLowerCase())
            .filter(Boolean),
        ),
      ),
    [rolePermissions],
  );

  const handleSaveRole = async () => {
    try {
      if (editingRoleId) {
        await updateRole(editingRoleId, {
          name: roleName,
          description: roleDescription || null,
          permissions: parsedPermissions,
          parent_role_id: roleParentId || null,
        });
      } else {
        await createRole({
          name: roleName,
          description: roleDescription || null,
          permissions: parsedPermissions,
          parent_role_id: roleParentId || null,
        });
      }
      setRoles(await getRoles());
      resetRoleForm();
      notifySuccess();
    } catch (error) {
      notifyError(error);
    }
  };

  const handleDeleteRole = async (role: RbacRole) => {
    if (!window.confirm(`${t("rbac.delete")} ${role.name}?`)) return;
    try {
      await deleteRole(role.id);
      setRoles(await getRoles());
      if (editingRoleId === role.id) resetRoleForm();
      notifySuccess();
    } catch (error) {
      notifyError(error);
    }
  };

  const handleAssignRole = async () => {
    if (!selectedUserId || !assignmentRoleId) return;
    try {
      await createRoleAssignment({
        user_id: selectedUserId,
        role_id: assignmentRoleId,
        domain_type: assignmentDomainType,
        domain_id: assignmentDomainType === "global" ? null : assignmentDomainId,
      });
      setSelectedSummary(await getIdentitySummary(selectedUserId));
      notifySuccess();
    } catch (error) {
      notifyError(error);
    }
  };

  const handleRevokeAssignment = async (assignmentId: string) => {
    try {
      await deleteRoleAssignment(assignmentId);
      setSelectedSummary(await getIdentitySummary(selectedUserId));
      notifySuccess();
    } catch (error) {
      notifyError(error);
    }
  };

  const handleCreateTeam = async () => {
    try {
      const team = await createTeam({
        team_name: teamName,
        adom_name: teamSlug,
        description: teamDescription || null,
        is_active: true,
      });
      const nextTeams = await getTeams();
      setTeams(nextTeams);
      setSelectedTeamId(team.id);
      setTeamName("");
      setTeamSlug("");
      setTeamDescription("");
      notifySuccess();
    } catch (error) {
      notifyError(error);
    }
  };

  const handleToggleTeam = async (team: Team) => {
    try {
      await updateTeam(team.id, { is_active: !team.is_active });
      setTeams(await getTeams());
      notifySuccess();
    } catch (error) {
      notifyError(error);
    }
  };

  const handleDeleteTeam = async (team: Team) => {
    if (!window.confirm(`${t("rbac.delete")} ${team.team_name}?`)) return;
    try {
      await deleteTeam(team.id);
      const nextTeams = await getTeams();
      setTeams(nextTeams);
      setSelectedTeamId(nextTeams[0]?.id || "");
      notifySuccess();
    } catch (error) {
      notifyError(error);
    }
  };

  const handleAddTeamMember = async () => {
    if (!selectedTeamId || !teamMemberUserId) return;
    try {
      await addTeamMember(selectedTeamId, teamMemberUserId);
      setTeamMembers(await getTeamMembers(selectedTeamId));
      setTeamMemberUserId("");
      notifySuccess();
    } catch (error) {
      notifyError(error);
    }
  };

  const handleRemoveTeamMember = async (userId: string) => {
    try {
      await removeTeamMember(selectedTeamId, userId);
      setTeamMembers(await getTeamMembers(selectedTeamId));
      notifySuccess();
    } catch (error) {
      notifyError(error);
    }
  };

  const handleCreateShare = async () => {
    try {
      await createShare({
        resource_type: shareResourceType,
        resource_id: shareResourceId,
        scope: shareScope,
        target_id: shareScope === "user" || shareScope === "team" ? shareTargetId : null,
        permission_level: shareLevel,
      });
      setShares(await getShares());
      setShareResourceId("");
      setShareTargetId("");
      notifySuccess();
    } catch (error) {
      notifyError(error);
    }
  };

  if (loading && !status) {
    return <div className="flex h-full items-center justify-center text-sm text-muted-foreground">{t("rbac.loading")}</div>;
  }

  return (
    <div className="flex h-full min-w-0 flex-col overflow-hidden px-5 pb-6">
      <div className="flex flex-wrap items-start justify-between gap-3 pb-4">
        <div>
          <h1 className="text-xl font-semibold">{t("rbac.title")}</h1>
          <p className="mt-1 max-w-4xl text-sm text-muted-foreground">{t("rbac.description")}</p>
        </div>
        <Button variant="outline" onClick={() => void loadAll()} loading={loading} ignoreTitleCase>
          {t("rbac.refresh")}
        </Button>
      </div>

      <div className="flex flex-wrap gap-2 border-b pb-3">
        {TABS.map((tab) => (
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
        {activeTab === "overview" && status && (
          <div className="grid gap-4 lg:grid-cols-2">
            <section className={PANEL_CLASS}>
              <div className="flex items-center justify-between gap-3">
                <h2 className="font-semibold">{status.production_ready ? t("rbac.status.ready") : t("rbac.status.notReady")}</h2>
                <StatusBadge enabled={status.production_ready} />
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                {[
                  [t("rbac.status.enforcement"), status.authz_enabled],
                  [t("rbac.status.audit"), status.audit_enabled],
                  [t("rbac.status.autoLogin"), status.auto_login],
                  [t("rbac.status.superuserBypass"), status.superuser_bypass],
                ].map(([label, enabled]) => (
                  <div key={String(label)} className="flex items-center justify-between rounded-md border p-3">
                    <span className="text-sm">{label}</span>
                    <StatusBadge enabled={Boolean(enabled)} />
                  </div>
                ))}
              </div>
              {status.warnings.length > 0 && (
                <div className="mt-4 rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm">
                  {status.warnings.map((warning) => (
                    <p key={warning}>• {warning}</p>
                  ))}
                </div>
              )}
            </section>
            <section className={PANEL_CLASS}>
              <h2 className="font-semibold">{t("rbac.users.effective")}</h2>
              <p className="mt-1 text-xs text-muted-foreground">{selectedSummary?.username || users[0]?.username}</p>
              <div className="mt-3 flex max-h-72 flex-wrap gap-2 overflow-y-auto custom-scroll">
                {(selectedSummary?.effective_permissions || []).map((permission) => (
                  <code key={permission} className="rounded bg-muted px-2 py-1 text-xs">{permission}</code>
                ))}
                {!selectedSummary?.effective_permissions.length && <EmptyState />}
              </div>
            </section>
          </div>
        )}

        {activeTab === "users" && (
          <div className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
            <section className={PANEL_CLASS}>
              <div className={FIELD_CLASS}>
                <label className="text-sm font-medium">{t("rbac.users.search")}</label>
                <div className="flex gap-2">
                  <Input value={userSearch} onChange={(event) => setUserSearch(event.target.value)} />
                  <Button variant="outline" onClick={() => void loadAll()} ignoreTitleCase>{t("rbac.refresh")}</Button>
                </div>
              </div>
              <div className="mt-3 max-h-[520px] space-y-1 overflow-y-auto custom-scroll">
                {users.map((user) => (
                  <button
                    type="button"
                    key={user.id}
                    onClick={() => setSelectedUserId(user.id)}
                    className={`w-full rounded-md border px-3 py-2 text-left text-sm ${selectedUserId === user.id ? "border-primary bg-muted" : "hover:bg-muted/60"}`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate font-medium">{user.username}</span>
                      <span className="text-xs text-muted-foreground">{user.is_superuser ? "superuser" : "user"}</span>
                    </div>
                    <div className="truncate text-xs text-muted-foreground">{user.id}</div>
                  </button>
                ))}
              </div>
            </section>

            <div className="space-y-4">
              <section className={PANEL_CLASS}>
                <h2 className="font-semibold">{t("rbac.users.assign")}</h2>
                <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                  <div className={FIELD_CLASS}>
                    <label className="text-sm">{t("rbac.roles.name")}</label>
                    <select className={SELECT_CLASS} value={assignmentRoleId} onChange={(event) => setAssignmentRoleId(event.target.value)}>
                      {roles.map((role) => <option key={role.id} value={role.id}>{role.name}</option>)}
                    </select>
                  </div>
                  <div className={FIELD_CLASS}>
                    <label className="text-sm">{t("rbac.users.domain")}</label>
                    <select className={SELECT_CLASS} value={assignmentDomainType} onChange={(event) => setAssignmentDomainType(event.target.value)}>
                      {['global', 'organization', 'workspace', 'project', 'channel'].map((domain) => <option key={domain} value={domain}>{domain}</option>)}
                    </select>
                  </div>
                  <div className={`${FIELD_CLASS} xl:col-span-2`}>
                    <label className="text-sm">{t("rbac.users.domainId")}</label>
                    <Input disabled={assignmentDomainType === "global"} value={assignmentDomainId} onChange={(event) => setAssignmentDomainId(event.target.value)} placeholder={t("rbac.users.domainIdHelp")} />
                  </div>
                </div>
                <Button className="mt-3" onClick={() => void handleAssignRole()} disabled={!selectedUserId || !assignmentRoleId || (assignmentDomainType !== "global" && !assignmentDomainId)} ignoreTitleCase>
                  {t("rbac.users.assign")}
                </Button>
              </section>

              <section className={PANEL_CLASS}>
                <h2 className="font-semibold">{t("rbac.users.roles")}</h2>
                <div className="mt-3 space-y-2">
                  {selectedSummary?.assignments.map((assignment) => (
                    <div key={assignment.id} className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-3">
                      <div>
                        <div className="font-medium">{assignment.role_name}</div>
                        <div className="text-xs text-muted-foreground">{assignment.domain_type}{assignment.domain_id ? ` · ${assignment.domain_id}` : ""}</div>
                      </div>
                      <Button variant="destructive" size="sm" onClick={() => void handleRevokeAssignment(assignment.id)} ignoreTitleCase>{t("rbac.remove")}</Button>
                    </div>
                  ))}
                  {!selectedSummary?.assignments.length && <EmptyState />}
                </div>
              </section>

              <div className="grid gap-4 lg:grid-cols-2">
                <section className={PANEL_CLASS}>
                  <h2 className="font-semibold">{t("rbac.users.effective")}</h2>
                  <div className="mt-3 flex max-h-64 flex-wrap gap-2 overflow-y-auto custom-scroll">
                    {selectedSummary?.effective_permissions.map((permission) => <code key={permission} className="rounded bg-muted px-2 py-1 text-xs">{permission}</code>)}
                    {!selectedSummary?.effective_permissions.length && <EmptyState />}
                  </div>
                </section>
                <section className={PANEL_CLASS}>
                  <h2 className="font-semibold">{t("rbac.users.teams")}</h2>
                  <div className="mt-3 space-y-2">
                    {selectedSummary?.teams.map((team) => <div key={team.id} className="rounded-md border p-3 text-sm"><div className="font-medium">{team.team_name}</div><div className="text-xs text-muted-foreground">{team.adom_name} · {team.source}</div></div>)}
                    {!selectedSummary?.teams.length && <EmptyState />}
                  </div>
                </section>
              </div>
            </div>
          </div>
        )}

        {activeTab === "roles" && (
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
            <section className={PANEL_CLASS}>
              <div className="space-y-2">
                {roles.map((role) => (
                  <div key={role.id} className="rounded-md border p-3">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2"><span className="font-medium">{role.name}</span><span className="rounded bg-muted px-2 py-0.5 text-xs">{role.is_system ? t("rbac.roles.system") : t("rbac.roles.custom")}</span></div>
                        <p className="mt-1 text-sm text-muted-foreground">{role.description}</p>
                      </div>
                      {!role.is_system && <div className="flex gap-2"><Button variant="outline" size="sm" onClick={() => editRole(role)} ignoreTitleCase>{t("rbac.roles.edit")}</Button><Button variant="destructive" size="sm" onClick={() => void handleDeleteRole(role)} ignoreTitleCase>{t("rbac.delete")}</Button></div>}
                    </div>
                    <div className="mt-3 flex flex-wrap gap-1.5">{role.permissions.map((permission) => <code key={permission} className="rounded bg-muted px-2 py-1 text-xs">{permission}</code>)}</div>
                  </div>
                ))}
              </div>
            </section>
            <section className={`${PANEL_CLASS} h-fit`}>
              <h2 className="font-semibold">{editingRoleId ? t("rbac.roles.edit") : t("rbac.roles.create")}</h2>
              <div className="mt-3 space-y-3">
                <div className={FIELD_CLASS}><label className="text-sm">{t("rbac.roles.name")}</label><Input value={roleName} onChange={(event) => setRoleName(event.target.value)} /></div>
                <div className={FIELD_CLASS}><label className="text-sm">{t("rbac.roles.description")}</label><Input value={roleDescription} onChange={(event) => setRoleDescription(event.target.value)} /></div>
                <div className={FIELD_CLASS}><label className="text-sm">{t("rbac.roles.parent")}</label><select className={SELECT_CLASS} value={roleParentId} onChange={(event) => setRoleParentId(event.target.value)}><option value="">—</option>{roles.filter((role) => role.id !== editingRoleId).map((role) => <option key={role.id} value={role.id}>{role.name}</option>)}</select></div>
                <div className={FIELD_CLASS}><label className="text-sm">{t("rbac.roles.permissions")}</label><textarea className="min-h-48 rounded-md border border-input bg-background p-3 font-mono text-xs outline-none focus:ring-1 focus:ring-ring" value={rolePermissions} onChange={(event) => setRolePermissions(event.target.value)} /><p className="text-xs text-muted-foreground">{t("rbac.roles.permissionsHelp")}</p></div>
                <div className="flex gap-2"><Button onClick={() => void handleSaveRole()} disabled={!roleName.trim()} ignoreTitleCase>{t("rbac.save")}</Button>{editingRoleId && <Button variant="outline" onClick={resetRoleForm} ignoreTitleCase>{t("rbac.cancel")}</Button>}</div>
              </div>
            </section>
          </div>
        )}

        {activeTab === "teams" && (
          <div className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
            <section className={PANEL_CLASS}>
              <h2 className="font-semibold">{t("rbac.teams.create")}</h2>
              <div className="mt-3 space-y-3">
                <div className={FIELD_CLASS}><label className="text-sm">{t("rbac.teams.name")}</label><Input value={teamName} onChange={(event) => setTeamName(event.target.value)} /></div>
                <div className={FIELD_CLASS}><label className="text-sm">{t("rbac.teams.slug")}</label><Input value={teamSlug} onChange={(event) => setTeamSlug(event.target.value)} /></div>
                <div className={FIELD_CLASS}><label className="text-sm">{t("rbac.teams.description")}</label><Input value={teamDescription} onChange={(event) => setTeamDescription(event.target.value)} /></div>
                <Button onClick={() => void handleCreateTeam()} disabled={!teamName.trim() || !teamSlug.trim()} ignoreTitleCase>{t("rbac.create")}</Button>
              </div>
              <div className="mt-4 space-y-2">
                {teams.map((team) => <button type="button" key={team.id} onClick={() => setSelectedTeamId(team.id)} className={`w-full rounded-md border p-3 text-left ${selectedTeamId === team.id ? "border-primary bg-muted" : "hover:bg-muted/60"}`}><div className="flex items-center justify-between"><span className="font-medium">{team.team_name}</span><StatusBadge enabled={team.is_active} /></div><div className="text-xs text-muted-foreground">{team.adom_name}</div></button>)}
              </div>
            </section>
            <section className={PANEL_CLASS}>
              {selectedTeamId ? <>
                <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-semibold">{teamsById.get(selectedTeamId)?.team_name}</h2><p className="text-xs text-muted-foreground">{teamsById.get(selectedTeamId)?.id}</p></div><div className="flex gap-2"><Button variant="outline" onClick={() => void handleToggleTeam(teamsById.get(selectedTeamId)!)} ignoreTitleCase>{teamsById.get(selectedTeamId)?.is_active ? t("rbac.disabled") : t("rbac.enabled")}</Button><Button variant="destructive" onClick={() => void handleDeleteTeam(teamsById.get(selectedTeamId)!)} ignoreTitleCase>{t("rbac.delete")}</Button></div></div>
                <div className="mt-4 flex gap-2"><select className={`${SELECT_CLASS} flex-1`} value={teamMemberUserId} onChange={(event) => setTeamMemberUserId(event.target.value)}><option value="">{t("rbac.users.select")}</option>{users.filter((user) => !teamMembers.some((member) => member.user_id === user.id)).map((user) => <option key={user.id} value={user.id}>{user.username}</option>)}</select><Button onClick={() => void handleAddTeamMember()} disabled={!teamMemberUserId} ignoreTitleCase>{t("rbac.add")}</Button></div>
                <h3 className="mt-5 font-medium">{t("rbac.teams.members")}</h3>
                <div className="mt-2 space-y-2">{teamMembers.map((member) => <div key={member.id} className="flex items-center justify-between rounded-md border p-3"><div><div className="font-medium">{usersById.get(member.user_id)?.username || member.user_id}</div><div className="text-xs text-muted-foreground">{member.source}</div></div><Button variant="destructive" size="sm" onClick={() => void handleRemoveTeamMember(member.user_id)} ignoreTitleCase>{t("rbac.remove")}</Button></div>)}{teamMembers.length === 0 && <EmptyState />}</div>
              </> : <EmptyState />}
            </section>
          </div>
        )}

        {activeTab === "shares" && (
          <div className="space-y-4">
            <section className={PANEL_CLASS}>
              <h2 className="font-semibold">{t("rbac.shares.create")}</h2>
              <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
                <div className={FIELD_CLASS}><label className="text-sm">{t("rbac.shares.resourceType")}</label><select className={SELECT_CLASS} value={shareResourceType} onChange={(event) => setShareResourceType(event.target.value)}>{['flow','project','knowledge_base','variable','file','deployment'].map((type) => <option key={type} value={type}>{type}</option>)}</select></div>
                <div className={FIELD_CLASS}><label className="text-sm">{t("rbac.shares.resourceId")}</label><Input value={shareResourceId} onChange={(event) => setShareResourceId(event.target.value)} /></div>
                <div className={FIELD_CLASS}><label className="text-sm">{t("rbac.shares.scope")}</label><select className={SELECT_CLASS} value={shareScope} onChange={(event) => setShareScope(event.target.value as ResourceShare["scope"])}>{['user','team','public','private'].map((scope) => <option key={scope} value={scope}>{scope}</option>)}</select></div>
                <div className={FIELD_CLASS}><label className="text-sm">{t("rbac.shares.target")}</label><Input disabled={shareScope === "public" || shareScope === "private"} value={shareTargetId} onChange={(event) => setShareTargetId(event.target.value)} /></div>
                <div className={FIELD_CLASS}><label className="text-sm">{t("rbac.shares.level")}</label><select className={SELECT_CLASS} value={shareLevel} onChange={(event) => setShareLevel(event.target.value as ResourceShare["permission_level"])}>{['read','execute','write','admin'].map((level) => <option key={level} value={level}>{level}</option>)}</select></div>
              </div>
              <Button className="mt-3" onClick={() => void handleCreateShare()} disabled={!shareResourceId || ((shareScope === "user" || shareScope === "team") && !shareTargetId)} ignoreTitleCase>{t("rbac.create")}</Button>
            </section>
            <section className={PANEL_CLASS}>
              <div className="space-y-2">{shares.map((share) => <div key={share.id} className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-3"><div><div className="font-medium">{share.resource_type}:{share.resource_id}</div><div className="text-xs text-muted-foreground">{share.scope}{share.target_id ? ` · ${share.target_id}` : ""}</div></div><div className="flex items-center gap-2"><select className={SELECT_CLASS} value={share.permission_level} onChange={async (event) => { try { await updateShare(share.id, event.target.value as ResourceShare["permission_level"]); setShares(await getShares()); notifySuccess(); } catch (error) { notifyError(error); } }}>{['read','execute','write','admin'].map((level) => <option key={level} value={level}>{level}</option>)}</select><Button variant="destructive" size="sm" onClick={async () => { try { await deleteShare(share.id); setShares(await getShares()); notifySuccess(); } catch (error) { notifyError(error); } }} ignoreTitleCase>{t("rbac.delete")}</Button></div></div>)}{shares.length === 0 && <EmptyState />}</div>
            </section>
          </div>
        )}

        {activeTab === "audit" && (
          <section className={PANEL_CLASS}>
            <div className="flex flex-wrap gap-2"><Input className="max-w-64" placeholder={t("rbac.audit.action")} value={auditAction} onChange={(event) => setAuditAction(event.target.value)} /><Input className="max-w-48" placeholder={t("rbac.audit.resource")} value={auditResourceType} onChange={(event) => setAuditResourceType(event.target.value)} /><select className={SELECT_CLASS} value={auditResult} onChange={(event) => setAuditResult(event.target.value)}><option value="">{t("rbac.audit.result")}</option><option value="allow">allow</option><option value="deny">deny</option><option value="owner_override">owner_override</option></select><Button variant="outline" onClick={() => void loadAudit(1)} ignoreTitleCase>{t("rbac.refresh")}</Button></div>
            <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[900px] text-sm"><thead><tr className="border-b text-left"><th className="p-2">{t("rbac.audit.time")}</th><th className="p-2">{t("rbac.audit.user")}</th><th className="p-2">{t("rbac.audit.action")}</th><th className="p-2">{t("rbac.audit.resource")}</th><th className="p-2">{t("rbac.audit.result")}</th></tr></thead><tbody>{audit.items.map((entry) => <tr key={entry.id} className="border-b"><td className="p-2 whitespace-nowrap">{new Date(entry.timestamp).toLocaleString()}</td><td className="p-2 font-mono text-xs">{entry.user_id || "—"}</td><td className="p-2">{entry.action}</td><td className="p-2 font-mono text-xs">{entry.resource_type || "—"}{entry.resource_id ? `:${entry.resource_id}` : ""}</td><td className="p-2"><span className={`rounded px-2 py-1 text-xs ${entry.result === "deny" ? "bg-destructive/10 text-destructive" : "bg-green-500/10 text-green-700 dark:text-green-300"}`}>{entry.result}</span></td></tr>)}</tbody></table>{audit.items.length === 0 && <EmptyState />}</div>
            <div className="mt-4 flex items-center justify-between"><span className="text-sm text-muted-foreground">{audit.total} · {audit.page}/{Math.max(audit.pages, 1)}</span><div className="flex gap-2"><Button variant="outline" disabled={audit.page <= 1} onClick={() => void loadAudit(audit.page - 1)} ignoreTitleCase>{t("rbac.audit.previous")}</Button><Button variant="outline" disabled={audit.pages === 0 || audit.page >= audit.pages} onClick={() => void loadAudit(audit.page + 1)} ignoreTitleCase>{t("rbac.audit.next")}</Button></div></div>
          </section>
        )}
      </div>
    </div>
  );
}
