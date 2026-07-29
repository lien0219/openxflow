import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import type { ChannelMutationHook } from "./types";

const FLOW_SELECTIONS_QUERY_KEY = ["useGetChannelFlowSelections"];

export const useDeleteChannelFlowSelection: ChannelMutationHook<
  { connectionId: string; selectionId: string },
  boolean
> = (options) => {
  const queryClient = useQueryClient();
  const userOnSettled = options?.onSettled;

  return useMutation<
    boolean,
    unknown,
    { connectionId: string; selectionId: string }
  >({
    mutationKey: ["useDeleteChannelFlowSelection"],
    mutationFn: async ({ connectionId, selectionId }) => {
      await api.delete(
        `${getURL("CHANNELS")}/${connectionId}/flow-selections/${selectionId}`,
      );
      return true;
    },
    ...options,
    onSettled: async (...args) => {
      await queryClient.invalidateQueries({ queryKey: FLOW_SELECTIONS_QUERY_KEY });
      await userOnSettled?.(...args);
    },
  });
};

export const useCleanupChannelFlowSelections: ChannelMutationHook<
  { connectionId: string },
  { removed: number }
> = (options) => {
  const queryClient = useQueryClient();
  const userOnSettled = options?.onSettled;

  return useMutation<
    { removed: number },
    unknown,
    { connectionId: string }
  >({
    mutationKey: ["useCleanupChannelFlowSelections"],
    mutationFn: async ({ connectionId }) => {
      const response = await api.post<{ removed: number }>(
        `${getURL("CHANNELS")}/${connectionId}/flow-selections/cleanup`,
      );
      return response.data;
    },
    ...options,
    onSettled: async (...args) => {
      await queryClient.invalidateQueries({ queryKey: FLOW_SELECTIONS_QUERY_KEY });
      await userOnSettled?.(...args);
    },
  });
};
