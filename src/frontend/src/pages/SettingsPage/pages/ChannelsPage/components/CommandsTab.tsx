import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import Loading from "@/components/ui/loading";
import {
  type ChannelCommandScope,
  type ChannelWorkflowCommand,
  type ChannelWorkflowCommandCreate,
  type ChannelWorkflowCommandUpdate,
  useCreateChannelCommand,
  useDeleteChannelCommand,
  useGetChannelCommands,
  useUpdateChannelCommand,
} from "@/controllers/API/queries/channels";
import DeleteConfirmationModal from "@/modals/deleteConfirmationModal";
import useAlertStore from "@/stores/alertStore";
import useChannelCopy from "../use-channel-copy";
import CommandDialog from "./CommandDialog";

interface CommandsTabProps {
  connectionId: string;
}

const SCOPE_LABELS: Record<ChannelCommandScope, string> = {
  connection_shared: "连接共享",
  conversation_shared: "会话共享",
  identity_connection: "我的连接指令",
  identity_conversation: "我的会话指令",
};

export default function CommandsTab({ connectionId }: CommandsTabProps) {
  const copy = useChannelCopy();
  const setSuccessData = useAlertStore((state) => state.setSuccessData);
  const setErrorData = useAlertStore((state) => state.setErrorData);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [scopeType, setScopeType] = useState<ChannelCommandScope | "">("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingCommand, setEditingCommand] =
    useState<ChannelWorkflowCommand | null>(null);
  const [deleteTarget, setDeleteTarget] =
    useState<ChannelWorkflowCommand | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setQuery(queryInput.trim());
      setPage(1);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [queryInput]);

  useEffect(() => {
    setPage(1);
    setDialogOpen(false);
    setEditingCommand(null);
  }, [connectionId]);

  const { data: result, isLoading } = useGetChannelCommands(
    {
      connectionId,
      page,
      pageSize,
      query,
      scopeType,
    },
    { enabled: Boolean(connectionId) },
  );
  const createCommand = useCreateChannelCommand();
  const updateCommand = useUpdateChannelCommand();
  const deleteCommand = useDeleteChannelCommand();

  const showError = (title: string, error: unknown) =>
    setErrorData({
      title,
      list: [error instanceof Error ? error.message : String(error)],
    });

  const handleCreate = async (payload: ChannelWorkflowCommandCreate) => {
    try {
      await createCommand.mutateAsync({ connectionId, payload });
      setDialogOpen(false);
      setSuccessData({ title: copy("自定义指令已创建") });
    } catch (error) {
      showError(copy("创建指令失败"), error);
      throw error;
    }
  };

  const handleUpdate = async (payload: ChannelWorkflowCommandUpdate) => {
    if (!editingCommand) return;
    try {
      await updateCommand.mutateAsync({
        connectionId,
        commandId: editingCommand.id,
        payload,
      });
      setDialogOpen(false);
      setEditingCommand(null);
      setSuccessData({ title: copy("自定义指令已更新") });
    } catch (error) {
      showError(copy("更新指令失败"), error);
      throw error;
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteCommand.mutateAsync({
        connectionId,
        commandId: deleteTarget.id,
      });
      setDeleteTarget(null);
      setSuccessData({ title: copy("自定义指令已删除") });
    } catch (error) {
      showError(copy("删除指令失败"), error);
    }
  };

  return (
    <div className="flex flex-col gap-4 rounded-xl border p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 className="font-semibold">{copy("自定义指令中心")}</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            {copy(
              "普通消息使用默认工作流；“/指令 内容”仅本次路由到指定工作流。",
            )}
          </p>
        </div>
        <Button
          variant="primary"
          size="sm"
          onClick={() => {
            setEditingCommand(null);
            setDialogOpen(true);
          }}
        >
          {copy("新增指令")}
        </Button>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <Input
          value={queryInput}
          onChange={(event) => setQueryInput(event.target.value)}
          placeholder={copy("搜索指令名称或说明")}
        />
        <select
          className="primary-input h-10"
          value={scopeType}
          onChange={(event) => {
            setScopeType(event.target.value as ChannelCommandScope | "");
            setPage(1);
          }}
        >
          <option value="">{copy("全部作用域")}</option>
          {Object.entries(SCOPE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {copy(label)}
            </option>
          ))}
        </select>
      </div>

      {isLoading ? (
        <Loading />
      ) : (result?.items.length ?? 0) === 0 ? (
        <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
          {copy(
            "暂无匹配指令。可创建连接共享、会话共享或仅自己可用的个人指令。",
          )}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[840px] text-left text-sm">
            <thead className="border-b text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2">{copy("指令")}</th>
                <th className="px-3 py-2">{copy("作用域")}</th>
                <th className="px-3 py-2">{copy("工作流")}</th>
                <th className="px-3 py-2">{copy("策略")}</th>
                <th className="px-3 py-2">{copy("最近使用")}</th>
                <th className="px-3 py-2 text-right">{copy("操作")}</th>
              </tr>
            </thead>
            <tbody>
              {(result?.items ?? []).map((command) => (
                <tr key={command.id} className="border-b last:border-0">
                  <td className="px-3 py-3">
                    <div className="font-medium">{command.command}</div>
                    <div className="max-w-64 truncate text-xs text-muted-foreground">
                      {command.description || copy("无说明")}
                    </div>
                    {command.aliases.length > 0 && (
                      <div className="mt-1 text-xs text-muted-foreground">
                        {copy("别名列表", {
                          aliases: command.aliases.join(", "),
                        })}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-3">
                    {copy(SCOPE_LABELS[command.scope_type])}
                  </td>
                  <td className="px-3 py-3 font-mono text-xs">
                    {command.flow_id.slice(0, 8)}
                  </td>
                  <td className="px-3 py-3 text-xs text-muted-foreground">
                    {command.enabled ? copy("已启用") : copy("已停用")}
                    {command.input_required ? ` · ${copy("必须输入")}` : ""}
                    {command.require_mention ? ` · ${copy("群聊需@")}` : ""}
                  </td>
                  <td className="px-3 py-3 text-xs text-muted-foreground">
                    {command.last_used_at
                      ? new Date(command.last_used_at).toLocaleString()
                      : copy("尚未使用")}
                  </td>
                  <td className="px-3 py-3 text-right">
                    <div className="flex justify-end gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          setEditingCommand(command);
                          setDialogOpen(true);
                        }}
                      >
                        {copy("编辑")}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive"
                        onClick={() => setDeleteTarget(command)}
                      >
                        {copy("删除")}
                      </Button>
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
          {copy("共 {{count}} 条指令", { count: result?.total ?? 0 })}
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

      <CommandDialog
        open={dialogOpen}
        onOpenChange={(open) => {
          setDialogOpen(open);
          if (!open) setEditingCommand(null);
        }}
        connectionId={connectionId}
        command={editingCommand}
        loading={createCommand.isPending || updateCommand.isPending}
        onCreate={handleCreate}
        onUpdate={handleUpdate}
      />

      <DeleteConfirmationModal
        open={Boolean(deleteTarget)}
        setOpen={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        description={deleteTarget?.command ?? ""}
        onConfirm={handleDelete}
      />
    </div>
  );
}
