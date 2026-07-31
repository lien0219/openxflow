import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  addTeamMember,
  addTeamRole,
  createTeam,
  deleteTeam,
  getTeamMembers,
  getTeamRoles,
  getTeams,
  getUsers,
  type RbacRole,
  type RbacUser,
  removeTeamMember,
  removeTeamRole,
  type Team,
  type TeamMember,
  type TeamRoleAssignment,
  updateTeam,
} from "@/controllers/API/queries/authz";
import {
  translateRbacRoleName,
  translateRbacValue,
} from "../rbac-i18n";

const PANEL_CLASS = "rounded-lg border bg-card p-4";
const FIELD_CLASS = "flex min-w-0 flex-col gap-1.5";
const SELECT_CLASS =
  "h-10 rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring";

export function TeamsTab({
  roles,
  onSuccess,
  onError,
}: {
  roles: RbacRole[];
  onSuccess: () => void;
  onError: (error: unknown) => void;
}) {
  const { t } = useTranslation();
  const [teams, setTeams] = useState<Team[]>([]);
  const [users, setUsers] = useState<RbacUser[]>([]);
  const [selectedTeamId, setSelectedTeamId] = useState("");
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [teamRoles, setTeamRoles] = useState<TeamRoleAssignment[]>([]);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [description, setDescription] = useState("");
  const [memberUserId, setMemberUserId] = useState("");
  const [teamRoleId, setTeamRoleId] = useState(
    roles.find((role) => role.name === "viewer")?.id || roles[0]?.id || "",
  );
  const [teamRoleDomainType, setTeamRoleDomainType] = useState("global");
  const [teamRoleDomainId, setTeamRoleDomainId] = useState("");

  const reloadTeams = useCallback(async () => {
    const nextTeams = await getTeams();
    setTeams(nextTeams);
    setSelectedTeamId((current) =>
      nextTeams.some((team) => team.id === current)
        ? current
        : nextTeams[0]?.id || "",
    );
  }, []);

  const reloadSelectedTeam = useCallback(async (teamId: string) => {
    const [nextMembers, nextRoles] = await Promise.all([
      getTeamMembers(teamId),
      getTeamRoles(teamId),
    ]);
    setMembers(nextMembers);
    setTeamRoles(nextRoles);
  }, []);

  useEffect(() => {
    Promise.all([getTeams(), getUsers(0, 200)])
      .then(([nextTeams, usersPage]) => {
        setTeams(nextTeams);
        setUsers(usersPage.users);
        setSelectedTeamId(nextTeams[0]?.id || "");
      })
      .catch(onError);
  }, [onError]);

  useEffect(() => {
    if (!selectedTeamId) {
      setMembers([]);
      setTeamRoles([]);
      return;
    }
    reloadSelectedTeam(selectedTeamId).catch(onError);
  }, [onError, reloadSelectedTeam, selectedTeamId]);

  useEffect(() => {
    if (!teamRoleId && roles.length > 0) {
      setTeamRoleId(
        roles.find((role) => role.name === "viewer")?.id || roles[0].id,
      );
    }
  }, [roles, teamRoleId]);

  const usersById = useMemo(
    () => new Map(users.map((user) => [user.id, user])),
    [users],
  );
  const rolesById = useMemo(
    () => new Map(roles.map((role) => [role.id, role])),
    [roles],
  );
  const selectedTeam = teams.find((team) => team.id === selectedTeamId);

  const create = async () => {
    try {
      const team = await createTeam({
        team_name: name,
        adom_name: slug,
        description: description || null,
        is_active: true,
      });
      await reloadTeams();
      setSelectedTeamId(team.id);
      setName("");
      setSlug("");
      setDescription("");
      onSuccess();
    } catch (error) {
      onError(error);
    }
  };

  const toggle = async () => {
    if (!selectedTeam) return;
    try {
      await updateTeam(selectedTeam.id, { is_active: !selectedTeam.is_active });
      await reloadTeams();
      onSuccess();
    } catch (error) {
      onError(error);
    }
  };

  const removeTeam = async () => {
    if (
      !selectedTeam ||
      !window.confirm(
        t("rbac.confirmDelete", { name: selectedTeam.team_name }),
      )
    ) {
      return;
    }
    try {
      await deleteTeam(selectedTeam.id);
      await reloadTeams();
      onSuccess();
    } catch (error) {
      onError(error);
    }
  };

  const addMember = async () => {
    if (!selectedTeamId || !memberUserId) return;
    try {
      await addTeamMember(selectedTeamId, memberUserId);
      await reloadSelectedTeam(selectedTeamId);
      setMemberUserId("");
      onSuccess();
    } catch (error) {
      onError(error);
    }
  };

  const removeMember = async (userId: string) => {
    try {
      await removeTeamMember(selectedTeamId, userId);
      await reloadSelectedTeam(selectedTeamId);
      onSuccess();
    } catch (error) {
      onError(error);
    }
  };

  const addPersistentTeamRole = async () => {
    if (!selectedTeamId || !teamRoleId) return;
    try {
      await addTeamRole(selectedTeamId, {
        role_id: teamRoleId,
        domain_type: teamRoleDomainType,
        domain_id:
          teamRoleDomainType === "global" ? null : teamRoleDomainId.trim(),
      });
      await reloadSelectedTeam(selectedTeamId);
      onSuccess();
    } catch (error) {
      onError(error);
    }
  };

  const removePersistentTeamRole = async (ruleId: number) => {
    try {
      await removeTeamRole(selectedTeamId, ruleId);
      await reloadSelectedTeam(selectedTeamId);
      onSuccess();
    } catch (error) {
      onError(error);
    }
  };

  return (
    <div className="grid gap-4 xl:grid-cols-[340px_minmax(0,1fr)]">
      <section className={PANEL_CLASS}>
        <h2 className="font-semibold">{t("rbac.teams.create")}</h2>
        <div className="mt-3 space-y-3">
          <div className={FIELD_CLASS}>
            <label className="text-sm">{t("rbac.teams.name")}</label>
            <Input
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div className={FIELD_CLASS}>
            <label className="text-sm">{t("rbac.teams.slug")}</label>
            <Input
              value={slug}
              onChange={(event) => setSlug(event.target.value)}
            />
          </div>
          <div className={FIELD_CLASS}>
            <label className="text-sm">{t("rbac.teams.description")}</label>
            <Input
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </div>
          <Button
            onClick={() => void create()}
            disabled={!name.trim() || !slug.trim()}
            ignoreTitleCase
          >
            {t("rbac.create")}
          </Button>
        </div>
        <div className="mt-4 space-y-2">
          {teams.map((team) => (
            <button
              type="button"
              key={team.id}
              onClick={() => setSelectedTeamId(team.id)}
              className={`w-full rounded-md border p-3 text-left ${
                selectedTeamId === team.id
                  ? "border-primary bg-muted"
                  : "hover:bg-muted/60"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium">{team.team_name}</span>
                <span className="text-xs text-muted-foreground">
                  {team.is_active ? t("rbac.enabled") : t("rbac.disabled")}
                </span>
              </div>
              <div className="text-xs text-muted-foreground">
                {team.adom_name}
              </div>
            </button>
          ))}
        </div>
      </section>

      <section className={PANEL_CLASS}>
        {selectedTeam ? (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="font-semibold">{selectedTeam.team_name}</h2>
                <p className="text-xs text-muted-foreground">
                  {selectedTeam.id}
                </p>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  onClick={() => void toggle()}
                  ignoreTitleCase
                >
                  {selectedTeam.is_active
                    ? t("rbac.disabled")
                    : t("rbac.enabled")}
                </Button>
                <Button
                  variant="destructive"
                  onClick={() => void removeTeam()}
                  ignoreTitleCase
                >
                  {t("rbac.delete")}
                </Button>
              </div>
            </div>

            <div className="mt-5 rounded-md border p-3">
              <h3 className="font-medium">{t("rbac.teams.roles")}</h3>
              <p className="mt-1 text-xs text-muted-foreground">
                {t("rbac.teams.rolesHelp")}
              </p>
              <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <div className={FIELD_CLASS}>
                  <label className="text-sm">{t("rbac.roles.name")}</label>
                  <select
                    className={SELECT_CLASS}
                    value={teamRoleId}
                    onChange={(event) => setTeamRoleId(event.target.value)}
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
                    value={teamRoleDomainType}
                    onChange={(event) => {
                      setTeamRoleDomainType(event.target.value);
                      if (event.target.value === "global") {
                        setTeamRoleDomainId("");
                      }
                    }}
                  >
                    {[
                      "global",
                      "organization",
                      "workspace",
                      "project",
                      "channel",
                    ].map((domain) => (
                      <option key={domain} value={domain}>
                        {translateRbacValue(t, "domain", domain)}
                      </option>
                    ))}
                  </select>
                </div>
                <div className={`${FIELD_CLASS} xl:col-span-2`}>
                  <label className="text-sm">{t("rbac.users.domainId")}</label>
                  <Input
                    disabled={teamRoleDomainType === "global"}
                    value={teamRoleDomainId}
                    onChange={(event) =>
                      setTeamRoleDomainId(event.target.value.trim())
                    }
                    placeholder={t("rbac.users.domainIdHelp")}
                  />
                </div>
              </div>
              <Button
                className="mt-3"
                onClick={() => void addPersistentTeamRole()}
                disabled={
                  !teamRoleId ||
                  (teamRoleDomainType !== "global" && !teamRoleDomainId)
                }
                ignoreTitleCase
              >
                {t("rbac.teams.addRole")}
              </Button>

              <div className="mt-3 space-y-2">
                {teamRoles.map((grant) => {
                  const role = rolesById.get(grant.role_id);
                  return (
                    <div
                      key={grant.id}
                      className="flex flex-wrap items-center justify-between gap-3 rounded-md bg-muted/40 p-3"
                    >
                      <div>
                        <div className="font-medium">
                          {role
                            ? translateRbacRoleName(
                                t,
                                role.name,
                                role.is_system,
                              )
                            : grant.role_id}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {translateRbacValue(
                            t,
                            "domain",
                            grant.domain_type,
                          )}
                          {grant.domain_id ? ` · ${grant.domain_id}` : ""}
                        </div>
                      </div>
                      <Button
                        variant="destructive"
                        size="sm"
                        onClick={() =>
                          void removePersistentTeamRole(grant.id)
                        }
                        ignoreTitleCase
                      >
                        {t("rbac.remove")}
                      </Button>
                    </div>
                  );
                })}
                {teamRoles.length === 0 && (
                  <div className="py-4 text-center text-sm text-muted-foreground">
                    {t("rbac.empty")}
                  </div>
                )}
              </div>
            </div>

            <div className="mt-5 flex gap-2">
              <select
                className={`${SELECT_CLASS} flex-1`}
                value={memberUserId}
                onChange={(event) => setMemberUserId(event.target.value)}
              >
                <option value="">{t("rbac.users.select")}</option>
                {users
                  .filter(
                    (user) =>
                      !members.some((member) => member.user_id === user.id),
                  )
                  .map((user) => (
                    <option key={user.id} value={user.id}>
                      {user.username}
                    </option>
                  ))}
              </select>
              <Button
                onClick={() => void addMember()}
                disabled={!memberUserId}
                ignoreTitleCase
              >
                {t("rbac.add")}
              </Button>
            </div>

            <h3 className="mt-5 font-medium">{t("rbac.teams.members")}</h3>
            <div className="mt-2 space-y-2">
              {members.map((member) => (
                <div
                  key={member.id}
                  className="flex items-center justify-between rounded-md border p-3"
                >
                  <div>
                    <div className="font-medium">
                      {usersById.get(member.user_id)?.username ||
                        member.user_id}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {translateRbacValue(
                        t,
                        "memberSource",
                        member.source,
                      )}
                    </div>
                  </div>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => void removeMember(member.user_id)}
                    ignoreTitleCase
                  >
                    {t("rbac.remove")}
                  </Button>
                </div>
              ))}
              {members.length === 0 && (
                <div className="py-8 text-center text-sm text-muted-foreground">
                  {t("rbac.empty")}
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="py-8 text-center text-sm text-muted-foreground">
            {t("rbac.empty")}
          </div>
        )}
      </section>
    </div>
  );
}
