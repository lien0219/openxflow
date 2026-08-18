import type { TFunction } from "i18next";
import type { RbacRole } from "@/controllers/API/queries/authz";

const WARNING_KEYS: Record<string, string> = {
  "AUTO_LOGIN is enabled; disable it before using multi-user RBAC in production.":
    "rbac.status.warnings.autoLogin",
  "RBAC enforcement is disabled; role decisions are not currently blocking requests.":
    "rbac.status.warnings.enforcement",
  "Authorization audit logging is disabled.": "rbac.status.warnings.audit",
};

export function translateRbacWarning(t: TFunction, warning: string): string {
  const key = WARNING_KEYS[warning];
  return key ? t(key) : warning;
}

export function translateRbacValue(
  t: TFunction,
  group: string,
  value: string | null | undefined,
): string {
  if (!value) return "—";
  return t(`rbac.values.${group}.${value}`, { defaultValue: value });
}

export function translateRbacPermission(
  t: TFunction,
  permission: string,
): string {
  const separatorIndex = permission.indexOf(":");
  if (separatorIndex <= 0 || separatorIndex === permission.length - 1) {
    return permission;
  }

  const resource = permission.slice(0, separatorIndex);
  const action = permission.slice(separatorIndex + 1);
  const resourceLabel = translateRbacValue(t, "resourceType", resource);
  const actionLabel = translateRbacValue(t, "permissionAction", action);

  return t("rbac.permission.label", {
    resource: resourceLabel,
    action: actionLabel,
    defaultValue: `${resourceLabel}: ${actionLabel}`,
  });
}

export function translateRbacRoleName(
  t: TFunction,
  roleName: string,
  isSystem = true,
): string {
  if (!isSystem) return roleName;
  return t(`rbac.systemRoles.${roleName}.name`, { defaultValue: roleName });
}

export function translateRbacRoleDescription(
  t: TFunction,
  role: Pick<RbacRole, "name" | "description" | "is_system">,
): string {
  if (!role.is_system) return role.description || "";
  return t(`rbac.systemRoles.${role.name}.description`, {
    defaultValue: role.description || "",
  });
}
