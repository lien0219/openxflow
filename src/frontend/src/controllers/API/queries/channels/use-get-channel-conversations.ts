import type { UseQueryResult } from "@tanstack/react-query";
import type { useQueryFunctionType } from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";
import type {
  ChannelConversationBindingPage,
  ChannelConversationQuery,
} from "./types";

export const useGetChannelConversations: useQueryFunctionType<
  ChannelConversationQuery,
  ChannelConversationBindingPage
> = (params, options) => {
  const { query } = UseRequestProcessor();

  const getConversations = async (): Promise<ChannelConversationBindingPage> => {
    const response = await api.get<ChannelConversationBindingPage>(
      `${getURL("CHANNELS")}/${params.connectionId}/conversations`,
      {
        params: {
          page: params.page ?? 1,
          page_size: params.pageSize ?? 20,
          query: params.query || undefined,
          conversation_type: params.conversationType || undefined,
          status: params.status || undefined,
          route_mode: params.routeMode || undefined,
          sort: params.sort ?? "-last_message_at",
        },
      },
    );
    return response.data;
  };

  return query(
    [
      "useGetChannelConversations",
      params.connectionId,
      params.page ?? 1,
      params.pageSize ?? 20,
      params.query ?? "",
      params.conversationType ?? "",
      params.status ?? "",
      params.routeMode ?? "",
      params.sort ?? "-last_message_at",
    ],
    getConversations,
    {
      enabled: Boolean(params.connectionId),
      refetchOnWindowFocus: false,
      ...options,
    },
  ) as UseQueryResult<ChannelConversationBindingPage, Error>;
};
