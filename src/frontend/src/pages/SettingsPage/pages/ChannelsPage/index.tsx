import { useEffect, useMemo, useState } from "react";
import ForwardedIconComponent from "@/components/common/genericIconComponent";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import Loading from "@/components/ui/loading";
import {
  type ChannelConnection,
  type ChannelConnectionCreate,
  type ChannelConnectionUpdate,
  type ChannelConversationBinding,
  useConfigureTelegramWebhook,
  useCreateChannelConnection,
  useDeleteChannelConnection,
  useDeleteChannelIdentity,
  useGetChannelConnections,
  useGetChannelConversations,
  useGetChannelIdentities,
  useRedeemChannelBindingCode,
  useTestChannelConnection,
  useUpdateChannelConnection,
  useUpsertChannelConversation,
} from "@/controllers/API/queries/channels";
import { useGetKnowledgeBases } from "@/controllers/API/queries/knowledge-bases/use-get-knowledge-bases";
import { useGetRefreshFlowsQuery } from "@/controllers/API/queries/flows/use-get-refresh-flows-query";
import DeleteConfirmationModal from "@/modals/deleteConfirmationModal";
import useAlertStore from "@/stores/alertStore";
import ChannelConnectionDialog from "./components/ChannelConnectionDialog";
import ConversationBindingDialog from "./components/ConversationBindingDialog";
import { getApiErrorMessage, getChannelStatusMeta, readConnectionSetting } from "./utils";

type DeleteTarget =
  | { kind: "connection"; id: string; name: string }
  | { kind: "identity"; id: string; name: string }
  | null;

const PROVIDERS = [
  { id: "telegram", name: "Telegram", enabled: true, icon: "Send" },
  { id: "feishu", name: "飞书", enabled: false, icon: "MessagesSquare" },
  { id: "dingtalk", name: "钉钉", enabled: false, icon: "MessageCircle" },
  { id: "wecom", name: "企业微信", enabled: false, icon: "Building2" },
] as const;

export default function ChannelsPage() {
  const setSuccessData = useAlertStore((state) => state.setSuccessData);
  const setErrorData = useAlertStore((state) => state.setErrorData);
  const [selectedConnectionId, setSelectedConnectionId] = useState("");
  const [connectionDialogOpen, setConnectionDialogOpen] = useState(false);
  const [editingConnection, setEditingConnection] =
    useState<ChannelConnection | null>(null);
  const [conversationDialogOpen, setConversationDialogOpen] = useState(false);
  const [editingConversation, setEditingConversation] =
    useState<ChannelConversationBinding | null>(null);
  const [bindingCode, setBindingCode] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget>(null);

  const {
    data: connections = [],
    isLoading: connectionsLoading,
  } = useGetChannelConnections();
  const selectedConnection = useMemo(
    () =>
      connections.find((connection) => connection.id === selectedConnectionId) ??
      null,
    [connections, selectedConnectionId],
  );

  useEffect(() => {
    if (connections.length === 0) {
      setSelectedConnectionId("");
      return;
    }
    if (!connections.some((item) => item.id === selectedConnectionId)) {
      setSelectedConnectionId(connections[0].id);
    }
  }, [connections, selectedConnectionId]);

  const { data: identities = [], isLoading: identitiesLoading } =
    useGetChannelIdentities(
      { connectionId: selectedConnectionId },
      { enabled: Boolean(selectedConnectionId) },
    );
  const { data: conversations = [], isLoading: conversationsLoading } =
    useGetChannelConversations(
      { connectionId: selectedConnectionId },
      { enabled: Boolean(selectedConnectionId) },
    );
  const { data: flowData } = useGetRefreshFlowsQuery(
    { get_all: true, header_flows: true, remove_example_flows: true },
    { refetchOnWindowFocus: false },
  );
  const { data: knowledgeBases = [] } = useGetKnowledgeBases({
    refetchOnWindowFocus: false,
  });
  const flows = Array.isArray(flowData) ? flowData : (flowData?.items ?? []);

  const createConnection = useCreateChannelConnection();
  const updateConnection = useUpdateChannelConnection();
  const deleteConnection = useDeleteChannelConnection();
  const testConnection = useTestChannelConnection();
  const configureWebhook = useConfigureTelegramWebhook();
  const redeemBinding = useRedeemChannelBindingCode();
  const deleteIdentity = useDeleteChannelIdentity();
  const upsertConversation = useUpsertChannelConversation();

  const showError = (title: string, error: unknown) =>
    setErrorData({ title, list: [getApiErrorMessage(error)] });

  const handleConnectionSubmit = async ({
    payload,
    publicBaseUrl,
  }: {
    payload: ChannelConnectionCreate | ChannelConnectionUpdate;
    publicBaseUrl: string;
  }) => {
    try {
      const connection = editingConnection
        ? await updateConnection.mutateAsync({
            connectionId: editingConnection.id,
            payload: payload as ChannelConnectionUpdate,
          })
        : await createConnection.mutateAsync(payload as ChannelConnectionCreate);

      if (publicBaseUrl) {
        await configureWebhook.mutateAsync({
          connectionId: connection.id,
          payload: {
            public_base_url: publicBaseUrl,
            drop_pending_updates: false,
          },
        });
      }
      setSelectedConnectionId(connection.id);
      setConnectionDialogOpen(false);
      setEditingConnection(null);
      setSuccessData({
        title: publicBaseUrl ? "Telegram 连接与 Webhook 已配置" : "Telegram 连接已保存",
      });
    } catch (error) {
      showError("保存渠道连接失败", error);
      throw error;
    }
  };

  const handleTestConnection = async (connection: ChannelConnection) => {
    try {
      const result = await testConnection.mutateAsync({
        connectionId: connection.id,
      });
      setSuccessData({
        title: `连接成功：@${result.username ?? result.display_name ?? connection.name}`,
      });
    } catch (error) {
      showError("渠道连接测试失败", error);
    }
  };

  const handleConfigureWebhook = async (connection: ChannelConnection) => {
    const publicBaseUrl = readConnectionSetting(connection, "public_base_url", "");
    if (!publicBaseUrl) {
      setEditingConnection(connection);
      setConnectionDialogOpen(true);
      setErrorData({
        title: "请先填写 OpenXFlow 公开地址",
        list: ["编辑连接后保存，系统会自动配置 Telegram Webhook。"],
      });
      return;
    }
    try {
      const result = await configureWebhook.mutateAsync({
        connectionId: connection.id,
        payload: {
          public_base_url: publicBaseUrl,
          drop_pending_updates: false,
        },
      });
      setSuccessData({ title: `Webhook 已配置：${result.webhook_url}` });
    } catch (error) {
      showError("Webhook 配置失败", error);
    }
  };

  const handleRedeemBinding = async () => {
    if (!bindingCode.trim()) return;
    try {
      await redeemBinding.mutateAsync({ code: bindingCode.trim() });
      setBindingCode("");
      setSuccessData({ title: "渠道账号绑定成功" });
    } catch (error) {
      showError("绑定码兑换失败", error);
    }
  };

  const handleConversationSubmit = async (
    payload: Parameters<typeof upsertConversation.mutateAsync>[0]["payload"],
  ) => {
    if (!selectedConnection) return;
    try {
      await upsertConversation.mutateAsync({
        connectionId: selectedConnection.id,
        payload,
      });
      setConversationDialogOpen(false);
      setEditingConversation(null);
      setSuccessData({ title: "会话绑定已保存" });
    } catch (error) {
      showError("保存会话绑定失败", error);
      throw error;
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget || !selectedConnection) return;
    try {
      if (deleteTarget.kind === "connection") {
        await deleteConnection.mutateAsync({ connectionId: deleteTarget.id });
        setSuccessData({ title: "渠道连接已删除" });
      } else {
        await deleteIdentity.mutateAsync({
          connectionId: selectedConnection.id,
          identityId: deleteTarget.id,
        });
        setSuccessData({ title: "渠道账号已解除绑定" });
      }
    } catch (error) {
      showError("删除失败", error);
    } finally {
      setDeleteTarget(null);
    }
  };

  if (connectionsLoading) {
    return (
      <div className="flex h-full w-full items-center justify-center">
        <Loading />
      </div>
    );
  }

  return (
    <div className="flex h-full w-full flex-col gap-6 overflow-y-auto pb-8 pr-1">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
            渠道中心
            <ForwardedIconComponent name="RadioTower" className="h-5 w-5 text-primary" />
          </h2>
          <p className="max-w-3xl text-sm text-muted-foreground">
            让用户在 Telegram、飞书、钉钉和企业微信手机端运行工作流、查询知识库并上传文件。当前阶段已开放 Telegram 全链路配置。
          </p>
        </div>
        <Button
          variant="primary"
          onClick={() => {
            setEditingConnection(null);
            setConnectionDialogOpen(true);
          }}
        >
          <ForwardedIconComponent name="Plus" className="h-4 w-4" />
          新增连接
        </Button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {PROVIDERS.map((provider) => (
          <div key={provider.id} className="flex items-center justify-between rounded-xl border p-4">
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-muted p-2">
                <ForwardedIconComponent name={provider.icon} className="h-5 w-5" />
              </div>
              <div>
                <div className="text-sm font-medium">{provider.name}</div>
                <div className="text-xs text-muted-foreground">
                  {provider.enabled ? "已开放" : "后续阶段接入"}
                </div>
              </div>
            </div>
            <span className={`h-2.5 w-2.5 rounded-full ${provider.enabled ? "bg-accent-emerald-foreground" : "bg-muted-foreground/30"}`} />
          </div>
        ))}
      </div>

      <div className="grid min-h-0 gap-6 xl:grid-cols-[minmax(280px,0.8fr)_minmax(0,1.8fr)]">
        <section className="flex flex-col gap-3">
          <div className="text-sm font-medium text-muted-foreground">渠道连接</div>
          {connections.length === 0 ? (
            <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
              尚未创建渠道连接。先创建 Telegram Bot 连接并配置 Webhook。
            </div>
          ) : (
            connections.map((connection) => {
              const status = getChannelStatusMeta(connection.status);
              const selected = selectedConnectionId === connection.id;
              return (
                <button
                  type="button"
                  key={connection.id}
                  onClick={() => setSelectedConnectionId(connection.id)}
                  className={`rounded-xl border p-4 text-left transition-colors ${selected ? "border-primary bg-accent" : "hover:bg-accent/60"}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-medium">{connection.name}</div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {connection.channel_type} · {connection.connection_mode}
                      </div>
                    </div>
                    <span className={`rounded-full px-2 py-1 text-xs ${status.className}`}>
                      {status.label}
                    </span>
                  </div>
                  {connection.last_error && (
                    <div className="mt-3 line-clamp-2 text-xs text-destructive">
                      {connection.last_error}
                    </div>
                  )}
                </button>
              );
            })
          )}
        </section>

        <section className="flex min-w-0 flex-col gap-5">
          {!selectedConnection ? (
            <div className="flex min-h-64 items-center justify-center rounded-xl border border-dashed text-sm text-muted-foreground">
              选择一个连接查看配置详情。
            </div>
          ) : (
            <>
              <div className="rounded-xl border p-5">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <h3 className="text-base font-semibold">{selectedConnection.name}</h3>
                    <p className="mt-1 text-sm text-muted-foreground">
                      已配置凭证：{selectedConnection.configured_credential_keys.join(", ") || "无"}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      最近连接：{selectedConnection.last_connected_at ? new Date(selectedConnection.last_connected_at).toLocaleString() : "尚未测试"}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button variant="outline" size="sm" onClick={() => handleTestConnection(selectedConnection)} loading={testConnection.isPending}>
                      测试连接
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => handleConfigureWebhook(selectedConnection)} loading={configureWebhook.isPending}>
                      配置 Webhook
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setEditingConnection(selectedConnection);
                        setConnectionDialogOpen(true);
                      }}
                    >
                      编辑
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-destructive"
                      onClick={() =>
                        setDeleteTarget({
                          kind: "connection",
                          id: selectedConnection.id,
                          name: selectedConnection.name,
                        })
                      }
                    >
                      删除
                    </Button>
                  </div>
                </div>
              </div>

              <div className="rounded-xl border p-5">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <h3 className="font-semibold">绑定手机账号</h3>
                    <p className="mt-1 text-sm text-muted-foreground">
                      用户私聊机器人发送 /bind 后，将收到 8 位绑定码；在此输入即可绑定当前登录账号。
                    </p>
                  </div>
                  <div className="flex w-full gap-2 sm:w-auto">
                    <Input
                      value={bindingCode}
                      onChange={(event) => setBindingCode(event.target.value.toUpperCase())}
                      placeholder="输入绑定码"
                      maxLength={12}
                      className="sm:w-48"
                    />
                    <Button onClick={handleRedeemBinding} loading={redeemBinding.isPending} disabled={!bindingCode.trim()}>
                      绑定
                    </Button>
                  </div>
                </div>

                <div className="mt-5 flex flex-col gap-2">
                  {identitiesLoading ? (
                    <Loading />
                  ) : identities.length === 0 ? (
                    <div className="text-sm text-muted-foreground">还没有账号绑定记录。</div>
                  ) : (
                    identities.map((identity) => (
                      <div key={identity.id} className="flex items-center justify-between rounded-lg bg-muted/50 px-3 py-2">
                        <div className="min-w-0">
                          <div className="truncate text-sm font-medium">
                            {identity.display_name || identity.external_user_id}
                          </div>
                          <div className="truncate text-xs text-muted-foreground">
                            Telegram ID：{identity.external_user_id} · OpenXFlow：{identity.openxflow_user_id}
                          </div>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-destructive"
                          onClick={() =>
                            setDeleteTarget({
                              kind: "identity",
                              id: identity.id,
                              name: identity.display_name || identity.external_user_id,
                            })
                          }
                        >
                          解绑
                        </Button>
                      </div>
                    ))
                  )}
                </div>
              </div>

              <div className="rounded-xl border p-5">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h3 className="font-semibold">会话与工作流</h3>
                    <p className="mt-1 text-sm text-muted-foreground">
                      为私聊或群聊配置默认工作流、知识库以及文件上传权限。
                    </p>
                  </div>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => {
                      setEditingConversation(null);
                      setConversationDialogOpen(true);
                    }}
                  >
                    <ForwardedIconComponent name="Plus" className="h-4 w-4" />
                    新增绑定
                  </Button>
                </div>

                <div className="mt-5 flex flex-col gap-2">
                  {conversationsLoading ? (
                    <Loading />
                  ) : conversations.length === 0 ? (
                    <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
                      机器人收到已绑定用户的消息或文件后，也会自动创建基础会话记录。
                    </div>
                  ) : (
                    conversations.map((conversation) => {
                      const flow = flows.find((item) => item.id === conversation.default_flow_id);
                      const kb = knowledgeBases.find((item) => item.id === conversation.knowledge_base_id);
                      return (
                        <div key={conversation.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-muted/50 px-3 py-3">
                          <div className="min-w-0">
                            <div className="text-sm font-medium">
                              {conversation.display_name || conversation.external_conversation_id}
                            </div>
                            <div className="mt-1 text-xs text-muted-foreground">
                              {conversation.conversation_type} · Chat ID：{conversation.external_conversation_id}
                            </div>
                            <div className="mt-1 text-xs text-muted-foreground">
                              工作流：{flow?.name ?? "未绑定"} · 知识库：{kb?.name ?? "未绑定"} · 文件上传：{conversation.allow_file_upload ? "允许" : "关闭"}
                            </div>
                          </div>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              setEditingConversation(conversation);
                              setConversationDialogOpen(true);
                            }}
                          >
                            编辑
                          </Button>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            </>
          )}
        </section>
      </div>

      <ChannelConnectionDialog
        open={connectionDialogOpen}
        onOpenChange={(open) => {
          setConnectionDialogOpen(open);
          if (!open) setEditingConnection(null);
        }}
        connection={editingConnection}
        loading={createConnection.isPending || updateConnection.isPending || configureWebhook.isPending}
        onSubmit={handleConnectionSubmit}
      />

      <ConversationBindingDialog
        open={conversationDialogOpen}
        onOpenChange={(open) => {
          setConversationDialogOpen(open);
          if (!open) setEditingConversation(null);
        }}
        binding={editingConversation}
        flows={flows}
        knowledgeBases={knowledgeBases}
        loading={upsertConversation.isPending}
        onSubmit={handleConversationSubmit}
      />

      <DeleteConfirmationModal
        open={Boolean(deleteTarget)}
        setOpen={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        description={deleteTarget?.name ?? "渠道配置"}
        onConfirm={handleDelete}
      />
    </div>
  );
}
