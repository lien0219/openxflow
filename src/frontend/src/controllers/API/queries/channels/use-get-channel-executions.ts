import type { UseQueryResult } from "@tanstack/react-query";
import type { useQueryFunctionType } from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";
import type { ChannelExecutionLogPage, ChannelExecutionQuery } from "./types";

export const useGetChannelExecutions: useQueryFunctionType<
  ChannelExecutionQuery,
  ChannelExecutionLogPage
> = (params, options) => {
  const { query } = UseRequestProcessor();

  const getExecutions = async (): Promise<ChannelExecutionLogPage> => {
    const response = await api.get<ChannelExecutionLogPage>(
      `${getURL("CHANNELS")}/${params.connectionId}/executions`,
      {
        params: {
          page: params.page ?? 1,
          page_size: params.pageSize ?? 20,
          conversation_binding_id: params.conversationBindingId || undefined,
          openxflow_user_id: params.openxflowUserId || undefined,
          external_user_id: params.externalUserId || undefined,
          session_id: params.sessionId || undefined,
          execution_identity_type: params.executionIdentityType || undefined,
          flow_id: params.flowId || undefined,
          error_code: params.errorCode || undefined,
          query: params.query || undefined,
          status: params.status || undefined,
          trigger_type: params.triggerType || undefined,
          created_from: params.createdFrom || undefined,
          created_to: params.createdTo || undefined,
        },
      },
    );
    return response.data;
  };

  return query(
    [
      "useGetChannelExecutions",
      params.connectionId,
      params.page ?? 1,
      params.pageSize ?? 20,
      params.conversationBindingId ?? "",
      params.openxflowUserId ?? "",
      params.externalUserId ?? "",
      params.sessionId ?? "",
      params.executionIdentityType ?? "",
      params.flowId ?? "",
      params.errorCode ?? "",
      params.query ?? "",
      params.status ?? "",
      params.triggerType ?? "",
      params.createdFrom ?? "",
      params.createdTo ?? "",
    ],
    getExecutions,
    {
      enabled: Boolean(params.connectionId),
      refetchInterval: 15_000,
      refetchOnWindowFocus: false,
      ...options,
    },
  ) as UseQueryResult<ChannelExecutionLogPage, Error>;
};
