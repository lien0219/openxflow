import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import type {
  ChannelMutationHook,
  ChannelRetryDeliveryResult,
} from "./types";

export const useRetryChannelDelivery: ChannelMutationHook<
  { connectionId: string; deliveryId: string },
  ChannelRetryDeliveryResult
> = (options) => {
  const queryClient = useQueryClient();
  const userOnSettled = options?.onSettled;

  return useMutation<
    ChannelRetryDeliveryResult,
    unknown,
    { connectionId: string; deliveryId: string }
  >({
    mutationKey: ["useRetryChannelDelivery"],
    mutationFn: async ({ connectionId, deliveryId }) => {
      const response = await api.post<ChannelRetryDeliveryResult>(
        `${getURL("CHANNELS")}/${connectionId}/deliveries/${deliveryId}/retry`,
      );
      return response.data;
    },
    ...options,
    onSettled: async (...args) => {
      const variables = args[2];
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: ["useGetChannelDeliveries", variables.connectionId],
        }),
        queryClient.invalidateQueries({
          queryKey: ["useGetChannelOverview", variables.connectionId],
        }),
        queryClient.invalidateQueries({
          queryKey: ["useGetChannelExecutions", variables.connectionId],
        }),
        queryClient.invalidateQueries({
          queryKey: ["useGetChannelMessages", variables.connectionId],
        }),
        queryClient.invalidateQueries({
          queryKey: ["useGetChannelAudits", variables.connectionId],
        }),
      ]);
      await userOnSettled?.(...args);
    },
  });
};
