import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  createShare,
  deleteShare,
  getShares,
  type ResourceShare,
  updateShare,
} from "@/controllers/API/queries/authz";
import { translateRbacValue } from "../rbac-i18n";

const PANEL_CLASS = "rounded-lg border bg-card p-4";
const FIELD_CLASS = "flex min-w-0 flex-col gap-1.5";
const SELECT_CLASS =
  "h-10 rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring";

export function SharesTab({
  canCreate,
  onSuccess,
  onError,
}: {
  canCreate: boolean;
  onSuccess: () => void;
  onError: (error: unknown) => void;
}) {
  const { t } = useTranslation();
  const [shares, setShares] = useState<ResourceShare[]>([]);
  const [resourceType, setResourceType] = useState("flow");
  const [resourceId, setResourceId] = useState("");
  const [scope, setScope] = useState<ResourceShare["scope"]>("user");
  const [targetId, setTargetId] = useState("");
  const [level, setLevel] = useState<ResourceShare["permission_level"]>("read");

  const reload = useCallback(async () => {
    setShares(await getShares());
  }, []);

  useEffect(() => {
    reload().catch(onError);
  }, [onError, reload]);

  const create = async () => {
    try {
      await createShare({
        resource_type: resourceType,
        resource_id: resourceId,
        scope,
        target_id: scope === "user" || scope === "team" ? targetId : null,
        permission_level: level,
      });
      await reload();
      setResourceId("");
      setTargetId("");
      onSuccess();
    } catch (error) {
      onError(error);
    }
  };

  const changeLevel = async (
    shareId: string,
    permissionLevel: ResourceShare["permission_level"],
  ) => {
    try {
      await updateShare(shareId, permissionLevel);
      await reload();
      onSuccess();
    } catch (error) {
      onError(error);
    }
  };

  const remove = async (shareId: string) => {
    try {
      await deleteShare(shareId);
      await reload();
      onSuccess();
    } catch (error) {
      onError(error);
    }
  };

  const resourceTypes = [
    "flow",
    "project",
    "knowledge_base",
    "variable",
    "file",
    "deployment",
  ];
  const shareScopes: ResourceShare["scope"][] = [
    "user",
    "team",
    "public",
    "private",
  ];
  const permissionLevels: ResourceShare["permission_level"][] = [
    "read",
    "execute",
    "write",
    "admin",
  ];

  return (
    <div className="space-y-4">
      {canCreate && (
        <section className={PANEL_CLASS}>
          <h2 className="font-semibold">{t("rbac.shares.create")}</h2>
          <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            <div className={FIELD_CLASS}>
              <label className="text-sm">{t("rbac.shares.resourceType")}</label>
              <select
                className={SELECT_CLASS}
                value={resourceType}
                onChange={(event) => setResourceType(event.target.value)}
              >
                {resourceTypes.map((type) => (
                  <option key={type} value={type}>
                    {translateRbacValue(t, "resourceType", type)}
                  </option>
                ))}
              </select>
            </div>
            <div className={FIELD_CLASS}>
              <label className="text-sm">{t("rbac.shares.resourceId")}</label>
              <Input
                value={resourceId}
                onChange={(event) => setResourceId(event.target.value.trim())}
              />
            </div>
            <div className={FIELD_CLASS}>
              <label className="text-sm">{t("rbac.shares.scope")}</label>
              <select
                className={SELECT_CLASS}
                value={scope}
                onChange={(event) =>
                  setScope(event.target.value as ResourceShare["scope"])
                }
              >
                {shareScopes.map((item) => (
                  <option key={item} value={item}>
                    {translateRbacValue(t, "shareScope", item)}
                  </option>
                ))}
              </select>
            </div>
            <div className={FIELD_CLASS}>
              <label className="text-sm">{t("rbac.shares.target")}</label>
              <Input
                disabled={scope === "public" || scope === "private"}
                value={targetId}
                onChange={(event) => setTargetId(event.target.value.trim())}
              />
            </div>
            <div className={FIELD_CLASS}>
              <label className="text-sm">{t("rbac.shares.level")}</label>
              <select
                className={SELECT_CLASS}
                value={level}
                onChange={(event) =>
                  setLevel(
                    event.target.value as ResourceShare["permission_level"],
                  )
                }
              >
                {permissionLevels.map((item) => (
                  <option key={item} value={item}>
                    {translateRbacValue(t, "permissionLevel", item)}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <Button
            className="mt-3"
            onClick={() => void create()}
            disabled={
              !resourceId ||
              ((scope === "user" || scope === "team") && !targetId)
            }
            ignoreTitleCase
          >
            {t("rbac.create")}
          </Button>
        </section>
      )}

      <section className={PANEL_CLASS}>
        <div className="space-y-2">
          {shares.map((share) => (
            <div
              key={share.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-3"
            >
              <div>
                <div className="font-medium">
                  {translateRbacValue(t, "resourceType", share.resource_type)}：
                  {share.resource_id}
                </div>
                <div className="text-xs text-muted-foreground">
                  {translateRbacValue(t, "shareScope", share.scope)}
                  {share.target_id ? ` · ${share.target_id}` : ""}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <select
                  className={SELECT_CLASS}
                  value={share.permission_level}
                  onChange={(event) =>
                    void changeLevel(
                      share.id,
                      event.target.value as ResourceShare["permission_level"],
                    )
                  }
                >
                  {permissionLevels.map((item) => (
                    <option key={item} value={item}>
                      {translateRbacValue(t, "permissionLevel", item)}
                    </option>
                  ))}
                </select>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => void remove(share.id)}
                  ignoreTitleCase
                >
                  {t("rbac.delete")}
                </Button>
              </div>
            </div>
          ))}
          {shares.length === 0 && (
            <div className="py-8 text-center text-sm text-muted-foreground">
              {t("rbac.empty")}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
