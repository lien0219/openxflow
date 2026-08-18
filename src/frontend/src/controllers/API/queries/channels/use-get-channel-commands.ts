import type { UseQueryResult } from "@tanstack/react-query";
import type { useQueryFunctionType } from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";
import type { ChannelCommandQuery, ChannelWorkflowCommandPage } from "./types";

export const useGetChannelCommands: useQueryFunctionType<
  ChannelCommandQuery,
  ChannelWorkflowCommandPage
> = (params, options) => {
  const { query } = UseRequestProcessor();

  const getCommands = async (): Promise<ChannelWorkflowCommandPage> => {
    const response = await api.get<ChannelWorkflowCommandPage>(
      `${getURL("CHANNELS")}/${params.connectionId}/commands`,
      {
        params: {
          page: params.page ?? 1,
          page_size: params.pageSize ?? 20,
          query: params.query || undefined,
          scope_type: params.scopeType || undefined,
          enabled: params.enabled,
        },
      },
    );
    return response.data;
  };

  return query(
    [
      "useGetChannelCommands",
      params.connectionId,
      params.page ?? 1,
      params.pageSize ?? 20,
      params.query ?? "",
      params.scopeType ?? "",
      params.enabled ?? "all",
    ],
    getCommands,
    {
      enabled: Boolean(params.connectionId),
      refetchOnWindowFocus: false,
      ...options,
    },
  ) as UseQueryResult<ChannelWorkflowCommandPage, Error>;
};
