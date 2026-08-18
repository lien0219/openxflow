import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import type {
  ChannelConversationBatchRequest,
  ChannelConversationBatchResponse,
} from "./admin-types";
import type { ChannelMutationHook } from "./types";

export const useBatchUpdateChannelConversations: ChannelMutationHook<
  { connectionId: string; payload: ChannelConversationBatchRequest },
  ChannelConversationBatchResponse
> = (options) => {
  const queryClient = useQueryClient();
  const userOnSettled = options?.onSettled;

  return useMutation<
    ChannelConversationBatchResponse,
    unknown,
    { connectionId: string; payload: ChannelConversationBatchRequest }
  >({
    mutationKey: ["useBatchUpdateChannelConversations"],
    mutationFn: async ({ connectionId, payload }) => {
      const response = await api.post<ChannelConversationBatchResponse>(
        `${getURL("CHANNELS")}/${connectionId}/conversations/batch`,
        payload,
      );
      return response.data;
    },
    ...options,
    onSettled: async (...args) => {
      await queryClient.invalidateQueries({
        queryKey: ["useGetChannelConversations"],
      });
      await userOnSettled?.(...args);
    },
  });
};
