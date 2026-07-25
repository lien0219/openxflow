import type { UseQueryResult } from "@tanstack/react-query";
import type { useQueryFunctionType } from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";
import type {
  ChannelConnectionOverview,
  ChannelOverviewQuery,
} from "./types";

export const useGetChannelOverview: useQueryFunctionType<
  ChannelOverviewQuery,
  ChannelConnectionOverview
> = (params, options) => {
  const { query } = UseRequestProcessor();

  const getOverview = async (): Promise<ChannelConnectionOverview> => {
    const response = await api.get<ChannelConnectionOverview>(
      `${getURL("CHANNELS")}/${params.connectionId}/overview`,
      {
        params: {
          window_hours: params.windowHours ?? 24,
        },
      },
    );
    return response.data;
  };

  return query(
    [
      "useGetChannelOverview",
      params.connectionId,
      params.windowHours ?? 24,
    ],
    getOverview,
    {
      enabled: Boolean(params.connectionId),
      refetchInterval: 30_000,
      refetchOnWindowFocus: false,
      ...options,
    },
  ) as UseQueryResult<ChannelConnectionOverview, Error>;
};
