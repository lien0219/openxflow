import type { UseQueryResult } from "@tanstack/react-query";
import type { useQueryFunctionType } from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";
import type { ChannelProviderCapabilitiesMap } from "./types";

export const useGetChannelProviderCapabilities: useQueryFunctionType<
  Record<string, never>,
  ChannelProviderCapabilitiesMap
> = (_params, options) => {
  const { query } = UseRequestProcessor();

  const getCapabilities = async (): Promise<ChannelProviderCapabilitiesMap> => {
    const response = await api.get<ChannelProviderCapabilitiesMap>(
      `${getURL("CHANNELS")}/providers/capabilities`,
    );
    return response.data;
  };

  return query(
    ["useGetChannelProviderCapabilities"],
    getCapabilities,
    {
      refetchOnWindowFocus: false,
      staleTime: 5 * 60 * 1000,
      ...options,
    },
  ) as UseQueryResult<ChannelProviderCapabilitiesMap, Error>;
};
