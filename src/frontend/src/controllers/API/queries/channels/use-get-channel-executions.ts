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
          status: params.status || undefined,
          trigger_type: params.triggerType || undefined,
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
      params.status ?? "",
      params.triggerType ?? "",
    ],
    getExecutions,
    {
      enabled: Boolean(params.connectionId),
      refetchOnWindowFocus: false,
      ...options,
    },
  ) as UseQueryResult<ChannelExecutionLogPage, Error>;
};
