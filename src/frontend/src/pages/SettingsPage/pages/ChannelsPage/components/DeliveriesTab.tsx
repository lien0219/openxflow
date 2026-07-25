import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import Loading from "@/components/ui/loading";
import {
  type ChannelOutboundDeliveryStatus,
  useGetChannelDeliveries,
  useRetryChannelDelivery,
} from "@/controllers/API/queries/channels";
import useAlertStore from "@/stores/alertStore";
import useChannelCopy from "../use-channel-copy";
import { getApiErrorMessage } from "../utils";

interface DeliveriesTabProps {
  connectionId: string;
}

const STATUS_LABELS: Record<ChannelOutboundDeliveryStatus, string> = {
  reserved: "已预留",
  sent: "已发送",
  failed: "发送失败",
};

export default function DeliveriesTab({ connectionId }: DeliveriesTabProps) {
  const copy = useChannelCopy();
  const setSuccessData = useAlertStore((state) => state.setSuccessData);
  const setErrorData = useAlertStore((state) => state.setErrorData);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [queryDraft, setQueryDraft] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<ChannelOutboundDeliveryStatus | "">("");
  const [deliveryKind, setDeliveryKind] = useState("");
  const [retryingId, setRetryingId] = useState("");

  useEffect(() => {
    setPage(1);
    setQueryDraft("");
    setQuery("");
    setStatus("");
    setDeliveryKind("");
    setRetryingId("");
  }, [connectionId]);

  const {
    data: result,
    isLoading,
    isFetching,
  } = useGetChannelDeliveries(
    {
      connectionId,
      page,
      pageSize,
      query,
      status,
      deliveryKind: deliveryKind || undefined,
    },
    { enabled: Boolean(connectionId) },
  );
  const retryDelivery = useRetryChannelDelivery();

  const applySearch = () => {
    setQuery(queryDraft.trim());
    setPage(1);
  };

  const handleRetry = async (deliveryId: string) => {
    setRetryingId(deliveryId);
    try {
      const response = await retryDelivery.mutateAsync({
        connectionId,
        deliveryId,
      });
      setSuccessData({
        title: response.already_queued
          ? copy("任务已在队列中")
          : copy("失败投递已重新入队"),
      });
    } catch (error) {
      setErrorData({
        title: copy("重试失败"),
        list: [getApiErrorMessage(error, copy("无法重新投递该消息"))],
      });
    } finally {
      setRetryingId("");
    }
  };

  return (
    <div className="flex flex-col gap-4 rounded-xl border p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold">{copy("投递运维")}</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            {copy("查看幂等投递结果，并将失败消息安全地重新放回原持久化队列。")}
          </p>
        </div>
        {isFetching && !isLoading ? (
          <span className="text-xs text-muted-foreground">
            {copy("正在刷新")}
          </span>
        ) : null}
      </div>

      <div className="grid gap-3 lg:grid-cols-[minmax(280px,2fr)_180px_180px_auto]">
        <Input
          value={queryDraft}
          onChange={(event) => setQueryDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") applySearch();
          }}
          placeholder={copy("搜索事件 ID、平台消息 ID 或错误")}
        />
        <select
          className="primary-input h-10"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value as ChannelOutboundDeliveryStatus | "");
            setPage(1);
          }}
        >
          <option value="">{copy("全部投递状态")}</option>
          {Object.entries(STATUS_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {copy(label)}
            </option>
          ))}
        </select>
        <select
          className="primary-input h-10"
          value={deliveryKind}
          onChange={(event) => {
            setDeliveryKind(event.target.value);
            setPage(1);
          }}
        >
          <option value="">{copy("全部投递类型")}</option>
          <option value="response">{copy("最终回复")}</option>
          <option value="processing">{copy("处理中消息")}</option>
          <option value="acknowledgement">{copy("事件确认")}</option>
        </select>
        <div className="flex gap-2">
          <Button type="button" onClick={applySearch}>
            {copy("搜索")}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setQueryDraft("");
              setQuery("");
              setStatus("");
              setDeliveryKind("");
              setPage(1);
            }}
          >
            {copy("重置")}
          </Button>
        </div>
      </div>

      {isLoading ? (
        <Loading />
      ) : (result?.items.length ?? 0) === 0 ? (
        <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
          {copy("当前筛选条件下暂无投递记录")}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1080px] text-left text-sm">
            <thead className="border-b text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2">{copy("时间")}</th>
                <th className="px-3 py-2">{copy("类型 / 状态")}</th>
                <th className="px-3 py-2">{copy("事件 ID")}</th>
                <th className="px-3 py-2">{copy("平台消息 ID")}</th>
                <th className="px-3 py-2">{copy("尝试次数")}</th>
                <th className="px-3 py-2">{copy("最后错误")}</th>
                <th className="px-3 py-2">{copy("操作")}</th>
              </tr>
            </thead>
            <tbody>
              {(result?.items ?? []).map((delivery) => (
                <tr
                  key={delivery.id}
                  className="border-b align-top last:border-0"
                >
                  <td className="whitespace-nowrap px-3 py-3 text-xs text-muted-foreground">
                    {new Date(delivery.updated_at).toLocaleString()}
                  </td>
                  <td className="px-3 py-3">
                    <div>{delivery.delivery_kind}</div>
                    <span className="mt-1 inline-flex rounded-full bg-muted px-2 py-1 text-xs">
                      {copy(STATUS_LABELS[delivery.status])}
                    </span>
                  </td>
                  <td className="max-w-64 px-3 py-3 font-mono text-xs">
                    <div
                      className="truncate"
                      title={delivery.external_event_id}
                    >
                      {delivery.external_event_id}
                    </div>
                  </td>
                  <td className="max-w-64 px-3 py-3 font-mono text-xs text-muted-foreground">
                    <div
                      className="truncate"
                      title={delivery.provider_message_id ?? undefined}
                    >
                      {delivery.provider_message_id || "-"}
                    </div>
                  </td>
                  <td className="px-3 py-3">{delivery.attempts}</td>
                  <td className="max-w-80 px-3 py-3 text-xs text-destructive">
                    <div className="line-clamp-3">
                      {delivery.last_error || "-"}
                    </div>
                  </td>
                  <td className="px-3 py-3">
                    {delivery.status === "failed" ? (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={Boolean(retryingId)}
                        onClick={() => handleRetry(delivery.id)}
                      >
                        {retryingId === delivery.id
                          ? copy("重新入队中")
                          : copy("重新投递")}
                      </Button>
                    ) : (
                      <span className="text-xs text-muted-foreground">-</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4 text-sm">
        <div className="text-muted-foreground">
          {copy("共 {{count}} 条记录", { count: result?.total ?? 0 })}
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
    </div>
  );
}
