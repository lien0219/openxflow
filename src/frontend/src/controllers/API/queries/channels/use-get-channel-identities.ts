import type { UseQueryResult } from "@tanstack/react-query";
import type { useQueryFunctionType } from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";
import type { ChannelIdentity } from "./types";

interface ChannelIdentityParams {
  connectionId: string;
}

export const useGetChannelIdentities: useQueryFunctionType<
  ChannelIdentityParams,
  ChannelIdentity[]
> = (params, options) => {
  const { query } = UseRequestProcessor();

  const getIdentities = async (): Promise<ChannelIdentity[]> => {
    const response = await api.get<ChannelIdentity[]>(
      `${getURL("CHANNELS")}/${params.connectionId}/identities`,
    );
    return response.data;
  };

  return query(
    ["useGetChannelIdentities", params.connectionId],
    getIdentities,
    {
      enabled: Boolean(params.connectionId),
      refetchOnWindowFocus: false,
      ...options,
    },
  ) as UseQueryResult<ChannelIdentity[], Error>;
};
