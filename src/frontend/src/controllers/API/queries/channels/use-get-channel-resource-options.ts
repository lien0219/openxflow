import type { UseQueryResult } from "@tanstack/react-query";
import type { useQueryFunctionType } from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";
import type {
  ChannelFlowOptionPage,
  ChannelKnowledgeBaseOptionPage,
  ChannelResourceQuery,
} from "./resource-types";

export const useGetChannelFlowOptions: useQueryFunctionType<
  ChannelResourceQuery,
  ChannelFlowOptionPage
> = (params, options) => {
  const { query } = UseRequestProcessor();

  const getOptions = async (): Promise<ChannelFlowOptionPage> => {
    const response = await api.get<ChannelFlowOptionPage>(
      `${getURL("CHANNELS")}/resources/flows`,
      {
        params: {
          page: params.page ?? 1,
          page_size: params.pageSize ?? 20,
          query: params.query || undefined,
        },
      },
    );
    return response.data;
  };

  return query(
    [
      "useGetChannelFlowOptions",
      params.page ?? 1,
      params.pageSize ?? 20,
      params.query ?? "",
    ],
    getOptions,
    { refetchOnWindowFocus: false, ...options },
  ) as UseQueryResult<ChannelFlowOptionPage, Error>;
};

export const useGetChannelKnowledgeBaseOptions: useQueryFunctionType<
  ChannelResourceQuery,
  ChannelKnowledgeBaseOptionPage
> = (params, options) => {
  const { query } = UseRequestProcessor();

  const getOptions = async (): Promise<ChannelKnowledgeBaseOptionPage> => {
    const response = await api.get<ChannelKnowledgeBaseOptionPage>(
      `${getURL("CHANNELS")}/resources/knowledge-bases`,
      {
        params: {
          page: params.page ?? 1,
          page_size: params.pageSize ?? 20,
          query: params.query || undefined,
        },
      },
    );
    return response.data;
  };

  return query(
    [
      "useGetChannelKnowledgeBaseOptions",
      params.page ?? 1,
      params.pageSize ?? 20,
      params.query ?? "",
    ],
    getOptions,
    { refetchOnWindowFocus: false, ...options },
  ) as UseQueryResult<ChannelKnowledgeBaseOptionPage, Error>;
};
