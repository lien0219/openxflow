import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import ForwardedIconComponent from "@/components/common/genericIconComponent";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import Loading from "@/components/ui/loading";
import {
  type ChannelConnection,
  type ChannelConnectionCreate,
  type ChannelConnectionUpdate,
  type ChannelConversationBinding,
  type ChannelConversationBindingUpsert,
  type ChannelType,
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

type DeleteTarget =
  | { kind: "connection"; id: string; name: string }
  | { kind: "identity"; id: string; name: string }
  | null;

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

export default function ChannelsPage() {
  const { t, i18n } = useTranslation();
  const setSuccessData = useAlertStore((state) => state.setSuccessData);
  const setErrorData = useAlertStore((state) => state.setErrorData);
  const [selectedConnectionId, setSelectedConnectionId] = useState("");
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

  const { data: connections = [], isLoading: connectionsLoading } =
    useGetChannelConnections();
  const selectedConnection = useMemo(
    () =>
      connections.find(
        (connection) => connection.id === selectedConnectionId,
      ) ?? null,
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
    payload: ChannelConversationBindingUpsert,
  ) => {
    if (!selectedConnection) return;
    try {
      await upsertConversation.mutateAsync({
        connectionId: selectedConnection.id,
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

      <div className="grid min-h-0 gap-6 xl:grid-cols-[minmax(280px,0.8fr)_minmax(0,1.8fr)]">
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
              const status = getChannelStatusMeta(connection.status, t);
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
                      className={`rounded-full px-2 py-1 text-xs ${status.className}`}
                    >
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
              {t("channels.selectConnection")}
            </div>
          ) : (
            <>
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

                    {selectedConnection.channel_type === "dingtalk" &&
                      selectedConnection.connection_mode === "stream" && (
                        <div className="mt-4 rounded-lg bg-muted/60 p-3 text-xs text-muted-foreground">
                          {t("channels.instructions.dingtalkStream")}
                        </div>
                      )}

                    {selectedConnection.channel_type === "wecom" && (
                      <div className="mt-4 rounded-lg border bg-muted/40 p-3 text-xs text-muted-foreground">
                        {t("channels.instructions.wecom")}
                      </div>
                    )}

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
                      onClick={() => handleTestConnection(selectedConnection)}
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
                            {identity.display_name || identity.external_user_id}
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

              <div className="rounded-xl border p-5">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h3 className="font-semibold">
                      {t("channels.conversations.title")}
                    </h3>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {t("channels.conversations.description")}
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
                    {t("channels.actions.addBinding")}
                  </Button>
                </div>
                <div className="mt-5 flex flex-col gap-2">
                  {conversationsLoading ? (
                    <Loading />
                  ) : conversations.length === 0 ? (
                    <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
                      {t("channels.conversations.empty")}
                    </div>
                  ) : (
                    conversations.map((conversation) => {
                      const flow = flows.find(
                        (item) => item.id === conversation.default_flow_id,
                      );
                      const knowledgeBase = knowledgeBases.find(
                        (item) => item.id === conversation.knowledge_base_id,
                      );
                      return (
                        <div
                          key={conversation.id}
                          className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-muted/50 px-3 py-3"
                        >
                          <div className="min-w-0">
                            <div className="text-sm font-medium">
                              {conversation.display_name ||
                                conversation.external_conversation_id}
                            </div>
                            <div className="mt-1 text-xs text-muted-foreground">
                              {t("channels.conversations.conversationId", {
                                type: getConversationTypeLabel(
                                  conversation.conversation_type,
                                ),
                                id: conversation.external_conversation_id,
                              })}
                            </div>
                            <div className="mt-1 text-xs text-muted-foreground">
                              {t("channels.conversations.summary", {
                                flow:
                                  flow?.name ??
                                  t("channels.conversations.unbound"),
                                knowledgeBase:
                                  knowledgeBase?.name ??
                                  t("channels.conversations.unbound"),
                                fileUpload: conversation.allow_file_upload
                                  ? t("channels.conversations.fileAllowed")
                                  : t("channels.conversations.fileDisabled"),
                              })}
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
                            {t("channels.actions.edit")}
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
        loading={upsertConversation.isPending}
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
