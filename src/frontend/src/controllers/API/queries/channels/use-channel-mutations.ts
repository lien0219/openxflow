import type { useMutationFunctionType } from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";
import type {
  ChannelConnection,
  ChannelConnectionCreate,
  ChannelConnectionUpdate,
  ChannelConversationBinding,
  ChannelConversationBindingUpsert,
  ChannelHealthResult,
  ChannelIdentity,
  TelegramWebhookConfigure,
  TelegramWebhookResult,
} from "./types";

const CONNECTIONS_QUERY_KEY = ["useGetChannelConnections"];

export const useCreateChannelConnection: useMutationFunctionType<
  undefined,
  ChannelConnectionCreate,
  ChannelConnection
> = (options) => {
  const { mutate, queryClient } = UseRequestProcessor();
  const userOnSettled = options?.onSettled;
  return mutate(
    ["useCreateChannelConnection"],
    async (payload: ChannelConnectionCreate) => {
      const response = await api.post<ChannelConnection>(
        `${getURL("CHANNELS")}/`,
        payload,
      );
      return response.data;
    },
    {
      ...options,
      onSettled: async (data, error, variables, context) => {
        await queryClient.invalidateQueries({
          queryKey: CONNECTIONS_QUERY_KEY,
        });
        await userOnSettled?.(data, error, variables, context);
      },
    },
  );
};

export const useUpdateChannelConnection: useMutationFunctionType<
  undefined,
  { connectionId: string; payload: ChannelConnectionUpdate },
  ChannelConnection
> = (options) => {
  const { mutate, queryClient } = UseRequestProcessor();
  const userOnSettled = options?.onSettled;
  return mutate(
    ["useUpdateChannelConnection"],
    async ({ connectionId, payload }) => {
      const response = await api.patch<ChannelConnection>(
        `${getURL("CHANNELS")}/${connectionId}`,
        payload,
      );
      return response.data;
    },
    {
      ...options,
      onSettled: async (data, error, variables, context) => {
        await queryClient.invalidateQueries({
          queryKey: CONNECTIONS_QUERY_KEY,
        });
        await userOnSettled?.(data, error, variables, context);
      },
    },
  );
};

export const useDeleteChannelConnection: useMutationFunctionType<
  undefined,
  { connectionId: string },
  boolean
> = (options) => {
  const { mutate, queryClient } = UseRequestProcessor();
  const userOnSettled = options?.onSettled;
  return mutate(
    ["useDeleteChannelConnection"],
    async ({ connectionId }) => {
      await api.delete(`${getURL("CHANNELS")}/${connectionId}`);
      return true;
    },
    {
      ...options,
      onSettled: async (data, error, variables, context) => {
        await queryClient.invalidateQueries({
          queryKey: CONNECTIONS_QUERY_KEY,
        });
        await userOnSettled?.(data, error, variables, context);
      },
    },
  );
};

export const useTestChannelConnection: useMutationFunctionType<
  undefined,
  { connectionId: string },
  ChannelHealthResult
> = (options) => {
  const { mutate, queryClient } = UseRequestProcessor();
  const userOnSettled = options?.onSettled;
  return mutate(
    ["useTestChannelConnection"],
    async ({ connectionId }) => {
      const response = await api.post<ChannelHealthResult>(
        `${getURL("CHANNELS")}/${connectionId}/test`,
      );
      return response.data;
    },
    {
      ...options,
      onSettled: async (data, error, variables, context) => {
        await queryClient.invalidateQueries({
          queryKey: CONNECTIONS_QUERY_KEY,
        });
        await userOnSettled?.(data, error, variables, context);
      },
    },
  );
};

export const useConfigureTelegramWebhook: useMutationFunctionType<
  undefined,
  { connectionId: string; payload: TelegramWebhookConfigure },
  TelegramWebhookResult
> = (options) => {
  const { mutate, queryClient } = UseRequestProcessor();
  const userOnSettled = options?.onSettled;
  return mutate(
    ["useConfigureTelegramWebhook"],
    async ({ connectionId, payload }) => {
      const response = await api.post<TelegramWebhookResult>(
        `${getURL("CHANNELS")}/${connectionId}/telegram/webhook`,
        payload,
      );
      return response.data;
    },
    {
      ...options,
      onSettled: async (data, error, variables, context) => {
        await queryClient.invalidateQueries({
          queryKey: CONNECTIONS_QUERY_KEY,
        });
        await userOnSettled?.(data, error, variables, context);
      },
    },
  );
};

export const useRedeemChannelBindingCode: useMutationFunctionType<
  undefined,
  { code: string },
  ChannelIdentity
> = (options) => {
  const { mutate, queryClient } = UseRequestProcessor();
  const userOnSettled = options?.onSettled;
  return mutate(
    ["useRedeemChannelBindingCode"],
    async ({ code }) => {
      const response = await api.post<ChannelIdentity>(
        `${getURL("CHANNEL_BINDINGS")}/redeem`,
        { code },
      );
      return response.data;
    },
    {
      ...options,
      onSettled: async (data, error, variables, context) => {
        await queryClient.invalidateQueries({
          queryKey: ["useGetChannelIdentities"],
        });
        await userOnSettled?.(data, error, variables, context);
      },
    },
  );
};

export const useDeleteChannelIdentity: useMutationFunctionType<
  undefined,
  { connectionId: string; identityId: string },
  boolean
> = (options) => {
  const { mutate, queryClient } = UseRequestProcessor();
  const userOnSettled = options?.onSettled;
  return mutate(
    ["useDeleteChannelIdentity"],
    async ({ connectionId, identityId }) => {
      await api.delete(
        `${getURL("CHANNELS")}/${connectionId}/identities/${identityId}`,
      );
      return true;
    },
    {
      ...options,
      onSettled: async (data, error, variables, context) => {
        if (variables?.connectionId) {
          await queryClient.invalidateQueries({
            queryKey: ["useGetChannelIdentities", variables.connectionId],
          });
        }
        await userOnSettled?.(data, error, variables, context);
      },
    },
  );
};

export const useUpsertChannelConversation: useMutationFunctionType<
  undefined,
  { connectionId: string; payload: ChannelConversationBindingUpsert },
  ChannelConversationBinding
> = (options) => {
  const { mutate, queryClient } = UseRequestProcessor();
  const userOnSettled = options?.onSettled;
  return mutate(
    ["useUpsertChannelConversation"],
    async ({ connectionId, payload }) => {
      const response = await api.put<ChannelConversationBinding>(
        `${getURL("CHANNELS")}/${connectionId}/conversations`,
        payload,
      );
      return response.data;
    },
    {
      ...options,
      onSettled: async (data, error, variables, context) => {
        if (variables?.connectionId) {
          await queryClient.invalidateQueries({
            queryKey: ["useGetChannelConversations", variables.connectionId],
          });
        }
        await userOnSettled?.(data, error, variables, context);
      },
    },
  );
};
