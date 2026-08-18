import { useTranslation } from "react-i18next";
import { translateRbacPermission } from "../rbac-i18n";

export function PermissionBadge({ permission }: { permission: string }) {
  const { t } = useTranslation();

  return (
    <span
      className="inline-flex max-w-full items-center gap-1.5 rounded bg-muted px-2 py-1 text-xs"
      title={permission}
    >
      <span className="truncate">{translateRbacPermission(t, permission)}</span>
      <code className="shrink-0 text-[10px] text-muted-foreground">
        {permission}
      </code>
    </span>
  );
}
