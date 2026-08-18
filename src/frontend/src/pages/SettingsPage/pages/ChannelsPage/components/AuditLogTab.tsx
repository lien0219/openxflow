import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import Loading from "@/components/ui/loading";
import { useGetChannelAudits } from "@/controllers/API/queries/channels";
import useChannelCopy from "../use-channel-copy";

interface AuditLogTabProps {
  connectionId: string;
}

const ACTION_LABELS: Record<string, string> = {
  create: "创建",
  update: "更新",
  delete: "删除",
  upsert: "新增或更新",
  retry: "手动重试",
  batch_activate: "批量启用",
  batch_ignore: "批量忽略",
  batch_disable: "批量禁用",
};

const RESOURCE_LABELS: Record<string, string> = {
  connection: "渠道连接",
  conversation: "会话",
  identity: "账号身份",
  command: "工作流指令",
  outbound_delivery: "出站投递",
};

function formatChanges(changes: Record<string, unknown>): string {
  if (Object.keys(changes).length === 0) return "-";
  return JSON.stringify(changes, null, 2);
}

export default function AuditLogTab({ connectionId }: AuditLogTabProps) {
  const copy = useChannelCopy();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [action, setAction] = useState("");
  const [resourceType, setResourceType] = useState("");

  useEffect(() => {
    setPage(1);
    setAction("");
    setResourceType("");
  }, [connectionId]);

  const { data: result, isLoading } = useGetChannelAudits(
    {
      connectionId,
      page,
      pageSize,
      action: action || undefined,
      resourceType: resourceType || undefined,
    },
    { enabled: Boolean(connectionId) },
  );

  return (
    <div className="flex min-w-0 flex-col gap-4 rounded-xl border p-5">
      <div>
        <h3 className="font-semibold">{copy("配置审计")}</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          {copy(
            "追踪连接、会话、账号、指令和人工重试变更；凭据、令牌与密钥始终脱敏。",
          )}
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        <select
          className="primary-input h-10 min-w-[200px] flex-1"
          value={action}
          onChange={(event) => {
            setAction(event.target.value);
            setPage(1);
          }}
        >
          <option value="">{copy("全部操作")}</option>
          <option value="create">{copy("创建")}</option>
          <option value="update">{copy("更新")}</option>
          <option value="delete">{copy("删除")}</option>
          <option value="upsert">{copy("新增或更新")}</option>
          <option value="retry">{copy("手动重试")}</option>
        </select>
        <select
          className="primary-input h-10 min-w-[200px] flex-1"
          value={resourceType}
          onChange={(event) => {
            setResourceType(event.target.value);
            setPage(1);
          }}
        >
          <option value="">{copy("全部资源")}</option>
          {Object.entries(RESOURCE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {copy(label)}
            </option>
          ))}
        </select>
      </div>

      <div className="min-h-44 min-w-0">
        {isLoading ? (
          <div className="flex min-h-44 w-full items-center justify-center">
            <Loading />
          </div>
        ) : (result?.items.length ?? 0) === 0 ? (
          <div className="flex min-h-44 items-center justify-center rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
            {copy("当前筛选条件下暂无审计记录")}
          </div>
        ) : (
          <div className="max-w-full overflow-x-auto">
            <table className="w-full min-w-[920px] table-fixed text-left text-sm">
              <thead className="border-b text-xs text-muted-foreground">
                <tr>
                  <th className="w-40 px-3 py-2">{copy("时间")}</th>
                  <th className="w-20 px-3 py-2">{copy("操作")}</th>
                  <th className="w-52 px-3 py-2">{copy("资源")}</th>
                  <th className="w-52 px-3 py-2">{copy("操作者")}</th>
                  <th className="w-[420px] px-3 py-2">{copy("变更内容")}</th>
                </tr>
              </thead>
              <tbody>
                {(result?.items ?? []).map((audit) => (
                  <tr
                    key={audit.id}
                    className="border-b align-top last:border-0"
                  >
                    <td className="whitespace-nowrap px-3 py-3 text-xs text-muted-foreground">
                      {new Date(audit.created_at).toLocaleString()}
                    </td>
                    <td className="px-3 py-3">
                      {copy(ACTION_LABELS[audit.action] ?? audit.action)}
                    </td>
                    <td className="px-3 py-3">
                      <div>
                        {copy(
                          RESOURCE_LABELS[audit.resource_type] ??
                            audit.resource_type,
                        )}
                      </div>
                      <div
                        className="mt-1 truncate font-mono text-xs text-muted-foreground"
                        title={audit.resource_id ?? undefined}
                      >
                        {audit.resource_id || "-"}
                      </div>
                    </td>
                    <td className="px-3 py-3 font-mono text-xs text-muted-foreground">
                      <div
                        className="truncate"
                        title={audit.actor_user_id ?? undefined}
                      >
                        {audit.actor_user_id || copy("系统")}
                      </div>
                    </td>
                    <td className="min-w-0 px-3 py-3">
                      <pre className="max-h-52 max-w-full overflow-auto whitespace-pre-wrap break-all rounded-md bg-muted/50 p-3 text-xs">
                        {formatChanges(audit.changes_data)}
                      </pre>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4 text-sm">
        <div className="text-muted-foreground">
          {copy("共 {{count}} 条记录", { count: result?.total ?? 0 })}
        </div>
        <div className="flex items-center gap-2">
          <select
            className="primary-input h-9 w-24"
            value={pageSize}
            onChange={(event) => {
              setPageSize(Number(event.target.value));
              setPage(1);
            }}
          >
            {[20, 50, 100].map((size) => (
              <option key={size} value={size}>
                {copy("{{count}} 条", { count: size })}
              </option>
            ))}
          </select>
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((current) => Math.max(1, current - 1))}
          >
            {copy("上一页")}
          </Button>
          <span>
            {page} / {Math.max(1, result?.total_pages ?? 0)}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= (result?.total_pages ?? 0)}
            onClick={() => setPage((current) => current + 1)}
          >
            {copy("下一页")}
          </Button>
        </div>
      </div>
    </div>
  );
}
