import type { UseQueryResult } from "@tanstack/react-query";
import type { useQueryFunctionType } from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";
import type { ChannelConnection } from "./types";

export const useGetChannelConnections: useQueryFunctionType<
  undefined,
  ChannelConnection[]
> = (options) => {
  const { query } = UseRequestProcessor();

  const getConnections = async (): Promise<ChannelConnection[]> => {
    const response = await api.get<ChannelConnection[]>(
      `${getURL("CHANNELS")}/`,
    );
    return response.data;
  };

  return query(["useGetChannelConnections"], getConnections, {
    refetchOnWindowFocus: false,
    ...options,
  }) as UseQueryResult<ChannelConnection[], Error>;
};
