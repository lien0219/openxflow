import type { UseQueryResult } from "@tanstack/react-query";
import type { useQueryFunctionType } from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";

export interface ChannelActiveWorkflowSelection {
  id: string;
  connection_id: string;
  conversation_binding_id: string;
  channel_identity_id: string;
  conversation_scope_id: string;
  workflow_command_id: string;
  selected_at: string;
  last_used_at: string | null;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
  identity_display_name: string | null;
  external_user_id: string | null;
  conversation_display_name: string | null;
  external_conversation_id: string | null;
  conversation_type: string | null;
  command: string | null;
  flow_id: string | null;
  flow_name: string | null;
  flow_endpoint_name: string | null;
  execution_identity_type: "service" | "bound_user" | null;
}

export interface ChannelActiveWorkflowSelectionPage {
  items: ChannelActiveWorkflowSelection[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface ChannelActiveWorkflowSelectionQuery {
  connectionId: string;
  page?: number;
  pageSize?: number;
  query?: string;
  conversationBindingId?: string;
  channelIdentityId?: string;
  workflowCommandId?: string;
}

export const useGetChannelFlowSelections: useQueryFunctionType<
  ChannelActiveWorkflowSelectionQuery,
  ChannelActiveWorkflowSelectionPage
> = (params, options) => {
  const { query } = UseRequestProcessor();

  const getSelections =
    async (): Promise<ChannelActiveWorkflowSelectionPage> => {
      const response = await api.get<ChannelActiveWorkflowSelectionPage>(
        `${getURL("CHANNELS")}/${params.connectionId}/flow-selections`,
        {
          params: {
            page: params.page ?? 1,
            page_size: params.pageSize ?? 20,
            query: params.query || undefined,
            conversation_binding_id: params.conversationBindingId || undefined,
            channel_identity_id: params.channelIdentityId || undefined,
            workflow_command_id: params.workflowCommandId || undefined,
          },
        },
      );
      return response.data;
    };

  return query(
    [
      "useGetChannelFlowSelections",
      params.connectionId,
      params.page ?? 1,
      params.pageSize ?? 20,
      params.query ?? "",
      params.conversationBindingId ?? "",
      params.channelIdentityId ?? "",
      params.workflowCommandId ?? "",
    ],
    getSelections,
    {
      enabled: Boolean(params.connectionId),
      refetchOnWindowFocus: false,
      ...options,
    },
  ) as UseQueryResult<ChannelActiveWorkflowSelectionPage, Error>;
};
