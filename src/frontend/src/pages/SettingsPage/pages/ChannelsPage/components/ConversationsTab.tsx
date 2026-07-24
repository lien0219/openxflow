import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import Loading from "@/components/ui/loading";
import {
  type ChannelConnection,
  type ChannelConversationBatchAction,
  type ChannelConversationBinding,
  type ChannelConversationBindingUpdate,
  type ChannelConversationRouteMode,
  type ChannelConversationStatus,
  type ChannelProviderCapabilities,
  useBatchUpdateChannelConversations,
  useGetChannelConversations,
  useUpdateChannelConversation,
} from "@/controllers/API/queries/channels";
import useAlertStore from "@/stores/alertStore";
import ChannelResourceSelect from "./ChannelResourceSelect";
import ConversationBindingDialog from "./ConversationBindingDialog";

interface ConversationsTabProps {
  connection: ChannelConnection;
  capabilities?: ChannelProviderCapabilities;
}

const STATUS_LABELS: Record<ChannelConversationStatus, string> = {
  pending: "待配置",
  inherited: "继承全局",
  overridden: "独立配置",
  ignored: "已忽略",
  disabled: "已停用",
  unavailable: "不可访问",
};

export default function ConversationsTab({
  connection,
  capabilities,
}: ConversationsTabProps) {
  const { t, i18n } = useTranslation();
  const setSuccessData = useAlertStore((state) => state.setSuccessData);
  const setErrorData = useAlertStore((state) => state.setErrorData);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [conversationType, setConversationType] = useState("");
  const [status, setStatus] = useState<ChannelConversationStatus | "">("");
  const [routeMode, setRouteMode] = useState<ChannelConversationRouteMode | "">(
    "",
  );
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [batchAction, setBatchAction] =
    useState<ChannelConversationBatchAction>("inherit");
  const [batchFlowId, setBatchFlowId] = useState("");
  const [editingConversation, setEditingConversation] =
    useState<ChannelConversationBinding | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setQuery(queryInput.trim());
      setPage(1);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [queryInput]);

  useEffect(() => {
    setPage(1);
    setSelectedIds([]);
    setEditingConversation(null);
  }, [connection.id]);

  const { data: result, isLoading } = useGetChannelConversations(
    {
      connectionId: connection.id,
      page,
      pageSize,
      query,
      conversationType,
      status,
      routeMode,
      sort: "-last_message_at",
    },
    { enabled: Boolean(connection.id) },
  );
  const updateConversation = useUpdateChannelConversation();
  const batchUpdate = useBatchUpdateChannelConversations();
  const conversations = result?.items ?? [];
  const pageIds = useMemo(
    () => conversations.map((conversation) => conversation.id),
    [conversations],
  );
  const allPageSelected =
    pageIds.length > 0 && pageIds.every((id) => selectedIds.includes(id));

  const showError = (title: string, error: unknown) =>
    setErrorData({
      title,
      list: [error instanceof Error ? error.message : String(error)],
    });

  const handleConversationSubmit = async (
    payload: ChannelConversationBindingUpdate,
  ) => {
    if (!editingConversation) return;
    try {
      await updateConversation.mutateAsync({
        connectionId: connection.id,
        bindingId: editingConversation.id,
        payload,
      });
      setEditingConversation(null);
      setSuccessData({ title: t("channels.toast.conversationSaved") });
    } catch (error) {
      showError(t("channels.toast.conversationSaveFailed"), error);
      throw error;
    }
  };

  const handleBatchAction = async () => {
    if (selectedIds.length === 0) return;
    if (batchAction === "override" && !batchFlowId) {
      setErrorData({
        title: "请选择批量覆盖工作流",
        list: ["批量设置独立工作流前必须选择目标工作流。"],
      });
      return;
    }
    try {
      const response = await batchUpdate.mutateAsync({
        connectionId: connection.id,
        payload: {
          conversation_ids: selectedIds,
          action: batchAction,
          default_flow_id: batchAction === "override" ? batchFlowId : null,
        },
      });
      setSelectedIds([]);
      setSuccessData({ title: `已更新 ${response.updated} 个会话` });
    } catch (error) {
      showError("批量更新会话失败", error);
    }
  };

  const togglePage = () => {
    if (allPageSelected) {
      setSelectedIds((current) =>
        current.filter((id) => !pageIds.includes(id)),
      );
    } else {
      setSelectedIds((current) =>
        Array.from(new Set([...current, ...pageIds])),
      );
    }
  };

  return (
    <div className="flex flex-col gap-4 rounded-xl border p-5">
      <div>
        <h3 className="font-semibold">会话管理</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          会话由渠道消息自动发现，平台会话 ID 和类型只读，不再手工新增。
        </p>
      </div>

      <div className="grid gap-3 lg:grid-cols-4">
        <Input
          value={queryInput}
          onChange={(event) => setQueryInput(event.target.value)}
          placeholder="搜索会话名称或平台会话 ID"
        />
        <select
          className="primary-input h-10"
          value={conversationType}
          onChange={(event) => {
            setConversationType(event.target.value);
            setPage(1);
          }}
        >
          <option value="">全部会话类型</option>
          {(capabilities?.conversation_types ?? []).map((type) => (
            <option key={type} value={type}>
              {conversationTypeLabel(type, t)}
            </option>
          ))}
        </select>
        <select
          className="primary-input h-10"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value as ChannelConversationStatus | "");
            setPage(1);
          }}
        >
          <option value="">全部状态</option>
          {Object.entries(STATUS_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <select
          className="primary-input h-10"
          value={routeMode}
          onChange={(event) => {
            setRouteMode(
              event.target.value as ChannelConversationRouteMode | "",
            );
            setPage(1);
          }}
        >
          <option value="">全部路由方式</option>
          <option value="inherit">继承全局</option>
          <option value="override">独立配置</option>
          <option value="disabled">禁用普通消息</option>
        </select>
      </div>

      {selectedIds.length > 0 && (
        <div className="flex flex-col gap-3 rounded-lg border bg-muted/30 p-4">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-sm font-medium">
              已选择 {selectedIds.length} 个会话
            </span>
            <select
              className="primary-input h-9 min-w-44"
              value={batchAction}
              onChange={(event) =>
                setBatchAction(
                  event.target.value as ChannelConversationBatchAction,
                )
              }
            >
              <option value="inherit">改为继承全局</option>
              <option value="override">设置独立工作流</option>
              <option value="ignore">忽略会话</option>
              <option value="restore">恢复会话</option>
              <option value="disable">停用会话</option>
              <option value="enable">启用并继承全局</option>
            </select>
            <Button
              size="sm"
              variant="primary"
              onClick={handleBatchAction}
              loading={batchUpdate.isPending}
            >
              应用
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setSelectedIds([])}
            >
              取消选择
            </Button>
          </div>
          {batchAction === "override" && (
            <ChannelResourceSelect
              kind="flow"
              label="批量覆盖工作流"
              emptyLabel="请选择目标工作流"
              value={batchFlowId}
              onChange={setBatchFlowId}
              required
            />
          )}
        </div>
      )}

      {isLoading ? (
        <Loading />
      ) : conversations.length === 0 ? (
        <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
          暂无匹配会话。用户或群聊第一次给机器人发消息后会自动出现在这里。
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead className="border-b text-xs text-muted-foreground">
              <tr>
                <th className="w-10 px-3 py-2">
                  <input
                    type="checkbox"
                    checked={allPageSelected}
                    onChange={togglePage}
                    aria-label="选择当前页全部会话"
                  />
                </th>
                <th className="px-3 py-2">会话</th>
                <th className="px-3 py-2">类型</th>
                <th className="px-3 py-2">状态</th>
                <th className="px-3 py-2">路由</th>
                <th className="px-3 py-2">最近活跃</th>
                <th className="px-3 py-2 text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {conversations.map((conversation) => (
                <tr key={conversation.id} className="border-b last:border-0">
                  <td className="px-3 py-3">
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(conversation.id)}
                      onChange={(event) =>
                        setSelectedIds((current) =>
                          event.target.checked
                            ? Array.from(new Set([...current, conversation.id]))
                            : current.filter((id) => id !== conversation.id),
                        )
                      }
                      aria-label={`选择 ${conversation.display_name || conversation.external_conversation_id}`}
                    />
                  </td>
                  <td className="px-3 py-3">
                    <div className="font-medium">
                      {conversation.display_name ||
                        conversation.external_conversation_id}
                    </div>
                    <div className="max-w-72 truncate text-xs text-muted-foreground">
                      {conversation.external_conversation_id}
                    </div>
                    {conversation.source === "legacy_manual" && (
                      <span className="mt-1 inline-flex rounded-full border border-border bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
                        {t("channels.conversations.legacyManual")}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-3">
                    {conversationTypeLabel(conversation.conversation_type, t)}
                  </td>
                  <td className="px-3 py-3">
                    <span className="rounded-full bg-muted px-2 py-1 text-xs">
                      {STATUS_LABELS[conversation.status]}
                    </span>
                  </td>
                  <td className="px-3 py-3 text-xs text-muted-foreground">
                    {routeLabel(conversation, connection)}
                  </td>
                  <td className="px-3 py-3 text-xs text-muted-foreground">
                    {new Date(conversation.last_message_at).toLocaleString(
                      i18n.language,
                    )}
                  </td>
                  <td className="px-3 py-3 text-right">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setEditingConversation(conversation)}
                    >
                      {t("channels.actions.edit")}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4 text-sm">
        <div className="text-muted-foreground">
          共 {result?.total ?? 0} 个会话
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
            <option value={20}>20 条</option>
            <option value={50}>50 条</option>
            <option value={100}>100 条</option>
          </select>
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((current) => Math.max(1, current - 1))}
          >
            上一页
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
            下一页
          </Button>
        </div>
      </div>

      <ConversationBindingDialog
        open={Boolean(editingConversation)}
        onOpenChange={(open) => {
          if (!open) setEditingConversation(null);
        }}
        binding={editingConversation}
        supportsMentions={capabilities?.supports_mentions}
        supportsFileUpload={capabilities?.supports_file_upload}
        loading={updateConversation.isPending}
        onSubmit={handleConversationSubmit}
      />
    </div>
  );
}

function conversationTypeLabel(
  conversationType: string,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  const keyByType: Record<string, string> = {
    private: "channels.conversationDialog.private",
    group: "channels.conversationDialog.group",
    supergroup: "channels.conversationDialog.supergroup",
    channel: "channels.conversationDialog.channel",
  };
  return keyByType[conversationType]
    ? t(keyByType[conversationType])
    : conversationType;
}

function routeLabel(
  conversation: ChannelConversationBinding,
  connection: ChannelConnection,
): string {
  if (conversation.route_mode === "disabled") return "普通消息已停用";
  if (conversation.route_mode === "override") {
    return conversation.default_flow_id
      ? `独立工作流 · ${conversation.default_flow_id.slice(0, 8)}`
      : "独立工作流未设置";
  }
  return connection.default_flow_id
    ? `继承全局 · ${connection.default_flow_id.slice(0, 8)}`
    : "继承全局但未设置";
}
