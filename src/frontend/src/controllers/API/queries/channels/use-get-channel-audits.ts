import type { UseQueryResult } from "@tanstack/react-query";
import type { useQueryFunctionType } from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";
import type { ChannelAuditQuery, ChannelConfigurationAuditPage } from "./types";

export const useGetChannelAudits: useQueryFunctionType<
  ChannelAuditQuery,
  ChannelConfigurationAuditPage
> = (params, options) => {
  const { query } = UseRequestProcessor();

  const getAudits = async (): Promise<ChannelConfigurationAuditPage> => {
    const response = await api.get<ChannelConfigurationAuditPage>(
      `${getURL("CHANNELS")}/${params.connectionId}/audits`,
      {
        params: {
          page: params.page ?? 1,
          page_size: params.pageSize ?? 20,
          action: params.action || undefined,
          resource_type: params.resourceType || undefined,
          actor_user_id: params.actorUserId || undefined,
          created_from: params.createdFrom || undefined,
          created_to: params.createdTo || undefined,
        },
      },
    );
    return response.data;
  };

  return query(
    [
      "useGetChannelAudits",
      params.connectionId,
      params.page ?? 1,
      params.pageSize ?? 20,
      params.action ?? "",
      params.resourceType ?? "",
      params.actorUserId ?? "",
      params.createdFrom ?? "",
      params.createdTo ?? "",
    ],
    getAudits,
    {
      enabled: Boolean(params.connectionId),
      refetchOnWindowFocus: false,
      ...options,
    },
  ) as UseQueryResult<ChannelConfigurationAuditPage, Error>;
};
