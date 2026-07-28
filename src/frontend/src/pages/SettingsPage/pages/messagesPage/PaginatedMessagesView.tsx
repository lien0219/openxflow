import type { NewValueParams, SelectionChangedEvent } from "ag-grid-community";
import cloneDeep from "lodash/cloneDeep";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import TableComponent from "@/components/core/parameterRenderComponent/components/tableComponent";
import Loading from "@/components/ui/loading";
import {
  type MessagePageItem,
  useDeleteMessages,
  useGetMessagesPageQuery,
  useUpdateMessage,
} from "@/controllers/API/queries/messages";
import useAlertStore from "@/stores/alertStore";
import { extractColumnsFromRows, messagesSorter } from "@/utils/utils";

const PAGE_SIZE_OPTIONS = [20, 50, 100] as const;

export default function PaginatedMessagesView() {
  const { t } = useTranslation();
  const setErrorData = useAlertStore((state) => state.setErrorData);
  const setSuccessData = useAlertStore((state) => state.setSuccessData);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(20);
  const [searchDraft, setSearchDraft] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedRows, setSelectedRows] = useState<string[]>([]);

  const { data, isFetching, refetch } = useGetMessagesPageQuery(
    {
      page,
      pageSize,
      query: searchQuery || undefined,
    },
    {},
  );

  const rows = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = data?.total_pages ?? 0;

  useEffect(() => {
    if (totalPages > 0 && page > totalPages) {
      setPage(totalPages);
    }
  }, [page, totalPages]);

  const columns = useMemo(() => {
    const columnHeaderMap: Record<string, string> = {
      timestamp: t("messages.column.timestamp"),
      text: t("messages.column.text"),
      sender: t("messages.column.sender"),
      sender_name: t("messages.column.senderName"),
      session_id: t("messages.column.sessionId"),
      files: t("messages.column.files"),
    };
    return extractColumnsFromRows(rows, "intersection")
      .map((column) =>
        column.field && columnHeaderMap[column.field]
          ? { ...column, headerName: columnHeaderMap[column.field] }
          : column,
      )
      .sort(messagesSorter);
  }, [rows, t]);

  const { mutate: deleteMessages } = useDeleteMessages({
    onSuccess: async () => {
      setSelectedRows([]);
      setSuccessData({ title: t("success.messagesDeleted") });
      await refetch();
    },
    onError: () => {
      setErrorData({ title: t("errors.deletingMessages") });
    },
  });

  const { mutate: updateMessageMutation } = useUpdateMessage();

  function handleUpdateMessage(
    event: NewValueParams<Record<string, unknown>, string>,
  ) {
    const field = event.column.getColId();
    const message = {
      ...cloneDeep(event.data),
      [field]: event.newValue,
    };
    updateMessageMutation(
      { message },
      {
        onSuccess: async () => {
          setSuccessData({ title: t("success.messagesUpdated") });
          await refetch();
        },
        onError: () => {
          setErrorData({ title: t("errors.updatingMessages") });
          event.data[field] = event.oldValue;
          event.api.refreshCells();
        },
      },
    );
  }

  function applySearch() {
    setPage(1);
    setSearchQuery(searchDraft.trim());
  }

  return (
    <div className="flex h-full min-h-0 w-full flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={searchDraft}
          onChange={(event) => setSearchDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              applySearch();
            }
          }}
          placeholder={t("messages.searchPlaceholder", {
            defaultValue: "搜索消息、发送人或会话 ID",
          })}
          className="h-9 min-w-[18rem] flex-1 rounded-md border bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring"
        />
        <button
          type="button"
          onClick={applySearch}
          className="h-9 rounded-md bg-primary px-4 text-sm text-primary-foreground"
        >
          {t("common.search", { defaultValue: "搜索" })}
        </button>
        <button
          type="button"
          onClick={() => {
            setSearchDraft("");
            setSearchQuery("");
            setPage(1);
          }}
          className="h-9 rounded-md border bg-background px-4 text-sm"
        >
          {t("common.reset", { defaultValue: "重置" })}
        </button>
      </div>

      <div className="min-h-0 flex-1">
        {isFetching && rows.length === 0 ? (
          <div className="flex h-full w-full items-center justify-center">
            <Loading />
          </div>
        ) : (
          <TableComponent
            key={`messages-page-${page}-${pageSize}`}
            onDelete={() => deleteMessages({ ids: selectedRows })}
            readOnlyEdit
            editable={[
              {
                field: "text",
                onUpdate: handleUpdateMessage,
                editableCell: false,
              },
            ]}
            overlayNoRowsTemplate={t("table.noRowsToShow")}
            onSelectionChanged={(event: SelectionChangedEvent) => {
              setSelectedRows(
                event.api
                  .getSelectedRows()
                  .map((row: MessagePageItem) => row.id),
              );
            }}
            rowSelection="multiple"
            suppressRowClickSelection
            pagination={false}
            columnDefs={columns}
            rowData={rows}
          />
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-3 text-sm">
        <div>
          {t("messages.pagination.summary", {
            defaultValue: `共 ${total} 条`,
            total,
          })}
          {isFetching ? (
            <span className="ml-2 text-muted-foreground">
              {t("common.loading", { defaultValue: "加载中…" })}
            </span>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          <label htmlFor="messages-page-size" className="text-muted-foreground">
            {t("messages.pagination.pageSize", { defaultValue: "每页" })}
          </label>
          <select
            id="messages-page-size"
            value={pageSize}
            onChange={(event) => {
              setPageSize(Number(event.target.value));
              setPage(1);
            }}
            className="h-8 rounded-md border bg-background px-2"
          >
            {PAGE_SIZE_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={page <= 1 || isFetching}
            onClick={() => setPage((current) => Math.max(1, current - 1))}
            className="h-8 rounded-md border px-3 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {t("messages.pagination.previous", { defaultValue: "上一页" })}
          </button>
          <span className="min-w-[6rem] text-center">
            {t("messages.pagination.page", {
              defaultValue: `第 ${page} / ${Math.max(totalPages, 1)} 页`,
              page,
              totalPages: Math.max(totalPages, 1),
            })}
          </span>
          <button
            type="button"
            disabled={page >= totalPages || totalPages === 0 || isFetching}
            onClick={() =>
              setPage((current) => Math.min(totalPages, current + 1))
            }
            className="h-8 rounded-md border px-3 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {t("messages.pagination.next", { defaultValue: "下一页" })}
          </button>
        </div>
      </div>
    </div>
  );
}
