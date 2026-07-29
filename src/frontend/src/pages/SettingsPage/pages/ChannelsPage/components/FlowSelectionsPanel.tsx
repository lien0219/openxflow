import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import Loading from "@/components/ui/loading";
import {
  type ChannelActiveWorkflowSelection,
  useCleanupChannelFlowSelections,
  useDeleteChannelFlowSelection,
  useGetChannelCommands,
  useGetChannelConversations,
  useGetChannelFlowSelections,
  useGetChannelIdentitiesPage,
} from "@/controllers/API/queries/channels";
import DeleteConfirmationModal from "@/modals/deleteConfirmationModal";
import useAlertStore from "@/stores/alertStore";
import useChannelCopy from "../use-channel-copy";

interface FlowSelectionsPanelProps {
  connectionId: string;
}

function formatDate(value: string | null): string {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

export default function FlowSelectionsPanel({
  connectionId,
}: FlowSelectionsPanelProps) {
  const copy = useChannelCopy();
  const setSuccessData = useAlertStore((state) => state.setSuccessData);
  const setErrorData = useAlertStore((state) => state.setErrorData);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [deleteTarget, setDeleteTarget] =
    useState<ChannelActiveWorkflowSelection | null>(null);

  useEffect(() => {
    setPage(1);
    setDeleteTarget(null);
  }, [connectionId]);

  const {
    data: selectionResult,
    isLoading,
    isFetching,
    isError,
    refetch,
  } = useGetChannelFlowSelections(
    { connectionId, page, pageSize },
    { enabled: Boolean(connectionId), retry: 1 },
  );
  const { data: commandResult } = useGetChannelCommands(
    { connectionId, page: 1, pageSize: 100 },
    { enabled: Boolean(connectionId) },
  );
  const { data: conversationResult } = useGetChannelConversations(
    {
      connectionId,
      page: 1,
      pageSize: 100,
      sort: "-last_message_at",
    },
    { enabled: Boolean(connectionId) },
  );
  const { data: identityResult } = useGetChannelIdentitiesPage(
    { connectionId, page: 1, pageSize: 100 },
    { enabled: Boolean(connectionId) },
  );

  const commandById = useMemo(
    () =>
      new Map(
        (commandResult?.items ?? []).map((command) => [command.id, command]),
      ),
    [commandResult?.items],
  );
  const conversationById = useMemo(
    () =>
      new Map(
        (conversationResult?.items ?? []).map((conversation) => [
          conversation.id,
          conversation,
        ]),
      ),
    [conversationResult?.items],
  );
  const identityById = useMemo(
    () =>
      new Map(
        (identityResult?.items ?? []).map((identity) => [identity.id, identity]),
      ),
    [identityResult?.items],
  );

  const deleteSelection = useDeleteChannelFlowSelection();
  const cleanupSelections = useCleanupChannelFlowSelections();

  const showError = (title: string, error: unknown) =>
    setErrorData({
      title,
      list: [error instanceof Error ? error.message : String(error)],
    });

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteSelection.mutateAsync({
        connectionId,
        selectionId: deleteTarget.id,
      });
      setDeleteTarget(null);
      setSuccessData({ title: copy("当前工作流选择已撤销") });
    } catch (error) {
      showError(copy("撤销工作流选择失败"), error);
    }
  };

  const handleCleanup = async () => {
    try {
      const result = await cleanupSelections.mutateAsync({ connectionId });
      setPage(1);
      setSuccessData({
        title: copy("已清理 {{count}} 条过期选择", {
          count: result.removed,
        }),
      });
    } catch (error) {
      showError(copy("清理过期选择失败"), error);
    }
  };

  return (
    <section className="flex flex-col gap-4 border-t pt-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h4 className="font-semibold">{copy("活动工作流选择")}</h4>
          <p className="mt-1 text-sm text-muted-foreground">
            {copy(
              "查看成员在私聊、群聊和线程中持续使用的工作流，并按需撤销或清理过期状态。",
            )}
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={isFetching}
            onClick={() => refetch()}
          >
            {copy("刷新")}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            loading={cleanupSelections.isPending}
            onClick={handleCleanup}
          >
            {copy("清理过期选择")}
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="flex min-h-32 items-center justify-center">
          <Loading />
        </div>
      ) : isError ? (
        <div className="flex min-h-32 flex-col items-center justify-center gap-3 rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
          <span>{copy("活动工作流选择加载失败")}</span>
          <Button type="button" size="sm" variant="outline" onClick={() => refetch()}>
            {copy("重新加载")}
          </Button>
        </div>
      ) : (selectionResult?.items.length ?? 0) === 0 ? (
        <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
          {copy("当前没有用户设置持续工作流。")}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[980px] text-left text-sm">
            <thead className="border-b text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2">{copy("成员")}</th>
                <th className="px-3 py-2">{copy("会话 / 线程")}</th>
                <th className="px-3 py-2">{copy("当前工作流")}</th>
                <th className="px-3 py-2">{copy("选择时间")}</th>
                <th className="px-3 py-2">{copy("最近使用")}</th>
                <th className="px-3 py-2">{copy("有效期至")}</th>
                <th className="px-3 py-2 text-right">{copy("操作")}</th>
              </tr>
            </thead>
            <tbody>
              {(selectionResult?.items ?? []).map((selection) => {
                const identity = identityById.get(selection.channel_identity_id);
                const conversation = conversationById.get(
                  selection.conversation_binding_id,
                );
                const command = commandById.get(selection.workflow_command_id);
                return (
                  <tr key={selection.id} className="border-b last:border-0">
                    <td className="px-3 py-3">
                      <div className="font-medium">
                        {identity?.display_name ||
                          identity?.external_user_id ||
                          selection.channel_identity_id.slice(0, 8)}
                      </div>
                      <div className="mt-1 font-mono text-xs text-muted-foreground">
                        {identity?.external_user_id ||
                          selection.channel_identity_id.slice(0, 8)}
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      <div>
                        {conversation?.display_name ||
                          conversation?.external_conversation_id ||
                          selection.conversation_binding_id.slice(0, 8)}
                      </div>
                      <div className="mt-1 font-mono text-xs text-muted-foreground">
                        {selection.conversation_scope_id
                          ? copy("线程：{{value}}", {
                              value: selection.conversation_scope_id,
                            })
                          : copy("主会话")}
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      <div className="font-medium">
                        {command?.command || copy("指令已删除")}
                      </div>
                      <div className="mt-1 font-mono text-xs text-muted-foreground">
                        {command?.flow_id.slice(0, 8) ||
                          selection.workflow_command_id.slice(0, 8)}
                      </div>
                    </td>
                    <td className="whitespace-nowrap px-3 py-3 text-xs text-muted-foreground">
                      {formatDate(selection.selected_at)}
                    </td>
                    <td className="whitespace-nowrap px-3 py-3 text-xs text-muted-foreground">
                      {formatDate(selection.last_used_at)}
                    </td>
                    <td className="whitespace-nowrap px-3 py-3 text-xs text-muted-foreground">
                      {selection.expires_at
                        ? formatDate(selection.expires_at)
                        : copy("永久")}
                    </td>
                    <td className="px-3 py-3 text-right">
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="text-destructive"
                        onClick={() => setDeleteTarget(selection)}
                      >
                        {copy("撤销")}
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
        <div className="text-muted-foreground">
          {copy("共 {{count}} 条活动选择", {
            count: selectionResult?.total ?? 0,
          })}
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
            type="button"
            size="sm"
            variant="outline"
            disabled={page <= 1}
            onClick={() => setPage((current) => Math.max(1, current - 1))}
          >
            {copy("上一页")}
          </Button>
          <span>
            {page} / {Math.max(1, selectionResult?.total_pages ?? 0)}
          </span>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={page >= (selectionResult?.total_pages ?? 0)}
            onClick={() => setPage((current) => current + 1)}
          >
            {copy("下一页")}
          </Button>
        </div>
      </div>

      <DeleteConfirmationModal
        open={Boolean(deleteTarget)}
        setOpen={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        description={copy("撤销该成员在当前会话中的持续工作流选择")}
        onConfirm={handleDelete}
      />
    </section>
  );
}
