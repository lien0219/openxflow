import type { UseQueryResult } from "@tanstack/react-query";
import type { useQueryFunctionType } from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";
import type { ChannelConversationBinding } from "./types";

interface ChannelConversationParams {
  connectionId: string;
}

export const useGetChannelConversations: useQueryFunctionType<
  ChannelConversationParams,
  ChannelConversationBinding[]
> = (params, options) => {
  const { query } = UseRequestProcessor();

  const getConversations = async (): Promise<ChannelConversationBinding[]> => {
    const response = await api.get<ChannelConversationBinding[]>(
      `${getURL("CHANNELS")}/${params.connectionId}/conversations`,
    );
    return response.data;
  };

  return query(
    ["useGetChannelConversations", params.connectionId],
    getConversations,
    {
      enabled: Boolean(params.connectionId),
      refetchOnWindowFocus: false,
      ...options,
    },
  ) as UseQueryResult<ChannelConversationBinding[], Error>;
};
