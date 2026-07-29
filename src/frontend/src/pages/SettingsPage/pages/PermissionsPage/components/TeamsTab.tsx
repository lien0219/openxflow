import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  addTeamMember,
  createTeam,
  deleteTeam,
  getTeamMembers,
  getTeams,
  getUsers,
  removeTeamMember,
  updateTeam,
  type RbacUser,
  type Team,
  type TeamMember,
} from "@/controllers/API/queries/authz";

const PANEL_CLASS = "rounded-lg border bg-card p-4";
const FIELD_CLASS = "flex min-w-0 flex-col gap-1.5";
const SELECT_CLASS =
  "h-10 rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring";

export function TeamsTab({
  onSuccess,
  onError,
}: {
  onSuccess: () => void;
  onError: (error: unknown) => void;
}) {
  const { t } = useTranslation();
  const [teams, setTeams] = useState<Team[]>([]);
  const [users, setUsers] = useState<RbacUser[]>([]);
  const [selectedTeamId, setSelectedTeamId] = useState("");
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [description, setDescription] = useState("");
  const [memberUserId, setMemberUserId] = useState("");

  const reloadTeams = async () => {
    const nextTeams = await getTeams();
    setTeams(nextTeams);
    setSelectedTeamId((current) =>
      nextTeams.some((team) => team.id === current)
        ? current
        : nextTeams[0]?.id || "",
    );
  };

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
      return;
    }
    getTeamMembers(selectedTeamId).then(setMembers).catch(onError);
  }, [onError, selectedTeamId]);

  const usersById = useMemo(
    () => new Map(users.map((user) => [user.id, user])),
    [users],
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
    if (!selectedTeam || !window.confirm(`${t("rbac.delete")} ${selectedTeam.team_name}?`)) return;
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
      setMembers(await getTeamMembers(selectedTeamId));
      setMemberUserId("");
      onSuccess();
    } catch (error) {
      onError(error);
    }
  };

  const removeMember = async (userId: string) => {
    try {
      await removeTeamMember(selectedTeamId, userId);
      setMembers(await getTeamMembers(selectedTeamId));
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
            <Input value={name} onChange={(event) => setName(event.target.value)} />
          </div>
          <div className={FIELD_CLASS}>
            <label className="text-sm">{t("rbac.teams.slug")}</label>
            <Input value={slug} onChange={(event) => setSlug(event.target.value)} />
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
                <Button variant="outline" onClick={() => void toggle()} ignoreTitleCase>
                  {selectedTeam.is_active ? t("rbac.disabled") : t("rbac.enabled")}
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

            <div className="mt-4 flex gap-2">
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
                      {usersById.get(member.user_id)?.username || member.user_id}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {member.source}
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
