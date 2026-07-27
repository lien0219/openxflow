import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import Loading from "@/components/ui/loading";
import {
  type ChannelMessageDirection,
  type ChannelMessageStatus,
  useGetChannelMessages,
} from "@/controllers/API/queries/channels";
import useChannelCopy from "../use-channel-copy";

interface MessagesTabProps {
  connectionId: string;
}

const DIRECTION_LABELS: Record<ChannelMessageDirection, string> = {
  inbound: "收到",
  outbound: "发出",
};

const STATUS_LABELS: Record<ChannelMessageStatus, string> = {
  received: "已接收",
  processed: "已处理",
  pending: "待发送",
  sent: "已发送",
  failed: "失败",
};

export default function MessagesTab({ connectionId }: MessagesTabProps) {
  const copy = useChannelCopy();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [queryDraft, setQueryDraft] = useState("");
  const [query, setQuery] = useState("");
  const [conversationId, setConversationId] = useState("");
  const [externalUserId, setExternalUserId] = useState("");
  const [direction, setDirection] = useState<ChannelMessageDirection | "">("");
  const [status, setStatus] = useState<ChannelMessageStatus | "">("");

  useEffect(() => {
    setPage(1);
    setQueryDraft("");
    setQuery("");
    setConversationId("");
    setExternalUserId("");
    setDirection("");
    setStatus("");
  }, [connectionId]);

  const {
    data: result,
    isLoading,
    isFetching,
  } = useGetChannelMessages(
    {
      connectionId,
      page,
      pageSize,
      query,
      direction,
      status,
      externalConversationId: conversationId.trim() || undefined,
      externalUserId: externalUserId.trim() || undefined,
    },
    { enabled: Boolean(connectionId) },
  );

  const applySearch = () => {
    setQuery(queryDraft.trim());
    setPage(1);
  };

  const clearFilters = () => {
    setQueryDraft("");
    setQuery("");
    setConversationId("");
    setExternalUserId("");
    setDirection("");
    setStatus("");
    setPage(1);
  };

  return (
    <div className="flex min-w-0 flex-col gap-4 rounded-xl border p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold">{copy("消息中心")}</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            {copy(
              "统一查看四个渠道经过脱敏处理的收发消息、线程、附件与处理状态。",
            )}
          </p>
        </div>
        {isFetching && !isLoading ? (
          <span className="text-xs text-muted-foreground">
            {copy("正在刷新")}
          </span>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Input
          className="min-w-[240px] flex-[2_1_320px]"
          value={queryDraft}
          onChange={(event) => setQueryDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") applySearch();
          }}
          placeholder={copy("搜索消息、发送人、用户或会话 ID")}
        />
        <Input
          className="min-w-[170px] flex-1"
          value={conversationId}
          onChange={(event) => {
            setConversationId(event.target.value);
            setPage(1);
          }}
          placeholder={copy("会话 ID")}
        />
        <Input
          className="min-w-[170px] flex-1"
          value={externalUserId}
          onChange={(event) => {
            setExternalUserId(event.target.value);
            setPage(1);
          }}
          placeholder={copy("渠道用户 ID")}
        />
        <select
          className="primary-input h-10 min-w-[140px] flex-1"
          value={direction}
          onChange={(event) => {
            setDirection(event.target.value as ChannelMessageDirection | "");
            setPage(1);
          }}
        >
          <option value="">{copy("全部方向")}</option>
          <option value="inbound">{copy("收到")}</option>
          <option value="outbound">{copy("发出")}</option>
        </select>
        <select
          className="primary-input h-10 min-w-[140px] flex-1"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value as ChannelMessageStatus | "");
            setPage(1);
          }}
        >
          <option value="">{copy("全部状态")}</option>
          {Object.entries(STATUS_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {copy(label)}
            </option>
          ))}
        </select>
        <div className="ml-auto flex shrink-0 gap-2">
          <Button type="button" onClick={applySearch}>
            {copy("搜索")}
          </Button>
          <Button type="button" variant="outline" onClick={clearFilters}>
            {copy("重置")}
          </Button>
        </div>
      </div>

      <div className="min-h-44 min-w-0">
        {isLoading ? (
          <div className="flex min-h-44 w-full items-center justify-center">
            <Loading />
          </div>
        ) : (result?.items.length ?? 0) === 0 ? (
          <div className="flex min-h-44 items-center justify-center rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
            {copy("当前筛选条件下暂无消息记录")}
          </div>
        ) : (
          <div className="max-w-full overflow-x-auto">
            <table className="w-full min-w-[1080px] table-fixed text-left text-sm">
              <thead className="border-b text-xs text-muted-foreground">
                <tr>
                  <th className="w-40 px-3 py-2">{copy("时间")}</th>
                  <th className="w-32 px-3 py-2">{copy("方向 / 状态")}</th>
                  <th className="w-48 px-3 py-2">{copy("发送人 / 用户")}</th>
                  <th className="w-56 px-3 py-2">{copy("会话 / 线程")}</th>
                  <th className="w-[360px] px-3 py-2">{copy("消息内容")}</th>
                  <th className="w-20 px-3 py-2">{copy("附件")}</th>
                  <th className="w-56 px-3 py-2">{copy("错误")}</th>
                </tr>
              </thead>
              <tbody>
                {(result?.items ?? []).map((message) => (
                  <tr
                    key={message.id}
                    className="border-b align-top last:border-0"
                  >
                    <td className="whitespace-nowrap px-3 py-3 text-xs text-muted-foreground">
                      {new Date(message.created_at).toLocaleString()}
                    </td>
                    <td className="px-3 py-3">
                      <div>{copy(DIRECTION_LABELS[message.direction])}</div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {copy(STATUS_LABELS[message.status])} ·{" "}
                        {message.message_type}
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      <div className="truncate">
                        {message.sender_name || "-"}
                      </div>
                      <div className="mt-1 truncate font-mono text-xs text-muted-foreground">
                        {message.external_user_id || "-"}
                      </div>
                    </td>
                    <td className="px-3 py-3 font-mono text-xs">
                      <div
                        className="truncate"
                        title={message.external_conversation_id}
                      >
                        {message.external_conversation_id}
                      </div>
                      <div className="mt-1 truncate text-muted-foreground">
                        {message.conversation_scope_id || copy("默认会话范围")}
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      <div className="line-clamp-4 whitespace-pre-wrap break-words">
                        {message.text || copy("无文本内容")}
                      </div>
                      <div className="mt-1 truncate font-mono text-[11px] text-muted-foreground">
                        {message.external_message_id ||
                          message.provider_message_id ||
                          "-"}
                      </div>
                    </td>
                    <td className="px-3 py-3 text-xs text-muted-foreground">
                      {message.has_attachments
                        ? copy("{{count}} 个", {
                            count: message.attachment_count,
                          })
                        : "-"}
                    </td>
                    <td className="px-3 py-3 text-xs text-destructive">
                      {message.error_code ? (
                        <div className="truncate font-mono">
                          {message.error_code}
                        </div>
                      ) : null}
                      <div className="line-clamp-3 break-words">
                        {message.error_message || "-"}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

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
