import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  createRole,
  deleteRole,
  type RbacRole,
  updateRole,
} from "@/controllers/API/queries/authz";

const PANEL_CLASS = "rounded-lg border bg-card p-4";
const FIELD_CLASS = "flex min-w-0 flex-col gap-1.5";
const SELECT_CLASS =
  "h-10 rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring";

export function RolesTab({
  roles,
  canManage,
  onReload,
  onSuccess,
  onError,
}: {
  roles: RbacRole[];
  canManage: boolean;
  onReload: () => Promise<void>;
  onSuccess: () => void;
  onError: (error: unknown) => void;
}) {
  const { t } = useTranslation();
  const [editingRoleId, setEditingRoleId] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [permissions, setPermissions] = useState("");
  const [parentRoleId, setParentRoleId] = useState("");

  const parsedPermissions = useMemo(
    () =>
      Array.from(
        new Set(
          permissions
            .split(/[\n,]/)
            .map((item) => item.trim().toLowerCase())
            .filter(Boolean),
        ),
      ),
    [permissions],
  );

  const reset = () => {
    setEditingRoleId("");
    setName("");
    setDescription("");
    setPermissions("");
    setParentRoleId("");
  };

  const edit = (role: RbacRole) => {
    setEditingRoleId(role.id);
    setName(role.name);
    setDescription(role.description || "");
    setPermissions(role.permissions.join("\n"));
    setParentRoleId(role.parent_role_id || "");
  };

  const save = async () => {
    try {
      if (editingRoleId) {
        await updateRole(editingRoleId, {
          name,
          description: description || null,
          permissions: parsedPermissions,
          parent_role_id: parentRoleId || null,
        });
      } else {
        await createRole({
          name,
          description: description || null,
          permissions: parsedPermissions,
          parent_role_id: parentRoleId || null,
        });
      }
      await onReload();
      reset();
      onSuccess();
    } catch (error) {
      onError(error);
    }
  };

  const remove = async (role: RbacRole) => {
    if (!window.confirm(`${t("rbac.delete")} ${role.name}?`)) return;
    try {
      await deleteRole(role.id);
      await onReload();
      if (editingRoleId === role.id) reset();
      onSuccess();
    } catch (error) {
      onError(error);
    }
  };

  return (
    <div
      className={
        canManage
          ? "grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]"
          : "grid gap-4"
      }
    >
      <section className={PANEL_CLASS}>
        <div className="space-y-2">
          {roles.map((role) => (
            <div key={role.id} className="rounded-md border p-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{role.name}</span>
                    <span className="rounded bg-muted px-2 py-0.5 text-xs">
                      {role.is_system
                        ? t("rbac.roles.system")
                        : t("rbac.roles.custom")}
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {role.description}
                  </p>
                </div>
                {canManage && !role.is_system && (
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => edit(role)}
                      ignoreTitleCase
                    >
                      {t("rbac.roles.edit")}
                    </Button>
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => void remove(role)}
                      ignoreTitleCase
                    >
                      {t("rbac.delete")}
                    </Button>
                  </div>
                )}
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {role.permissions.map((permission) => (
                  <code
                    key={permission}
                    className="rounded bg-muted px-2 py-1 text-xs"
                  >
                    {permission}
                  </code>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {canManage && (
        <section className={`${PANEL_CLASS} h-fit`}>
          <h2 className="font-semibold">
            {editingRoleId ? t("rbac.roles.edit") : t("rbac.roles.create")}
          </h2>
          <div className="mt-3 space-y-3">
            <div className={FIELD_CLASS}>
              <label className="text-sm">{t("rbac.roles.name")}</label>
              <Input
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </div>
            <div className={FIELD_CLASS}>
              <label className="text-sm">{t("rbac.roles.description")}</label>
              <Input
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </div>
            <div className={FIELD_CLASS}>
              <label className="text-sm">{t("rbac.roles.parent")}</label>
              <select
                className={SELECT_CLASS}
                value={parentRoleId}
                onChange={(event) => setParentRoleId(event.target.value)}
              >
                <option value="">—</option>
                {roles
                  .filter((role) => role.id !== editingRoleId)
                  .map((role) => (
                    <option key={role.id} value={role.id}>
                      {role.name}
                    </option>
                  ))}
              </select>
            </div>
            <div className={FIELD_CLASS}>
              <label className="text-sm">{t("rbac.roles.permissions")}</label>
              <textarea
                className="min-h-48 rounded-md border border-input bg-background p-3 font-mono text-xs outline-none focus:ring-1 focus:ring-ring"
                value={permissions}
                onChange={(event) => setPermissions(event.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                {t("rbac.roles.permissionsHelp")}
              </p>
            </div>
            <div className="flex gap-2">
              <Button
                onClick={() => void save()}
                disabled={!name.trim()}
                ignoreTitleCase
              >
                {t("rbac.save")}
              </Button>
              {editingRoleId && (
                <Button variant="outline" onClick={reset} ignoreTitleCase>
                  {t("rbac.cancel")}
                </Button>
              )}
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
