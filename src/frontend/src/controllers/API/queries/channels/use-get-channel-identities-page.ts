import type { UseQueryResult } from "@tanstack/react-query";
import type { useQueryFunctionType } from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";
import type {
  ChannelIdentityPage,
  ChannelIdentityPageQuery,
} from "./identity-types";

export const useGetChannelIdentitiesPage: useQueryFunctionType<
  ChannelIdentityPageQuery,
  ChannelIdentityPage
> = (params, options) => {
  const { query } = UseRequestProcessor();

  const getIdentities = async (): Promise<ChannelIdentityPage> => {
    const response = await api.get<ChannelIdentityPage>(
      `${getURL("CHANNELS")}/${params.connectionId}/identities/page`,
      {
        params: {
          page: params.page ?? 1,
          page_size: params.pageSize ?? 20,
          query: params.query || undefined,
          status: params.status || undefined,
        },
      },
    );
    return response.data;
  };

  return query(
    [
      "useGetChannelIdentitiesPage",
      params.connectionId,
      params.page ?? 1,
      params.pageSize ?? 20,
      params.query ?? "",
      params.status ?? "",
    ],
    getIdentities,
    {
      enabled: Boolean(params.connectionId),
      refetchOnWindowFocus: false,
      ...options,
    },
  ) as UseQueryResult<ChannelIdentityPage, Error>;
};
