import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import type {
  ChannelConnection,
  ChannelConnectionCreate,
  ChannelConnectionUpdate,
  ChannelConversationBinding,
  ChannelConversationBindingUpdate,
  ChannelConversationBindingUpsert,
  ChannelHealthResult,
  ChannelIdentity,
  ChannelMutationHook,
  TelegramWebhookConfigure,
  TelegramWebhookResult,
} from "./types";

const CONNECTIONS_QUERY_KEY = ["useGetChannelConnections"];
const CONVERSATIONS_QUERY_KEY = ["useGetChannelConversations"];

export const useCreateChannelConnection: ChannelMutationHook<
  ChannelConnectionCreate,
  ChannelConnection
> = (options) => {
  const queryClient = useQueryClient();
  const userOnSettled = options?.onSettled;

  return useMutation<ChannelConnection, unknown, ChannelConnectionCreate>({
    mutationKey: ["useCreateChannelConnection"],
    mutationFn: async (payload) => {
      const response = await api.post<ChannelConnection>(
        `${getURL("CHANNELS")}/`,
        payload,
      );
      return response.data;
    },
    ...options,
    onSettled: async (...args) => {
      await queryClient.invalidateQueries({ queryKey: CONNECTIONS_QUERY_KEY });
      await userOnSettled?.(...args);
    },
  });
};

export const useUpdateChannelConnection: ChannelMutationHook<
  { connectionId: string; payload: ChannelConnectionUpdate },
  ChannelConnection
> = (options) => {
  const queryClient = useQueryClient();
  const userOnSettled = options?.onSettled;

  return useMutation<
    ChannelConnection,
    unknown,
    { connectionId: string; payload: ChannelConnectionUpdate }
  >({
    mutationKey: ["useUpdateChannelConnection"],
    mutationFn: async ({ connectionId, payload }) => {
      const response = await api.patch<ChannelConnection>(
        `${getURL("CHANNELS")}/${connectionId}`,
        payload,
      );
      return response.data;
    },
    ...options,
    onSettled: async (...args) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: CONNECTIONS_QUERY_KEY }),
        queryClient.invalidateQueries({ queryKey: CONVERSATIONS_QUERY_KEY }),
      ]);
      await userOnSettled?.(...args);
    },
  });
};

export const useDeleteChannelConnection: ChannelMutationHook<
  { connectionId: string },
  boolean
> = (options) => {
  const queryClient = useQueryClient();
  const userOnSettled = options?.onSettled;

  return useMutation<boolean, unknown, { connectionId: string }>({
    mutationKey: ["useDeleteChannelConnection"],
    mutationFn: async ({ connectionId }) => {
      await api.delete(`${getURL("CHANNELS")}/${connectionId}`);
      return true;
    },
    ...options,
    onSettled: async (...args) => {
      await queryClient.invalidateQueries({ queryKey: CONNECTIONS_QUERY_KEY });
      await userOnSettled?.(...args);
    },
  });
};

export const useTestChannelConnection: ChannelMutationHook<
  { connectionId: string },
  ChannelHealthResult
> = (options) => {
  const queryClient = useQueryClient();
  const userOnSettled = options?.onSettled;

  return useMutation<ChannelHealthResult, unknown, { connectionId: string }>({
    mutationKey: ["useTestChannelConnection"],
    mutationFn: async ({ connectionId }) => {
      const response = await api.post<ChannelHealthResult>(
        `${getURL("CHANNELS")}/${connectionId}/test`,
      );
      return response.data;
    },
    ...options,
    onSettled: async (...args) => {
      await queryClient.invalidateQueries({ queryKey: CONNECTIONS_QUERY_KEY });
      await userOnSettled?.(...args);
    },
  });
};

export const useConfigureTelegramWebhook: ChannelMutationHook<
  { connectionId: string; payload: TelegramWebhookConfigure },
  TelegramWebhookResult
> = (options) => {
  const queryClient = useQueryClient();
  const userOnSettled = options?.onSettled;

  return useMutation<
    TelegramWebhookResult,
    unknown,
    { connectionId: string; payload: TelegramWebhookConfigure }
  >({
    mutationKey: ["useConfigureTelegramWebhook"],
    mutationFn: async ({ connectionId, payload }) => {
      const response = await api.post<TelegramWebhookResult>(
        `${getURL("CHANNELS")}/${connectionId}/telegram/webhook`,
        payload,
      );
      return response.data;
    },
    ...options,
    onSettled: async (...args) => {
      await queryClient.invalidateQueries({ queryKey: CONNECTIONS_QUERY_KEY });
      await userOnSettled?.(...args);
    },
  });
};

export const useRedeemChannelBindingCode: ChannelMutationHook<
  { code: string },
  ChannelIdentity
> = (options) => {
  const queryClient = useQueryClient();
  const userOnSettled = options?.onSettled;

  return useMutation<ChannelIdentity, unknown, { code: string }>({
    mutationKey: ["useRedeemChannelBindingCode"],
    mutationFn: async ({ code }) => {
      const response = await api.post<ChannelIdentity>(
        `${getURL("CHANNEL_BINDINGS")}/redeem`,
        { code },
      );
      return response.data;
    },
    ...options,
    onSettled: async (...args) => {
      await queryClient.invalidateQueries({
        queryKey: ["useGetChannelIdentities"],
      });
      await userOnSettled?.(...args);
    },
  });
};

export const useDeleteChannelIdentity: ChannelMutationHook<
  { connectionId: string; identityId: string },
  boolean
> = (options) => {
  const queryClient = useQueryClient();
  const userOnSettled = options?.onSettled;

  return useMutation<
    boolean,
    unknown,
    { connectionId: string; identityId: string }
  >({
    mutationKey: ["useDeleteChannelIdentity"],
    mutationFn: async ({ connectionId, identityId }) => {
      await api.delete(
        `${getURL("CHANNELS")}/${connectionId}/identities/${identityId}`,
      );
      return true;
    },
    ...options,
    onSettled: async (...args) => {
      const variables = args[2];
      await queryClient.invalidateQueries({
        queryKey: ["useGetChannelIdentities", variables.connectionId],
      });
      await userOnSettled?.(...args);
    },
  });
};

export const useUpsertChannelConversation: ChannelMutationHook<
  { connectionId: string; payload: ChannelConversationBindingUpsert },
  ChannelConversationBinding
> = (options) => {
  const queryClient = useQueryClient();
  const userOnSettled = options?.onSettled;

  return useMutation<
    ChannelConversationBinding,
    unknown,
    { connectionId: string; payload: ChannelConversationBindingUpsert }
  >({
    mutationKey: ["useUpsertChannelConversation"],
    mutationFn: async ({ connectionId, payload }) => {
      const response = await api.put<ChannelConversationBinding>(
        `${getURL("CHANNELS")}/${connectionId}/conversations`,
        payload,
      );
      return response.data;
    },
    ...options,
    onSettled: async (...args) => {
      await queryClient.invalidateQueries({ queryKey: CONVERSATIONS_QUERY_KEY });
      await userOnSettled?.(...args);
    },
  });
};

export const useUpdateChannelConversation: ChannelMutationHook<
  {
    connectionId: string;
    bindingId: string;
    payload: ChannelConversationBindingUpdate;
  },
  ChannelConversationBinding
> = (options) => {
  const queryClient = useQueryClient();
  const userOnSettled = options?.onSettled;

  return useMutation<
    ChannelConversationBinding,
    unknown,
    {
      connectionId: string;
      bindingId: string;
      payload: ChannelConversationBindingUpdate;
    }
  >({
    mutationKey: ["useUpdateChannelConversation"],
    mutationFn: async ({ connectionId, bindingId, payload }) => {
      const response = await api.patch<ChannelConversationBinding>(
        `${getURL("CHANNELS")}/${connectionId}/conversations/${bindingId}`,
        payload,
      );
      return response.data;
    },
    ...options,
    onSettled: async (...args) => {
      await queryClient.invalidateQueries({ queryKey: CONVERSATIONS_QUERY_KEY });
      await userOnSettled?.(...args);
    },
  });
};
