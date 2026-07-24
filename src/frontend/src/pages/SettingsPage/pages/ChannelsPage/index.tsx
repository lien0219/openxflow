import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import ForwardedIconComponent from "@/components/common/genericIconComponent";
import { Button } from "@/components/ui/button";
import Loading from "@/components/ui/loading";
import {
  type ChannelConnection,
  type ChannelConnectionCreate,
  type ChannelConnectionUpdate,
  type ChannelType,
  useConfigureTelegramWebhook,
  useCreateChannelConnection,
  useDeleteChannelConnection,
  useGetChannelConnections,
  useGetChannelProviderCapabilities,
  useTestChannelConnection,
  useUpdateChannelConnection,
} from "@/controllers/API/queries/channels";
import DeleteConfirmationModal from "@/modals/deleteConfirmationModal";
import useAlertStore from "@/stores/alertStore";
import AccountsTab from "./components/AccountsTab";
import ChannelConnectionDialog from "./components/ChannelConnectionDialog";
import CommandsTab from "./components/CommandsTab";
import ConnectionOverviewTab from "./components/ConnectionOverviewTab";
import ConversationsTab from "./components/ConversationsTab";
import DefaultRoutingTab from "./components/DefaultRoutingTab";
import ExecutionLogsTab from "./components/ExecutionLogsTab";
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

const TABS: Array<{ id: DetailTab; label: string }> = [
  { id: "overview", label: "概览" },
  { id: "routing", label: "默认路由" },
  { id: "conversations", label: "会话" },
  { id: "commands", label: "指令" },
  { id: "accounts", label: "账号" },
  { id: "logs", label: "运行记录" },
];

export default function ChannelsPage() {
  const { t } = useTranslation();
  const setSuccessData = useAlertStore((state) => state.setSuccessData);
  const setErrorData = useAlertStore((state) => state.setErrorData);
  const [selectedConnectionId, setSelectedConnectionId] = useState("");
  const [activeTab, setActiveTab] = useState<DetailTab>("overview");
  const [connectionDialogOpen, setConnectionDialogOpen] = useState(false);
  const [newChannelType, setNewChannelType] =
    useState<SupportedChannelType>("telegram");
  const [editingConnection, setEditingConnection] =
    useState<ChannelConnection | null>(null);
  const [deleteConnectionTarget, setDeleteConnectionTarget] =
    useState<ChannelConnection | null>(null);

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
    setActiveTab("overview");
  }, [selectedConnectionId]);

  const createConnection = useCreateChannelConnection();
  const updateConnection = useUpdateChannelConnection();
  const deleteConnection = useDeleteChannelConnection();
  const testConnection = useTestChannelConnection();
  const configureWebhook = useConfigureTelegramWebhook();

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

  const handleDeleteConnection = async () => {
    if (!deleteConnectionTarget) return;
    try {
      await deleteConnection.mutateAsync({
        connectionId: deleteConnectionTarget.id,
      });
      setDeleteConnectionTarget(null);
      setSuccessData({ title: t("channels.toast.connectionDeleted") });
    } catch (error) {
      showError(t("channels.toast.deleteFailed"), error);
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
              <div className="flex flex-wrap gap-2 border-b pb-3">
                {TABS.map((tab) => (
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
                <ConnectionOverviewTab
                  connection={selectedConnection}
                  modeLabel={getConnectionModeLabel(selectedConnection)}
                  webhookLabel={getWebhookLabel(selectedConnection)}
                  webhookUrl={buildChannelWebhookUrl(selectedConnection)}
                  showWebhookUrl={
                    selectedConnection.channel_type !== "dingtalk" ||
                    selectedConnection.connection_mode !== "stream"
                  }
                  testing={testConnection.isPending}
                  configuringWebhook={configureWebhook.isPending}
                  onTest={() => handleTestConnection(selectedConnection)}
                  onConfigureWebhook={() =>
                    handleConfigureTelegramWebhook(selectedConnection)
                  }
                  onEdit={() => {
                    setEditingConnection(selectedConnection);
                    setConnectionDialogOpen(true);
                  }}
                  onDelete={() =>
                    setDeleteConnectionTarget(selectedConnection)
                  }
                />
              )}
              {activeTab === "routing" && (
                <DefaultRoutingTab
                  connection={selectedConnection}
                  capabilities={selectedCapabilities}
                />
              )}
              {activeTab === "conversations" && (
                <ConversationsTab
                  connection={selectedConnection}
                  capabilities={selectedCapabilities}
                />
              )}
              {activeTab === "commands" && (
                <CommandsTab connectionId={selectedConnection.id} />
              )}
              {activeTab === "accounts" && (
                <AccountsTab connectionId={selectedConnection.id} />
              )}
              {activeTab === "logs" && (
                <ExecutionLogsTab connectionId={selectedConnection.id} />
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

      <DeleteConfirmationModal
        open={Boolean(deleteConnectionTarget)}
        setOpen={(open) => {
          if (!open) setDeleteConnectionTarget(null);
        }}
        description={deleteConnectionTarget?.name ?? ""}
        onConfirm={handleDeleteConnection}
      />
    </div>
  );
}
