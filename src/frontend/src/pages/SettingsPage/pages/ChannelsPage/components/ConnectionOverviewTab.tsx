import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import type { ChannelConnection } from "@/controllers/API/queries/channels";

interface ConnectionOverviewTabProps {
  connection: ChannelConnection;
  modeLabel: string;
  webhookLabel: string;
  webhookUrl: string | null;
  showWebhookUrl: boolean;
  testing: boolean;
  configuringWebhook: boolean;
  onTest: () => void;
  onConfigureWebhook: () => void;
  onEdit: () => void;
  onDelete: () => void;
}

export default function ConnectionOverviewTab({
  connection,
  modeLabel,
  webhookLabel,
  webhookUrl,
  showWebhookUrl,
  testing,
  configuringWebhook,
  onTest,
  onConfigureWebhook,
  onEdit,
  onDelete,
}: ConnectionOverviewTabProps) {
  const { t, i18n } = useTranslation();

  return (
    <div className="rounded-xl border p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <h3 className="text-base font-semibold">{connection.name}</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            {t("channels.credentialsConfigured", {
              keys:
                connection.configured_credential_keys.join(", ") ||
                t("channels.none"),
            })}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {t("channels.accessMode", { mode: modeLabel })} ·{" "}
            {t("channels.lastConnected", {
              time: connection.last_connected_at
                ? new Date(connection.last_connected_at).toLocaleString(
                    i18n.language,
                  )
                : t("channels.notTested"),
            })}
          </p>

          {connection.last_error && (
            <div className="mt-4 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-xs text-destructive">
              {connection.last_error}
            </div>
          )}

          {showWebhookUrl && webhookUrl && (
            <div className="mt-4 rounded-lg bg-muted/60 p-3">
              <div className="text-xs font-medium">{webhookLabel}</div>
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
            onClick={onTest}
            loading={testing}
          >
            {t("channels.actions.testConnection")}
          </Button>
          {connection.channel_type === "telegram" && (
            <Button
              variant="outline"
              size="sm"
              onClick={onConfigureWebhook}
              loading={configuringWebhook}
            >
              {t("channels.actions.configureWebhook")}
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={onEdit}>
            {t("channels.actions.edit")}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="text-destructive"
            onClick={onDelete}
          >
            {t("channels.actions.delete")}
          </Button>
        </div>
      </div>
    </div>
  );
}
