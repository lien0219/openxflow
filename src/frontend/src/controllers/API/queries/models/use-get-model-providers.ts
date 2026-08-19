import { useQueryFunctionType } from "@/types/api";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";

export interface ModelProviderInfo {
  provider: string;
  models: Array<{
    model_name: string;
    metadata: Record<string, unknown>;
  }>;
  is_enabled: boolean;
  is_configured?: boolean;
  api_docs_url?: string;
  icon?: string;
  display_name_key?: string;
}

export interface ModelProviderWithStatus extends ModelProviderInfo {
  icon?: string;
}

export interface GetModelProvidersParams {
  includeDeprecated?: boolean;
  includeUnsupported?: boolean;
}

export const normalizeModelProviderStatus = (
  providerInfo: ModelProviderInfo,
): ModelProviderWithStatus => ({
  ...providerInfo,
  // A configured provider is available to catalog consumers even when the
  // user has not explicitly toggled an individual model yet. Keeping these
  // states separate on the backend is useful for model-management screens,
  // but treating only `is_enabled` as availability caused knowledge-base
  // embedding pickers to hide valid configured providers.
  is_enabled: providerInfo.is_enabled || providerInfo.is_configured === true,
  icon: providerInfo.icon || getProviderIcon(providerInfo.provider),
});
export const getModelProvidersQueryOptions = (
  params?: GetModelProvidersParams,
) => {
  const queryParams = new URLSearchParams();
  if (params?.includeDeprecated) {
    queryParams.append("include_deprecated", "true");
  }
  if (params?.includeUnsupported) {
    queryParams.append("include_unsupported", "true");
  }

  const url = `${getURL("MODELS")}${
    queryParams.toString() ? `?${queryParams.toString()}` : ""
  }`;

  return {
    queryKey: [
      "useGetModelProviders",
      params?.includeDeprecated,
      params?.includeUnsupported,
    ] as const,
    queryFn: async (): Promise<ModelProviderWithStatus[]> => {
      const response = await api.get<ModelProviderInfo[]>(url);
      return response.data.map(normalizeModelProviderStatus);
    },
    refetchOnWindowFocus: false,
    staleTime: 1000 * 60 * 5,
  };
};

export const useGetModelProviders: useQueryFunctionType<
  GetModelProvidersParams | undefined,
  ModelProviderWithStatus[]
> = (params, options) => {
  const { query } = UseRequestProcessor();
  const { queryKey, queryFn, refetchOnWindowFocus, staleTime } =
    getModelProvidersQueryOptions(params);

  const queryResult = query(queryKey, queryFn, {
    refetchOnWindowFocus,
    staleTime,
    ...options,
  });

  return queryResult;
};

// Helper function to map provider names to icon names when the API omits icon.
const getProviderIcon = (providerName: string): string => {
  const iconMap: Record<string, string> = {
    OpenAI: "OpenAI",
    Anthropic: "Anthropic",
    "Google Generative AI": "GoogleGenerativeAI",
    Groq: "Groq",
    "Amazon Bedrock": "Bedrock",
    NVIDIA: "NVIDIA",
    Cohere: "Cohere",
    // Both Azure providers share the Azure brand icon asset (there is no
    // AzureOpenAI icon module in the frontend icon registry).
    "Azure OpenAI": "Azure",
    "Azure AI Foundry": "Azure",
    SambaNova: "SambaNova",
    Ollama: "Ollama",
    "IBM WatsonX": "IBM",
    "IBM watsonx.ai": "IBM",
    OpenRouter: "OpenRouter",
    "OpenAI Compatible": "Plug",
  };

  return iconMap[providerName] || "Bot";
};
