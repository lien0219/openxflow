import { keepPreviousData } from "@tanstack/react-query";
import type { useQueryFunctionType } from "../../../../types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";

export interface MessagePageItem {
  id: string;
  timestamp?: string;
  text?: string;
  sender?: string;
  sender_name?: string;
  session_id?: string;
  flow_id?: string;
  files?: unknown[];
  [key: string]: unknown;
}

export interface MessagesPageResponse {
  items: MessagePageItem[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface MessagesPageParams {
  page: number;
  pageSize: number;
  query?: string;
  flowId?: string;
  sessionId?: string;
  sender?: string;
  senderName?: string;
}

export const useGetMessagesPageQuery: useQueryFunctionType<
  MessagesPageParams,
  MessagesPageResponse
> = (params, options) => {
  const { query } = UseRequestProcessor();

  const responseFn = async () => {
    const response = await api.get<MessagesPageResponse>(
      `${getURL("MESSAGES")}/page`,
      {
        params: {
          page: params.page,
          page_size: params.pageSize,
          query: params.query || undefined,
          flow_id: params.flowId || undefined,
          session_id: params.sessionId || undefined,
          sender: params.sender || undefined,
          sender_name: params.senderName || undefined,
          order_by: "-timestamp",
        },
      },
    );
    return response.data;
  };

  return query(
    [
      "useGetMessagesPageQuery",
      params.page,
      params.pageSize,
      params.query,
      params.flowId,
      params.sessionId,
      params.sender,
      params.senderName,
    ],
    responseFn,
    {
      placeholderData: keepPreviousData,
      ...options,
    },
  );
};
