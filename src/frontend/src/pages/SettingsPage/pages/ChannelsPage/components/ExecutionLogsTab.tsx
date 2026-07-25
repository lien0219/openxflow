import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import Loading from "@/components/ui/loading";
import {
  type ChannelExecutionIdentityType,
  type ChannelExecutionStatus,
  type ChannelExecutionTrigger,
  useGetChannelExecutions,
} from "@/controllers/API/queries/channels";
import useChannelCopy from "../use-channel-copy";

interface ExecutionLogsTabProps {
  connectionId: string;
}

const TRIGGER_LABELS: Record<ChannelExecutionTrigger, string> = {
  default: "默认工作流",
  command: "自定义指令",
  admin_flow: "管理员调试",
  file: "文件处理",
};

const STATUS_LABELS: Record<ChannelExecutionStatus, string> = {
  queued: "排队中",
  running: "执行中",
  succeeded: "成功",
  failed: "失败",
  timeout: "超时",
  cancelled: "已取消",
  delivery_failed: "投递失败",
};

const IDENTITY_LABELS: Record<ChannelExecutionIdentityType, string> = {
  service: "服务身份",
  bound_user: "绑定用户",
};

function formatDuration(value: number | null): string {
  if (value === null) return "-";
  if (value < 1000) return `${value} ms`;
  return `${(value / 1000).toFixed(2)} s`;
}

export default function ExecutionLogsTab({
  connectionId,
}: ExecutionLogsTabProps) {
  const copy = useChannelCopy();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [queryDraft, setQueryDraft] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<ChannelExecutionStatus | "">("");
  const [triggerType, setTriggerType] = useState<ChannelExecutionTrigger | "">("");
  const [identityType, setIdentityType] = useState<ChannelExecutionIdentityType | "">("");

  useEffect(() => {
    setPage(1);
    setQueryDraft("");
    setQuery("");
    setStatus("");
    setTriggerType("");
    setIdentityType("");
  }, [connectionId]);

  const { data: result, isLoading, isFetching } = useGetChannelExecutions(
    {
      connectionId,
      page,
      pageSize,
      query,
      status,
      triggerType,
      executionIdentityType: identityType,
    },
    { enabled: Boolean(connectionId) },
  );

  const applySearch = () => {
    setQuery(queryDraft.trim());
    setPage(1);
  };

  return (
    <div className="flex flex-col gap-4 rounded-xl border p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold">{copy("渠道运行记录")}</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            {copy("查看排队、执行、超时和最终消息投递的完整生产链路。")}
          </p>
        </div>
        {isFetching && !isLoading ? (
          <span className="text-xs text-muted-foreground">{copy("正在刷新")}</span>
        ) : null}
      </div>

      <div className="grid gap-3 xl:grid-cols-[minmax(260px,2fr)_180px_180px_180px_auto]">
        <Input
          value={queryDraft}
          onChange={(event) => setQueryDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") applySearch();
          }}
          placeholder={copy("搜索事件、渠道用户、线程、指令或错误")}
        />
        <select
          className="primary-input h-10"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value as ChannelExecutionStatus | "");
            setPage(1);
          }}
        >
          <option value="">{copy("全部执行状态")}</option>
          {Object.entries(STATUS_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {copy(label)}
            </option>
          ))}
        </select>
        <select
          className="primary-input h-10"
          value={triggerType}
          onChange={(event) => {
            setTriggerType(event.target.value as ChannelExecutionTrigger | "");
            setPage(1);
          }}
        >
          <option value="">{copy("全部触发方式")}</option>
          {Object.entries(TRIGGER_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {copy(label)}
            </option>
          ))}
        </select>
        <select
          className="primary-input h-10"
          value={identityType}
          onChange={(event) => {
            setIdentityType(event.target.value as ChannelExecutionIdentityType | "");
            setPage(1);
          }}
        >
          <option value="">{copy("全部执行身份")}</option>
          <option value="service">{copy("服务身份")}</option>
          <option value="bound_user">{copy("绑定用户")}</option>
        </select>
        <div className="flex gap-2">
          <Button type="button" onClick={applySearch}>
            {copy("搜索")}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setQueryDraft("");
              setQuery("");
              setStatus("");
              setTriggerType("");
              setIdentityType("");
              setPage(1);
            }}
          >
            {copy("重置")}
          </Button>
        </div>
      </div>

      {isLoading ? (
        <Loading />
      ) : (result?.items.length ?? 0) === 0 ? (
        <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
          {copy("当前筛选条件下暂无运行记录")}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1320px] text-left text-sm">
            <thead className="border-b text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2">{copy("时间")}</th>
                <th className="px-3 py-2">{copy("触发 / 身份")}</th>
                <th className="px-3 py-2">{copy("工作流")}</th>
                <th className="px-3 py-2">{copy("渠道用户 / 线程")}</th>
                <th className="px-3 py-2">{copy("状态")}</th>
                <th className="px-3 py-2">{copy("排队 / 执行 / 投递")}</th>
                <th className="px-3 py-2">{copy("重试")}</th>
                <th className="px-3 py-2">{copy("错误")}</th>
              </tr>
            </thead>
            <tbody>
              {(result?.items ?? []).map((execution) => (
                <tr key={execution.id} className="border-b align-top last:border-0">
                  <td className="whitespace-nowrap px-3 py-3 text-xs text-muted-foreground">
                    {new Date(execution.created_at).toLocaleString()}
                  </td>
                  <td className="px-3 py-3">
                    <div>{copy(TRIGGER_LABELS[execution.trigger_type])}</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {copy(IDENTITY_LABELS[execution.execution_identity_type])}
                      {execution.command_name ? ` · ${execution.command_name}` : ""}
                    </div>
                  </td>
                  <td className="px-3 py-3 font-mono text-xs">
                    <div>{execution.flow_id?.slice(0, 8) ?? copy("工作流已删除")}</div>
                    <div className="mt-1 max-w-48 truncate text-muted-foreground" title={execution.external_event_id}>
                      {execution.external_event_id}
                    </div>
                  </td>
                  <td className="px-3 py-3 font-mono text-xs text-muted-foreground">
                    <div className="max-w-52 truncate" title={execution.external_user_id ?? undefined}>
                      {execution.external_user_id || "-"}
                    </div>
                    <div className="mt-1 max-w-52 truncate" title={execution.session_id ?? undefined}>
                      {execution.session_id || "-"}
                    </div>
                  </td>
                  <td className="px-3 py-3">
                    <span className="rounded-full bg-muted px-2 py-1 text-xs">
                      {copy(STATUS_LABELS[execution.status])}
                    </span>
                  </td>
                  <td className="px-3 py-3 text-xs text-muted-foreground">
                    <div>{copy("排队：{{value}}", { value: formatDuration(execution.queue_wait_ms) })}</div>
                    <div className="mt-1">{copy("执行：{{value}}", { value: formatDuration(execution.duration_ms) })}</div>
                    <div className="mt-1">{copy("投递：{{value}}", { value: formatDuration(execution.delivery_duration_ms) })}</div>
                  </td>
                  <td className="px-3 py-3 text-center">{execution.retry_count}</td>
                  <td className="max-w-80 px-3 py-3 text-xs text-destructive">
                    {execution.error_code ? (
                      <div className="font-mono">{execution.error_code}</div>
                    ) : null}
                    <div className="line-clamp-3">{execution.error_message || "-"}</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

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
