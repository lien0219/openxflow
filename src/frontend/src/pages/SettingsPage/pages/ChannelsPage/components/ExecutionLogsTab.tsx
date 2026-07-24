import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import Loading from "@/components/ui/loading";
import {
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
  running: "执行中",
  succeeded: "成功",
  failed: "失败",
};

export default function ExecutionLogsTab({
  connectionId,
}: ExecutionLogsTabProps) {
  const copy = useChannelCopy();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [status, setStatus] = useState<ChannelExecutionStatus | "">("");
  const [triggerType, setTriggerType] = useState<ChannelExecutionTrigger | "">(
    "",
  );

  useEffect(() => {
    setPage(1);
  }, [connectionId]);

  const { data: result, isLoading } = useGetChannelExecutions(
    {
      connectionId,
      page,
      pageSize,
      status,
      triggerType,
    },
    { enabled: Boolean(connectionId) },
  );

  return (
    <div className="flex flex-col gap-4 rounded-xl border p-5">
      <div>
        <h3 className="font-semibold">{copy("渠道运行记录")}</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          {copy("查看默认路由、指令路由和管理员调试触发的工作流执行结果。")}
        </p>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <select
          className="primary-input h-10"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value as ChannelExecutionStatus | "");
            setPage(1);
          }}
        >
          <option value="">{copy("全部执行状态")}</option>
          <option value="running">{copy("执行中")}</option>
          <option value="succeeded">{copy("成功")}</option>
          <option value="failed">{copy("失败")}</option>
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
          <option value="default">{copy("默认工作流")}</option>
          <option value="command">{copy("自定义指令")}</option>
          <option value="admin_flow">{copy("管理员调试")}</option>
          <option value="file">{copy("文件处理")}</option>
        </select>
      </div>

      {isLoading ? (
        <Loading />
      ) : (result?.items.length ?? 0) === 0 ? (
        <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
          {copy("当前筛选条件下暂无运行记录")}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead className="border-b text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2">{copy("时间")}</th>
                <th className="px-3 py-2">{copy("触发方式")}</th>
                <th className="px-3 py-2">{copy("工作流")}</th>
                <th className="px-3 py-2">{copy("会话 / 用户")}</th>
                <th className="px-3 py-2">{copy("状态")}</th>
                <th className="px-3 py-2">{copy("耗时")}</th>
                <th className="px-3 py-2">{copy("错误")}</th>
              </tr>
            </thead>
            <tbody>
              {(result?.items ?? []).map((execution) => (
                <tr key={execution.id} className="border-b last:border-0">
                  <td className="px-3 py-3 text-xs text-muted-foreground">
                    {new Date(execution.created_at).toLocaleString()}
                  </td>
                  <td className="px-3 py-3">
                    {copy(TRIGGER_LABELS[execution.trigger_type])}
                    {execution.command_name
                      ? ` · ${execution.command_name}`
                      : ""}
                  </td>
                  <td className="px-3 py-3 font-mono text-xs">
                    {execution.flow_id?.slice(0, 8) ?? copy("工作流已删除")}
                  </td>
                  <td className="px-3 py-3 font-mono text-xs text-muted-foreground">
                    <div>
                      {copy("会话：{{id}}", {
                        id:
                          execution.conversation_binding_id?.slice(0, 8) ?? "-",
                      })}
                    </div>
                    <div>
                      {copy("用户：{{id}}", {
                        id: execution.openxflow_user_id?.slice(0, 8) ?? "-",
                      })}
                    </div>
                  </td>
                  <td className="px-3 py-3">
                    <span className="rounded-full bg-muted px-2 py-1 text-xs">
                      {copy(STATUS_LABELS[execution.status])}
                    </span>
                  </td>
                  <td className="px-3 py-3 text-xs text-muted-foreground">
                    {execution.duration_ms === null
                      ? "-"
                      : `${execution.duration_ms} ms`}
                  </td>
                  <td className="max-w-72 px-3 py-3 text-xs text-destructive">
                    <div className="line-clamp-2">
                      {execution.error_message || "-"}
                    </div>
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
            <option value={20}>{copy("{{count}} 条", { count: 20 })}</option>
            <option value={50}>{copy("{{count}} 条", { count: 50 })}</option>
            <option value={100}>{copy("{{count}} 条", { count: 100 })}</option>
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
