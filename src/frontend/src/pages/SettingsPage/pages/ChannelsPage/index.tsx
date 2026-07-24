import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import ForwardedIconComponent from "@/components/common/genericIconComponent";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import Loading from "@/components/ui/loading";
import { Switch } from "@/components/ui/switch";
import {
  type ChannelConnection,
  type ChannelConnectionCreate,
  type ChannelConnectionUpdate,
  type ChannelConversationBinding,
  type ChannelConversationBindingUpdate,
  type ChannelConversationRouteMode,
  type ChannelConversationStatus,
  type ChannelType,
  type ChannelUnconfiguredBehavior,
  useConfigureTelegramWebhook,
  useCreateChannelConnection,
  useDeleteChannelConnection,
  useDeleteChannelIdentity,
  useGetChannelConnections,
  useGetChannelConversations,
  useGetChannelIdentities,
  useGetChannelProviderCapabilities,
  useRedeemChannelBindingCode,
  useTestChannelConnection,
  useUpdateChannelConnection,
  useUpdateChannelConversation,
} from "@/controllers/API/queries/channels";
import { useGetRefreshFlowsQuery } from "@/controllers/API/queries/flows/use-get-refresh-flows-query";
import { useGetKnowledgeBases } from "@/controllers/API/queries/knowledge-bases/use-get-knowledge-bases";
import DeleteConfirmationModal from "@/modals/deleteConfirmationModal";
import useAlertStore from "@/stores/alertStore";
import ChannelConnectionDialog from "./components/ChannelConnectionDialog";
import ConversationBindingDialog from "./components/ConversationBindingDialog";
import {
  buildChannelWebhookUrl,
  getApiErrorMessage,
  getChannelStatusMeta,
  readConnectionSetting,
} from "./utils";

type SupportedChannelType = Extract<
  ChannelType,
  "telegram" | "feishu" | "dingtalk" | "wecom"
>;

type DetailTab =
  | "overview"
  | "routing"
  | "conversations"
  | "commands"
  | "accounts"
  | "logs";

type DeleteTarget =
  | { kind: "connection"; id: string; name: string }
  | { kind: "identity"; id: string; name: string }
  | null;

interface RoutingFormState {
  defaultFlowId: string;
  defaultKnowledgeBaseId: string;
  autoDiscoverConversations: boolean;
  unconfiguredBehavior: ChannelUnconfiguredBehavior;
  pendingNoticeEnabled: boolean;
  personalCommandsEnabled: boolean;
  defaultResponseMode: string;
  defaultAllowFileUpload: boolean;
}

const PROVIDERS: Array<{
  id: SupportedChannelType;
  nameKey: string;
  enabled: boolean;
  icon: string;
}> = [
  {
    id: "telegram",
    nameKey: "channels.provider.telegram",
    enabled: true,
    icon: "Send",
  },
  {
    id: "feishu",
    nameKey: "channels.provider.feishu",
    enabled: true,
    icon: "MessagesSquare",
  },
  {
    id: "dingtalk",
    nameKey: "channels.provider.dingtalk",
    enabled: true,
    icon: "MessageCircle",
  },
  {
    id: "wecom",
    nameKey: "channels.provider.wecom",
    enabled: true,
    icon: "Building2",
  },
];

const PROVIDER_KEYS: Record<SupportedChannelType, string> = {
  telegram: "channels.provider.telegram",
  feishu: "channels.provider.feishu",
  dingtalk: "channels.provider.dingtalk",
  wecom: "channels.provider.wecom",
};

const DEFAULT_ROUTING_FORM: RoutingFormState = {
  defaultFlowId: "",
  defaultKnowledgeBaseId: "",
  autoDiscoverConversations: true,
  unconfiguredBehavior: "notify_pending",
  pendingNoticeEnabled: true,
  personalCommandsEnabled: true,
  defaultResponseMode: "mentions_only",
  defaultAllowFileUpload: true,
};

export default function ChannelsPage() {
  const { t, i18n } = useTranslation();
  const setSuccessData = useAlertStore((state) => state.setSuccessData);
  const setErrorData = useAlertStore((state) => state.setErrorData);
  const [selectedConnectionId, setSelectedConnectionId] = useState("");
  const [activeTab, setActiveTab] = useState<DetailTab>("overview");
  const [connectionDialogOpen, setConnectionDialogOpen] = useState(false);
  const [newChannelType, setNewChannelType] =
    useState<SupportedChannelType>("telegram");
  const [editingConnection, setEditingConnection] =
    useState<ChannelConnection | null>(null);
  const [conversationDialogOpen, setConversationDialogOpen] = useState(false);
  const [editingConversation, setEditingConversation] =
    useState<ChannelConversationBinding | null>(null);
  const [bindingCode, setBindingCode] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget>(null);
  const [routingForm, setRoutingForm] = useState<RoutingFormState>(
    DEFAULT_ROUTING_FORM,
  );
  const [conversationPage, setConversationPage] = useState(1);
  const [conversationPageSize, setConversationPageSize] = useState(20);
  const [conversationQueryInput, setConversationQueryInput] = useState("");
  const [conversationQuery, setConversationQuery] = useState("");
  const [conversationTypeFilter, setConversationTypeFilter] = useState("");
  const [conversationStatusFilter, setConversationStatusFilter] = useState<
    ChannelConversationStatus | ""
  >("");
  const [conversationRouteFilter, setConversationRouteFilter] = useState<
    ChannelConversationRouteMode | ""
  >("");

  const { data: connections = [], isLoading: connectionsLoading } =
    useGetChannelConnections();
  const { data: providerCapabilities } =
    useGetChannelProviderCapabilities({});
  const selectedConnection = useMemo(
    () =>
      connections.find(
        (connection) => connection.id === selectedConnectionId,
      ) ?? null,
    [connections, selectedConnectionId],
  );
  const selectedCapabilities = selectedConnection
    ? providerCapabilities?.[selectedConnection.channel_type]
    : undefined;

  useEffect(() => {
    if (connections.length === 0) {
      setSelectedConnectionId("");
      return;
    }
    if (!connections.some((item) => item.id === selectedConnectionId)) {
      setSelectedConnectionId(connections[0].id);
    }
  }, [connections, selectedConnectionId]);

  useEffect(() => {
    setConversationPage(1);
    setEditingConversation(null);
    setConversationDialogOpen(false);
  }, [selectedConnectionId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setConversationQuery(conversationQueryInput.trim());
      setConversationPage(1);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [conversationQueryInput]);

  useEffect(() => {
    if (!selectedConnection) {
      setRoutingForm(DEFAULT_ROUTING_FORM);
      return;
    }
    setRoutingForm({
      defaultFlowId: selectedConnection.default_flow_id ?? "",
      defaultKnowledgeBaseId:
        selectedConnection.default_knowledge_base_id ?? "",
      autoDiscoverConversations:
        selectedConnection.auto_discover_conversations,
      unconfiguredBehavior: selectedConnection.unconfigured_behavior,
      pendingNoticeEnabled: selectedConnection.pending_notice_enabled,
      personalCommandsEnabled: selectedConnection.personal_commands_enabled,
      defaultResponseMode: selectedConnection.default_response_mode,
      defaultAllowFileUpload:
        selectedConnection.default_allow_file_upload,
    });
  }, [selectedConnection]);

  const { data: identities = [], isLoading: identitiesLoading } =
    useGetChannelIdentities(
      { connectionId: selectedConnectionId },
      { enabled: Boolean(selectedConnectionId) },
    );
  const { data: conversationResult, isLoading: conversationsLoading } =
    useGetChannelConversations(
      {
        connectionId: selectedConnectionId,
        page: conversationPage,
        pageSize: conversationPageSize,
        query: conversationQuery,
        conversationType: conversationTypeFilter,
        status: conversationStatusFilter,
        routeMode: conversationRouteFilter,
        sort: "-last_message_at",
      },
      { enabled: Boolean(selectedConnectionId) },
    );
  const conversations = conversationResult?.items ?? [];

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
  const updateConversation = useUpdateChannelConversation();

  const showError = (title: string, error: unknown) =>
    setErrorData({
      title,
      list: [getApiErrorMessage(error, t("channels.error.requestFailed"))],
    });

  const getProviderName = (channelType: string) => {
    if (channelType in PROVIDER_KEYS) {
      return t(PROVIDER_KEYS[channelType as SupportedChannelType]);
    }
    return channelType;
  };

  const getConnectionModeLabel = (connection: ChannelConnection): string => {
    if (
      connection.channel_type === "dingtalk" &&
      connection.connection_mode === "stream"
    ) {
      return t("channels.mode.stream");
    }
    return connection.connection_mode === "webhook"
      ? "Webhook"
      : connection.connection_mode;
  };

  const getWebhookLabel = (connection: ChannelConnection): string => {
    if (connection.channel_type === "feishu") {
      return t("channels.webhook.feishu");
    }
    if (connection.channel_type === "wecom") {
      return t("channels.webhook.wecom");
    }
    if (connection.channel_type === "dingtalk") {
      return t("channels.webhook.dingtalk");
    }
    return t("channels.webhook.default");
  };

  const getConversationTypeLabel = (conversationType: string) => {
    const keyByType: Record<string, string> = {
      private: "channels.conversationDialog.private",
      group: "channels.conversationDialog.group",
      supergroup: "channels.conversationDialog.supergroup",
      channel: "channels.conversationDialog.channel",
    };
    return keyByType[conversationType]
      ? t(keyByType[conversationType])
      : conversationType;
  };

  const getConversationStatusLabel = (status: ChannelConversationStatus) => {
    const labels: Record<ChannelConversationStatus, string> = {
      pending: "待配置",
      inherited: "继承全局",
      overridden: "独立配置",
      ignored: "已忽略",
      disabled: "已停用",
      unavailable: "不可访问",
    };
    return labels[status];
  };

  const openNewConnection = (channelType: SupportedChannelType) => {
    setNewChannelType(channelType);
    setEditingConnection(null);
    setConnectionDialogOpen(true);
  };

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
        : await createConnection.mutateAsync(
            payload as ChannelConnectionCreate,
          );

      if (connection.channel_type === "telegram" && publicBaseUrl) {
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
        title:
          connection.channel_type === "telegram" && publicBaseUrl
            ? t("channels.toast.telegramConfigured")
            : t("channels.toast.connectionSaved", { name: connection.name }),
      });
    } catch (error) {
      showError(t("channels.toast.connectionSaveFailed"), error);
      throw error;
    }
  };

  const handleRoutingSubmit = async () => {
    if (!selectedConnection) return;
    try {
      await updateConnection.mutateAsync({
        connectionId: selectedConnection.id,
        payload: {
          default_flow_id: routingForm.defaultFlowId || null,
          default_knowledge_base_id:
            routingForm.defaultKnowledgeBaseId || null,
          auto_discover_conversations:
            routingForm.autoDiscoverConversations,
          unconfigured_behavior: routingForm.unconfiguredBehavior,
          pending_notice_enabled: routingForm.pendingNoticeEnabled,
          personal_commands_enabled: routingForm.personalCommandsEnabled,
          default_response_mode: routingForm.defaultResponseMode,
          default_allow_file_upload:
            routingForm.defaultAllowFileUpload,
        },
      });
      setSuccessData({ title: "默认路由设置已保存" });
    } catch (error) {
      showError("默认路由保存失败", error);
    }
  };

  const handleTestConnection = async (connection: ChannelConnection) => {
    try {
      const result = await testConnection.mutateAsync({
        connectionId: connection.id,
      });
      setSuccessData({
        title: t("channels.toast.connectionSucceeded", {
          name: result.username ?? result.display_name ?? connection.name,
        }),
      });
    } catch (error) {
      showError(t("channels.toast.connectionTestFailed"), error);
    }
  };

  const handleConfigureTelegramWebhook = async (
    connection: ChannelConnection,
  ) => {
    const publicBaseUrl = readConnectionSetting(
      connection,
      "public_base_url",
      "",
    );
    if (!publicBaseUrl) {
      setEditingConnection(connection);
      setConnectionDialogOpen(true);
      setErrorData({
        title: t("channels.toast.publicUrlRequired"),
        list: [t("channels.toast.publicUrlRequiredDetail")],
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
      setSuccessData({
        title: t("channels.toast.webhookConfigured", {
          url: result.webhook_url,
        }),
      });
    } catch (error) {
      showError(t("channels.toast.webhookFailed"), error);
    }
  };

  const handleRedeemBinding = async () => {
    if (!bindingCode.trim()) return;
    try {
      await redeemBinding.mutateAsync({ code: bindingCode.trim() });
      setBindingCode("");
      setSuccessData({ title: t("channels.toast.accountBound") });
    } catch (error) {
      showError(t("channels.toast.bindingCodeFailed"), error);
    }
  };

  const handleConversationSubmit = async (
    payload: ChannelConversationBindingUpdate,
  ) => {
    if (!selectedConnection || !editingConversation) return;
    try {
      await updateConversation.mutateAsync({
        connectionId: selectedConnection.id,
        bindingId: editingConversation.id,
        payload,
      });
      setConversationDialogOpen(false);
      setEditingConversation(null);
      setSuccessData({ title: t("channels.toast.conversationSaved") });
    } catch (error) {
      showError(t("channels.toast.conversationSaveFailed"), error);
      throw error;
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget || !selectedConnection) return;
    try {
      if (deleteTarget.kind === "connection") {
        await deleteConnection.mutateAsync({ connectionId: deleteTarget.id });
        setSuccessData({ title: t("channels.toast.connectionDeleted") });
      } else {
        await deleteIdentity.mutateAsync({
          connectionId: selectedConnection.id,
          identityId: deleteTarget.id,
        });
        setSuccessData({ title: t("channels.toast.accountUnbound") });
      }
    } catch (error) {
      showError(t("channels.toast.deleteFailed"), error);
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

  const webhookUrl = selectedConnection
    ? buildChannelWebhookUrl(selectedConnection)
    : null;
  const showWebhookUrl =
    selectedConnection?.channel_type !== "dingtalk" ||
    selectedConnection?.connection_mode !== "stream";

  const tabs: Array<{ id: DetailTab; label: string }> = [
    { id: "overview", label: "概览" },
    { id: "routing", label: "默认路由" },
    { id: "conversations", label: "会话" },
    { id: "commands", label: "指令" },
    { id: "accounts", label: "账号" },
    { id: "logs", label: "运行记录" },
  ];

  return (
    <div className="flex h-full w-full flex-col gap-6 overflow-y-auto pb-8 pr-1">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
            {t("channels.title")}
            <ForwardedIconComponent
              name="RadioTower"
              className="h-5 w-5 text-primary"
            />
          </h2>
          <p className="max-w-3xl text-sm text-muted-foreground">
            {t("channels.description")}
          </p>
        </div>
        <Button variant="primary" onClick={() => openNewConnection("telegram")}>
          <ForwardedIconComponent name="Plus" className="h-4 w-4" />
          {t("channels.addConnection")}
        </Button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {PROVIDERS.map((provider) => (
          <button
            type="button"
            key={provider.id}
            disabled={!provider.enabled}
            onClick={() => provider.enabled && openNewConnection(provider.id)}
            className="flex items-center justify-between rounded-xl border p-4 text-left transition-colors enabled:hover:bg-accent disabled:cursor-default"
          >
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-muted p-2">
                <ForwardedIconComponent
                  name={provider.icon}
                  className="h-5 w-5"
                />
              </div>
              <div>
                <div className="text-sm font-medium">{t(provider.nameKey)}</div>
                <div className="text-xs text-muted-foreground">
                  {t(
                    provider.enabled
                      ? "channels.provider.available"
                      : "channels.provider.comingSoon",
                  )}
                </div>
              </div>
            </div>
            <span
              className={`h-2.5 w-2.5 rounded-full ${
                provider.enabled
                  ? "bg-accent-emerald-foreground"
                  : "bg-muted-foreground/30"
              }`}
            />
          </button>
        ))}
      </div>

      <div className="grid min-h-0 gap-6 xl:grid-cols-[minmax(280px,0.8fr)_minmax(0,2fr)]">
        <section className="flex flex-col gap-3">
          <div className="text-sm font-medium text-muted-foreground">
            {t("channels.connections")}
          </div>
          {connections.length === 0 ? (
            <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
              {t("channels.emptyConnections")}
            </div>
          ) : (
            connections.map((connection) => {
              const connectionStatus = getChannelStatusMeta(
                connection.status,
                t,
              );
              const selected = selectedConnectionId === connection.id;
              return (
                <button
                  type="button"
                  key={connection.id}
                  onClick={() => setSelectedConnectionId(connection.id)}
                  className={`rounded-xl border p-4 text-left transition-colors ${
                    selected ? "border-primary bg-accent" : "hover:bg-accent/60"
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-medium">{connection.name}</div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {getProviderName(connection.channel_type)} ·{" "}
                        {getConnectionModeLabel(connection)}
                      </div>
                    </div>
                    <span
                      className={`rounded-full px-2 py-1 text-xs ${connectionStatus.className}`}
                    >
                      {connectionStatus.label}
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
              {t("channels.selectConnection")}
            </div>
          ) : (
            <>
              <div className="flex flex-wrap gap-2 border-b pb-3">
                {tabs.map((tab) => (
                  <Button
                    key={tab.id}
                    type="button"
                    size="sm"
                    variant={activeTab === tab.id ? "primary" : "ghost"}
                    onClick={() => setActiveTab(tab.id)}
                  >
                    {tab.label}
                  </Button>
                ))}
              </div>

              {activeTab === "overview" && (
                <div className="rounded-xl border p-5">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <h3 className="text-base font-semibold">
                        {selectedConnection.name}
                      </h3>
                      <p className="mt-1 text-sm text-muted-foreground">
                        {t("channels.credentialsConfigured", {
                          keys:
                            selectedConnection.configured_credential_keys.join(
                              ", ",
                            ) || t("channels.none"),
                        })}
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {t("channels.accessMode", {
                          mode: getConnectionModeLabel(selectedConnection),
                        })}{" "}
                        ·{" "}
                        {t("channels.lastConnected", {
                          time: selectedConnection.last_connected_at
                            ? new Date(
                                selectedConnection.last_connected_at,
                              ).toLocaleString(i18n.language)
                            : t("channels.notTested"),
                        })}
                      </p>

                      {showWebhookUrl && webhookUrl && (
                        <div className="mt-4 rounded-lg bg-muted/60 p-3">
                          <div className="text-xs font-medium">
                            {getWebhookLabel(selectedConnection)}
                          </div>
                          <code className="mt-1 block break-all text-xs text-muted-foreground">
                            {webhookUrl}
                          </code>
                        </div>
                      )}
                    </div>

                    <div className="flex flex-wrap gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() =>
                          handleTestConnection(selectedConnection)
                        }
                        loading={testConnection.isPending}
                      >
                        {t("channels.actions.testConnection")}
                      </Button>
                      {selectedConnection.channel_type === "telegram" && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() =>
                            handleConfigureTelegramWebhook(selectedConnection)
                          }
                          loading={configureWebhook.isPending}
                        >
                          {t("channels.actions.configureWebhook")}
                        </Button>
                      )}
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          setEditingConnection(selectedConnection);
                          setConnectionDialogOpen(true);
                        }}
                      >
                        {t("channels.actions.edit")}
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
                        {t("channels.actions.delete")}
                      </Button>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === "routing" && (
                <div className="flex flex-col gap-5 rounded-xl border p-5">
                  <div>
                    <h3 className="font-semibold">连接默认路由</h3>
                    <p className="mt-1 text-sm text-muted-foreground">
                      没有单独覆盖的会话会继承这里配置的工作流和知识库。
                    </p>
                  </div>
                  <label className="flex flex-col gap-2 text-sm font-medium">
                    全局默认工作流
                    <select
                      className="primary-input h-10"
                      value={routingForm.defaultFlowId}
                      onChange={(event) =>
                        setRoutingForm((current) => ({
                          ...current,
                          defaultFlowId: event.target.value,
                        }))
                      }
                    >
                      <option value="">不设置全局默认工作流</option>
                      {flows.map((flow) => (
                        <option key={flow.id} value={flow.id}>
                          {flow.name}
                          {flow.endpoint_name
                            ? ` (${flow.endpoint_name})`
                            : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex flex-col gap-2 text-sm font-medium">
                    全局默认知识库
                    <select
                      className="primary-input h-10"
                      value={routingForm.defaultKnowledgeBaseId}
                      onChange={(event) =>
                        setRoutingForm((current) => ({
                          ...current,
                          defaultKnowledgeBaseId: event.target.value,
                        }))
                      }
                    >
                      <option value="">不设置全局默认知识库</option>
                      {knowledgeBases.map((knowledgeBase) => (
                        <option key={knowledgeBase.id} value={knowledgeBase.id}>
                          {knowledgeBase.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex flex-col gap-2 text-sm font-medium">
                    没有可用默认工作流时
                    <select
                      className="primary-input h-10"
                      value={routingForm.unconfiguredBehavior}
                      onChange={(event) =>
                        setRoutingForm((current) => ({
                          ...current,
                          unconfiguredBehavior: event.target
                            .value as ChannelUnconfiguredBehavior,
                        }))
                      }
                    >
                      <option value="notify_pending">首次提示待配置</option>
                      <option value="ignore">静默忽略</option>
                      <option value="use_global_default">
                        优先使用全局默认工作流
                      </option>
                    </select>
                  </label>
                  <div className="grid gap-3 md:grid-cols-2">
                    <SettingSwitch
                      title="自动发现会话"
                      description="收到新私聊或群聊消息时自动记录真实平台会话 ID。"
                      checked={routingForm.autoDiscoverConversations}
                      onCheckedChange={(checked) =>
                        setRoutingForm((current) => ({
                          ...current,
                          autoDiscoverConversations: checked,
                        }))
                      }
                    />
                    <SettingSwitch
                      title="待配置提示"
                      description="无默认工作流时向会话发送一次配置提示。"
                      checked={routingForm.pendingNoticeEnabled}
                      onCheckedChange={(checked) =>
                        setRoutingForm((current) => ({
                          ...current,
                          pendingNoticeEnabled: checked,
                        }))
                      }
                    />
                    <SettingSwitch
                      title="允许个人指令"
                      description="绑定用户可创建仅对自己生效的工作流指令。"
                      checked={routingForm.personalCommandsEnabled}
                      onCheckedChange={(checked) =>
                        setRoutingForm((current) => ({
                          ...current,
                          personalCommandsEnabled: checked,
                        }))
                      }
                    />
                    <SettingSwitch
                      title="默认允许文件上传"
                      description="新发现会话默认允许接收和处理文件。"
                      checked={routingForm.defaultAllowFileUpload}
                      onCheckedChange={(checked) =>
                        setRoutingForm((current) => ({
                          ...current,
                          defaultAllowFileUpload: checked,
                        }))
                      }
                    />
                  </div>
                  {selectedCapabilities?.supports_group_chat &&
                    selectedCapabilities.supports_mentions && (
                      <label className="flex flex-col gap-2 text-sm font-medium">
                        新群聊默认响应模式
                        <select
                          className="primary-input h-10"
                          value={routingForm.defaultResponseMode}
                          onChange={(event) =>
                            setRoutingForm((current) => ({
                              ...current,
                              defaultResponseMode: event.target.value,
                            }))
                          }
                        >
                          <option value="mentions_only">
                            仅 @机器人或指令时响应
                          </option>
                          <option value="all_messages">响应所有消息</option>
                        </select>
                      </label>
                    )}
                  <div className="flex justify-end">
                    <Button
                      variant="primary"
                      onClick={handleRoutingSubmit}
                      loading={updateConnection.isPending}
                    >
                      保存默认路由
                    </Button>
                  </div>
                </div>
              )}

              {activeTab === "conversations" && (
                <div className="flex flex-col gap-4 rounded-xl border p-5">
                  <div>
                    <h3 className="font-semibold">会话管理</h3>
                    <p className="mt-1 text-sm text-muted-foreground">
                      会话由平台消息自动发现，不再需要手工填写会话 ID。
                    </p>
                  </div>
                  <div className="grid gap-3 lg:grid-cols-4">
                    <Input
                      value={conversationQueryInput}
                      onChange={(event) =>
                        setConversationQueryInput(event.target.value)
                      }
                      placeholder="搜索会话名称或平台会话 ID"
                    />
                    <select
                      className="primary-input h-10"
                      value={conversationTypeFilter}
                      onChange={(event) => {
                        setConversationTypeFilter(event.target.value);
                        setConversationPage(1);
                      }}
                    >
                      <option value="">全部会话类型</option>
                      {(selectedCapabilities?.conversation_types ?? []).map(
                        (conversationType) => (
                          <option
                            key={conversationType}
                            value={conversationType}
                          >
                            {getConversationTypeLabel(conversationType)}
                          </option>
                        ),
                      )}
                    </select>
                    <select
                      className="primary-input h-10"
                      value={conversationStatusFilter}
                      onChange={(event) => {
                        setConversationStatusFilter(
                          event.target.value as ChannelConversationStatus | "",
                        );
                        setConversationPage(1);
                      }}
                    >
                      <option value="">全部状态</option>
                      <option value="pending">待配置</option>
                      <option value="inherited">继承全局</option>
                      <option value="overridden">独立配置</option>
                      <option value="ignored">已忽略</option>
                      <option value="disabled">已停用</option>
                    </select>
                    <select
                      className="primary-input h-10"
                      value={conversationRouteFilter}
                      onChange={(event) => {
                        setConversationRouteFilter(
                          event.target.value as ChannelConversationRouteMode | "",
                        );
                        setConversationPage(1);
                      }}
                    >
                      <option value="">全部路由方式</option>
                      <option value="inherit">继承全局</option>
                      <option value="override">独立配置</option>
                      <option value="disabled">禁用普通消息</option>
                    </select>
                  </div>

                  {conversationsLoading ? (
                    <Loading />
                  ) : conversations.length === 0 ? (
                    <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
                      暂无匹配会话。用户或群聊第一次给机器人发消息后会自动出现在这里。
                    </div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full min-w-[820px] text-left text-sm">
                        <thead className="border-b text-xs text-muted-foreground">
                          <tr>
                            <th className="px-3 py-2">会话</th>
                            <th className="px-3 py-2">类型</th>
                            <th className="px-3 py-2">状态</th>
                            <th className="px-3 py-2">默认工作流</th>
                            <th className="px-3 py-2">最近活跃</th>
                            <th className="px-3 py-2 text-right">操作</th>
                          </tr>
                        </thead>
                        <tbody>
                          {conversations.map((conversation) => {
                            const flow = flows.find(
                              (item) =>
                                item.id === conversation.default_flow_id,
                            );
                            const effectiveFlowName =
                              conversation.route_mode === "override"
                                ? flow?.name ?? "未绑定"
                                : flows.find(
                                    (item) =>
                                      item.id ===
                                      selectedConnection.default_flow_id,
                                  )?.name ?? "继承但未设置";
                            return (
                              <tr
                                key={conversation.id}
                                className="border-b last:border-0"
                              >
                                <td className="px-3 py-3">
                                  <div className="font-medium">
                                    {conversation.display_name ||
                                      conversation.external_conversation_id}
                                  </div>
                                  <div className="max-w-72 truncate text-xs text-muted-foreground">
                                    {conversation.external_conversation_id}
                                  </div>
                                </td>
                                <td className="px-3 py-3">
                                  {getConversationTypeLabel(
                                    conversation.conversation_type,
                                  )}
                                </td>
                                <td className="px-3 py-3">
                                  <span className="rounded-full bg-muted px-2 py-1 text-xs">
                                    {getConversationStatusLabel(
                                      conversation.status,
                                    )}
                                  </span>
                                </td>
                                <td className="px-3 py-3">
                                  {effectiveFlowName}
                                </td>
                                <td className="px-3 py-3 text-xs text-muted-foreground">
                                  {new Date(
                                    conversation.last_message_at,
                                  ).toLocaleString(i18n.language)}
                                </td>
                                <td className="px-3 py-3 text-right">
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => {
                                      setEditingConversation(conversation);
                                      setConversationDialogOpen(true);
                                    }}
                                  >
                                    {t("channels.actions.edit")}
                                  </Button>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}

                  <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4 text-sm">
                    <div className="text-muted-foreground">
                      共 {conversationResult?.total ?? 0} 个会话
                    </div>
                    <div className="flex items-center gap-2">
                      <select
                        className="primary-input h-9 w-24"
                        value={conversationPageSize}
                        onChange={(event) => {
                          setConversationPageSize(Number(event.target.value));
                          setConversationPage(1);
                        }}
                      >
                        <option value={20}>20 条</option>
                        <option value={50}>50 条</option>
                        <option value={100}>100 条</option>
                      </select>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={conversationPage <= 1}
                        onClick={() =>
                          setConversationPage((current) =>
                            Math.max(1, current - 1),
                          )
                        }
                      >
                        上一页
                      </Button>
                      <span>
                        {conversationPage} /{" "}
                        {Math.max(1, conversationResult?.total_pages ?? 0)}
                      </span>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={
                          conversationPage >=
                          (conversationResult?.total_pages ?? 0)
                        }
                        onClick={() =>
                          setConversationPage((current) => current + 1)
                        }
                      >
                        下一页
                      </Button>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === "commands" && (
                <div className="rounded-xl border border-dashed p-10 text-center">
                  <h3 className="font-semibold">自定义指令中心</h3>
                  <p className="mt-2 text-sm text-muted-foreground">
                    将在这里管理连接共享、会话共享、个人连接和个人会话四类工作流指令。
                  </p>
                </div>
              )}

              {activeTab === "accounts" && (
                <div className="rounded-xl border p-5">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <h3 className="font-semibold">
                        {t("channels.binding.title")}
                      </h3>
                      <p className="mt-1 text-sm text-muted-foreground">
                        {t("channels.binding.description")}
                      </p>
                    </div>
                    <div className="flex w-full gap-2 sm:w-auto">
                      <Input
                        value={bindingCode}
                        onChange={(event) =>
                          setBindingCode(event.target.value.toUpperCase())
                        }
                        placeholder={t("channels.binding.placeholder")}
                        maxLength={12}
                        className="sm:w-48"
                      />
                      <Button
                        onClick={handleRedeemBinding}
                        loading={redeemBinding.isPending}
                        disabled={!bindingCode.trim()}
                      >
                        {t("channels.actions.bind")}
                      </Button>
                    </div>
                  </div>
                  <div className="mt-5 flex flex-col gap-2">
                    {identitiesLoading ? (
                      <Loading />
                    ) : identities.length === 0 ? (
                      <div className="text-sm text-muted-foreground">
                        {t("channels.binding.empty")}
                      </div>
                    ) : (
                      identities.map((identity) => (
                        <div
                          key={identity.id}
                          className="flex items-center justify-between rounded-lg bg-muted/50 px-3 py-2"
                        >
                          <div className="min-w-0">
                            <div className="truncate text-sm font-medium">
                              {identity.display_name ||
                                identity.external_user_id}
                            </div>
                            <div className="truncate text-xs text-muted-foreground">
                              {t("channels.binding.channelUser", {
                                channelUser: identity.external_user_id,
                                openxflowUser: identity.openxflow_user_id,
                              })}
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
                                name:
                                  identity.display_name ||
                                  identity.external_user_id,
                              })
                            }
                          >
                            {t("channels.actions.unbind")}
                          </Button>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}

              {activeTab === "logs" && (
                <div className="rounded-xl border border-dashed p-10 text-center">
                  <h3 className="font-semibold">渠道运行记录</h3>
                  <p className="mt-2 text-sm text-muted-foreground">
                    后续将在这里按会话、用户、触发指令和工作流查看执行状态与耗时。
                  </p>
                </div>
              )}
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
        initialChannelType={newChannelType}
        loading={
          createConnection.isPending ||
          updateConnection.isPending ||
          configureWebhook.isPending
        }
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
        supportsMentions={selectedCapabilities?.supports_mentions}
        supportsFileUpload={selectedCapabilities?.supports_file_upload}
        loading={updateConversation.isPending}
        onSubmit={handleConversationSubmit}
      />

      <DeleteConfirmationModal
        open={Boolean(deleteTarget)}
        setOpen={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        description={deleteTarget?.name ?? t("channels.deleteFallback")}
        onConfirm={handleDelete}
      />
    </div>
  );
}

function SettingSwitch({
  title,
  description,
  checked,
  onCheckedChange,
}: {
  title: string;
  description: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between rounded-lg border p-4">
      <div className="pr-4">
        <div className="text-sm font-medium">{title}</div>
        <div className="mt-1 text-xs text-muted-foreground">{description}</div>
      </div>
      <Switch checked={checked} onCheckedChange={onCheckedChange} />
    </div>
  );
}
