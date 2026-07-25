import type { UseQueryResult } from "@tanstack/react-query";
import type { useQueryFunctionType } from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";
import type { ChannelMessageQuery, ChannelMessageRecordPage } from "./types";

export const useGetChannelMessages: useQueryFunctionType<
  ChannelMessageQuery,
  ChannelMessageRecordPage
> = (params, options) => {
  const { query } = UseRequestProcessor();

  const getMessages = async (): Promise<ChannelMessageRecordPage> => {
    const response = await api.get<ChannelMessageRecordPage>(
      `${getURL("CHANNELS")}/${params.connectionId}/messages`,
      {
        params: {
          page: params.page ?? 1,
          page_size: params.pageSize ?? 20,
          query: params.query || undefined,
          direction: params.direction || undefined,
          status: params.status || undefined,
          conversation_binding_id: params.conversationBindingId || undefined,
          external_conversation_id: params.externalConversationId || undefined,
          external_user_id: params.externalUserId || undefined,
          created_from: params.createdFrom || undefined,
          created_to: params.createdTo || undefined,
        },
      },
    );
    return response.data;
  };

  return query(
    [
      "useGetChannelMessages",
      params.connectionId,
      params.page ?? 1,
      params.pageSize ?? 20,
      params.query ?? "",
      params.direction ?? "",
      params.status ?? "",
      params.conversationBindingId ?? "",
      params.externalConversationId ?? "",
      params.externalUserId ?? "",
      params.createdFrom ?? "",
      params.createdTo ?? "",
    ],
    getMessages,
    {
      enabled: Boolean(params.connectionId),
      refetchInterval: 15_000,
      refetchOnWindowFocus: false,
      ...options,
    },
  ) as UseQueryResult<ChannelMessageRecordPage, Error>;
};
