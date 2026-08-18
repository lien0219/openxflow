import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import Loading from "@/components/ui/loading";
import {
  type ChannelActiveWorkflowSelection,
  useCleanupChannelFlowSelections,
  useDeleteChannelFlowSelection,
  useGetChannelFlowSelections,
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
  const [search, setSearch] = useState("");
  const [deleteTarget, setDeleteTarget] =
    useState<ChannelActiveWorkflowSelection | null>(null);

  useEffect(() => {
    setPage(1);
    setSearch("");
    setDeleteTarget(null);
  }, [connectionId]);

  const {
    data: selectionResult,
    isLoading,
    isFetching,
    isError,
    refetch,
  } = useGetChannelFlowSelections(
    { connectionId, page, pageSize, query: search.trim() },
    { enabled: Boolean(connectionId), retry: 1 },
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

      <Input
        value={search}
        placeholder={copy("搜索成员、会话、指令或工作流")}
        onChange={(event) => {
          setSearch(event.target.value);
          setPage(1);
        }}
      />

      {isLoading ? (
        <div className="flex min-h-32 items-center justify-center">
          <Loading />
        </div>
      ) : isError ? (
        <div className="flex min-h-32 flex-col items-center justify-center gap-3 rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
          <span>{copy("活动工作流选择加载失败")}</span>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => refetch()}
          >
            {copy("重新加载")}
          </Button>
        </div>
      ) : (selectionResult?.items.length ?? 0) === 0 ? (
        <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
          {copy("当前没有匹配的活动工作流选择。")}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1080px] text-left text-sm">
            <thead className="border-b text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2">{copy("成员")}</th>
                <th className="px-3 py-2">{copy("会话 / 线程")}</th>
                <th className="px-3 py-2">{copy("当前工作流")}</th>
                <th className="px-3 py-2">{copy("执行身份")}</th>
                <th className="px-3 py-2">{copy("选择时间")}</th>
                <th className="px-3 py-2">{copy("最近使用")}</th>
                <th className="px-3 py-2">{copy("有效期至")}</th>
                <th className="px-3 py-2 text-right">{copy("操作")}</th>
              </tr>
            </thead>
            <tbody>
              {(selectionResult?.items ?? []).map((selection) => (
                <tr key={selection.id} className="border-b last:border-0">
                  <td className="px-3 py-3">
                    <div className="font-medium">
                      {selection.identity_display_name ||
                        selection.external_user_id ||
                        selection.channel_identity_id.slice(0, 8)}
                    </div>
                    <div className="mt-1 font-mono text-xs text-muted-foreground">
                      {selection.external_user_id ||
                        selection.channel_identity_id.slice(0, 8)}
                    </div>
                  </td>
                  <td className="px-3 py-3">
                    <div>
                      {selection.conversation_display_name ||
                        selection.external_conversation_id ||
                        selection.conversation_binding_id.slice(0, 8)}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {selection.conversation_type || copy("未知会话")}
                      {selection.conversation_scope_id
                        ? ` · ${copy("线程：{{value}}", {
                            value: selection.conversation_scope_id,
                          })}`
                        : ""}
                    </div>
                  </td>
                  <td className="px-3 py-3">
                    <div className="font-medium">
                      {selection.flow_name ||
                        selection.command ||
                        copy("工作流已删除")}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {selection.command || "-"}
                      {selection.flow_endpoint_name
                        ? ` · ${selection.flow_endpoint_name}`
                        : ""}
                    </div>
                  </td>
                  <td className="px-3 py-3 text-xs text-muted-foreground">
                    {selection.execution_identity_type === "bound_user"
                      ? copy("绑定用户")
                      : copy("渠道共享身份")}
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
              ))}
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
