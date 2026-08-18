import type { UseQueryResult } from "@tanstack/react-query";
import type { useQueryFunctionType } from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";
import type {
  ChannelDeliveryQuery,
  ChannelOutboundDeliveryPage,
} from "./types";

export const useGetChannelDeliveries: useQueryFunctionType<
  ChannelDeliveryQuery,
  ChannelOutboundDeliveryPage
> = (params, options) => {
  const { query } = UseRequestProcessor();

  const getDeliveries = async (): Promise<ChannelOutboundDeliveryPage> => {
    const response = await api.get<ChannelOutboundDeliveryPage>(
      `${getURL("CHANNELS")}/${params.connectionId}/deliveries`,
      {
        params: {
          page: params.page ?? 1,
          page_size: params.pageSize ?? 20,
          query: params.query || undefined,
          status: params.status || undefined,
          delivery_kind: params.deliveryKind || undefined,
          created_from: params.createdFrom || undefined,
          created_to: params.createdTo || undefined,
        },
      },
    );
    return response.data;
  };

  return query(
    [
      "useGetChannelDeliveries",
      params.connectionId,
      params.page ?? 1,
      params.pageSize ?? 20,
      params.query ?? "",
      params.status ?? "",
      params.deliveryKind ?? "",
      params.createdFrom ?? "",
      params.createdTo ?? "",
    ],
    getDeliveries,
    {
      enabled: Boolean(params.connectionId),
      refetchInterval: 15_000,
      refetchOnWindowFocus: false,
      ...options,
    },
  ) as UseQueryResult<ChannelOutboundDeliveryPage, Error>;
};
