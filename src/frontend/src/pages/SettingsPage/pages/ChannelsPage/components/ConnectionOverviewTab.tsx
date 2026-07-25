import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import Loading from "@/components/ui/loading";
import {
  type ChannelConnection,
  useGetChannelOverview,
} from "@/controllers/API/queries/channels";
import useChannelCopy from "../use-channel-copy";

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

function formatDuration(value: number | null): string {
  if (value === null) return "-";
  if (value < 1000) return `${Math.round(value)} ms`;
  return `${(value / 1000).toFixed(2)} s`;
}

function MetricCard({
  label,
  value,
  detail,
}: {
  label: string;
  value: string | number;
  detail?: string;
}) {
  return (
    <div className="rounded-xl border bg-card p-4">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-2 text-2xl font-semibold tracking-tight">{value}</div>
      {detail ? (
        <div className="mt-1 text-xs text-muted-foreground">{detail}</div>
      ) : null}
    </div>
  );
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
  const copy = useChannelCopy();
  const [windowHours, setWindowHours] = useState(24);
  const {
    data: overview,
    isLoading,
    isFetching,
  } = useGetChannelOverview(
    { connectionId: connection.id, windowHours },
    { enabled: Boolean(connection.id) },
  );

  const succeeded = overview?.execution_counts.succeeded ?? 0;
  const failed =
    (overview?.execution_counts.failed ?? 0) +
    (overview?.execution_counts.timeout ?? 0) +
    (overview?.execution_counts.delivery_failed ?? 0);

  return (
    <div className="flex flex-col gap-4">
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
            <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
              <span className="rounded-full bg-muted px-2 py-1">
                {copy("访问策略：{{value}}", {
                  value: connection.access_policy,
                })}
              </span>
              <span className="rounded-full bg-muted px-2 py-1">
                {copy("上下文：{{value}}", {
                  value: connection.default_context_mode,
                })}
              </span>
              <span className="rounded-full bg-muted px-2 py-1">
                {copy("服务身份：{{value}}", {
                  value:
                    connection.service_user_id?.slice(0, 8) ?? copy("未创建"),
                })}
              </span>
            </div>

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

      <div className="rounded-xl border p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="font-semibold">{copy("运行概览")}</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              {copy(
                "基于持久化消息、队列、执行和投递记录统计，不依赖单进程内存。",
              )}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {isFetching && !isLoading ? (
              <span className="text-xs text-muted-foreground">
                {copy("正在刷新")}
              </span>
            ) : null}
            <select
              className="primary-input h-9"
              value={windowHours}
              onChange={(event) => setWindowHours(Number(event.target.value))}
            >
              <option value={24}>{copy("最近 24 小时")}</option>
              <option value={24 * 7}>{copy("最近 7 天")}</option>
              <option value={24 * 30}>{copy("最近 30 天")}</option>
            </select>
          </div>
        </div>

        {isLoading ? (
          <div className="mt-5">
            <Loading />
          </div>
        ) : overview ? (
          <>
            <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <MetricCard
                label={copy("活跃会话")}
                value={overview.active_conversations}
                detail={copy("{{count}} 个渠道用户", {
                  count: overview.unique_external_users,
                })}
              />
              <MetricCard
                label={copy("收发消息")}
                value={overview.inbound_messages + overview.outbound_messages}
                detail={copy("收到 {{inbound}} · 发出 {{outbound}}", {
                  inbound: overview.inbound_messages,
                  outbound: overview.outbound_messages,
                })}
              />
              <MetricCard
                label={copy("执行成功率")}
                value={`${(overview.execution_success_rate * 100).toFixed(1)}%`}
                detail={copy("成功 {{success}} · 异常 {{failed}}", {
                  success: succeeded,
                  failed,
                })}
              />
              <MetricCard
                label={copy("排队任务")}
                value={overview.queued_jobs}
                detail={copy("处理中 {{processing}} · 失败 {{failed}}", {
                  processing: overview.processing_jobs,
                  failed: overview.failed_jobs,
                })}
              />
              <MetricCard
                label={copy("平均执行耗时")}
                value={formatDuration(overview.average_execution_duration_ms)}
                detail={copy("P95：{{value}}", {
                  value: formatDuration(overview.p95_execution_duration_ms),
                })}
              />
              <MetricCard
                label={copy("平均排队等待")}
                value={formatDuration(overview.average_queue_wait_ms)}
                detail={copy("P95：{{value}}", {
                  value: formatDuration(overview.p95_queue_wait_ms),
                })}
              />
              <MetricCard
                label={copy("投递结果")}
                value={overview.sent_deliveries}
                detail={copy("失败 {{failed}} · 预留 {{reserved}}", {
                  failed: overview.failed_deliveries,
                  reserved: overview.reserved_deliveries,
                })}
              />
              <MetricCard
                label={copy("消息异常")}
                value={overview.failed_messages}
                detail={copy("包含处理失败与投递失败")}
              />
            </div>

            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4 text-sm">
              <div className="rounded-lg bg-muted/50 p-3">
                <div className="text-xs text-muted-foreground">
                  {copy("连接并发")}
                </div>
                <div className="mt-1 font-medium">
                  {connection.max_concurrency} / {copy("单用户")}{" "}
                  {connection.per_user_concurrency}
                </div>
              </div>
              <div className="rounded-lg bg-muted/50 p-3">
                <div className="text-xs text-muted-foreground">
                  {copy("单用户队列")}
                </div>
                <div className="mt-1 font-medium">
                  {connection.per_user_queue_limit}
                </div>
              </div>
              <div className="rounded-lg bg-muted/50 p-3">
                <div className="text-xs text-muted-foreground">
                  {copy("频率 / 每日配额")}
                </div>
                <div className="mt-1 font-medium">
                  {connection.rate_limit_per_minute} / min ·{" "}
                  {connection.daily_quota || copy("不限")}
                </div>
              </div>
              <div className="rounded-lg bg-muted/50 p-3">
                <div className="text-xs text-muted-foreground">
                  {copy("排队 / 执行超时")}
                </div>
                <div className="mt-1 font-medium">
                  {connection.queue_timeout_seconds}s /{" "}
                  {connection.task_timeout_seconds}s
                </div>
              </div>
            </div>
          </>
        ) : (
          <div className="mt-5 rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
            {copy("暂时无法读取运行统计")}
          </div>
        )}
      </div>
    </div>
  );
}
