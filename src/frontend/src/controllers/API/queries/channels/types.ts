import type {
  UseMutationOptions,
  UseMutationResult,
} from "@tanstack/react-query";

export type ChannelType = "telegram" | "feishu" | "dingtalk" | "wecom" | "mock";
export type ChannelConversationRouteMode = "inherit" | "override" | "disabled";
export type ChannelConversationStatus =
  | "pending"
  | "inherited"
  | "overridden"
  | "ignored"
  | "disabled"
  | "unavailable";
export type ChannelConversationSource = "auto_discovered" | "legacy_manual";
export type ChannelUnconfiguredBehavior =
  | "use_global_default"
  | "notify_pending"
  | "ignore";

export type ChannelMutationHook<Variables, Data, Error = unknown> = (
  options?: Omit<
    UseMutationOptions<Data, Error, Variables>,
    "mutationFn" | "mutationKey"
  >,
) => UseMutationResult<Data, Error, Variables>;

export interface ChannelConnection {
  id: string;
  user_id: string;
  name: string;
  channel_type: ChannelType;
  enabled: boolean;
  connection_mode: string;
  default_flow_id: string | null;
  default_knowledge_base_id: string | null;
  auto_discover_conversations: boolean;
  unconfigured_behavior: ChannelUnconfiguredBehavior;
  pending_notice_enabled: boolean;
  personal_commands_enabled: boolean;
  default_response_mode: string;
  default_allow_file_upload: boolean;
  settings_data: Record<string, unknown>;
  status: string;
  configured_credential_keys: string[];
  last_connected_at: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChannelConnectionCreate {
  name: string;
  channel_type: ChannelType;
  enabled: boolean;
  connection_mode: string;
  default_flow_id?: string | null;
  default_knowledge_base_id?: string | null;
  auto_discover_conversations?: boolean;
  unconfigured_behavior?: ChannelUnconfiguredBehavior;
  pending_notice_enabled?: boolean;
  personal_commands_enabled?: boolean;
  default_response_mode?: string;
  default_allow_file_upload?: boolean;
  settings_data: Record<string, unknown>;
  credentials: Record<string, string>;
}

export interface ChannelConnectionUpdate {
  name?: string;
  enabled?: boolean;
  connection_mode?: string;
  default_flow_id?: string | null;
  default_knowledge_base_id?: string | null;
  auto_discover_conversations?: boolean;
  unconfigured_behavior?: ChannelUnconfiguredBehavior;
  pending_notice_enabled?: boolean;
  personal_commands_enabled?: boolean;
  default_response_mode?: string;
  default_allow_file_upload?: boolean;
  settings_data?: Record<string, unknown>;
  credentials?: Record<string, string>;
}

export interface ChannelIdentity {
  id: string;
  connection_id: string;
  openxflow_user_id: string;
  external_user_id: string;
  external_tenant_id: string;
  external_union_id: string | null;
  display_name: string | null;
  status: string;
  profile_data: Record<string, unknown>;
  bound_at: string;
  updated_at: string;
}

export interface ChannelConversationBinding {
  id: string;
  connection_id: string;
  external_conversation_id: string;
  conversation_type: string;
  display_name: string | null;
  response_mode: string;
  allow_file_upload: boolean;
  route_mode: ChannelConversationRouteMode;
  status: ChannelConversationStatus;
  source: ChannelConversationSource;
  settings_data: Record<string, unknown>;
  provider_metadata: Record<string, unknown>;
  default_flow_id: string | null;
  knowledge_base_id: string | null;
  first_seen_at: string;
  last_seen_at: string;
  last_message_at: string;
  pending_notice_sent_at: string | null;
  ignored_at: string | null;
  disabled_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChannelConversationBindingPage {
  items: ChannelConversationBinding[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface ChannelConversationBindingUpsert {
  external_conversation_id: string;
  conversation_type: string;
  display_name?: string | null;
  response_mode: string;
  allow_file_upload: boolean;
  route_mode?: ChannelConversationRouteMode;
  status?: ChannelConversationStatus;
  source?: ChannelConversationSource;
  settings_data: Record<string, unknown>;
  provider_metadata?: Record<string, unknown>;
  default_flow_id?: string | null;
  knowledge_base_id?: string | null;
}

export interface ChannelConversationBindingUpdate {
  display_name?: string | null;
  response_mode?: string;
  allow_file_upload?: boolean;
  route_mode?: ChannelConversationRouteMode;
  status?: ChannelConversationStatus;
  settings_data?: Record<string, unknown>;
  default_flow_id?: string | null;
  knowledge_base_id?: string | null;
}

export interface ChannelConversationQuery {
  connectionId: string;
  page?: number;
  pageSize?: number;
  query?: string;
  conversationType?: string;
  status?: ChannelConversationStatus | "";
  routeMode?: ChannelConversationRouteMode | "";
  sort?: string;
}

export interface ChannelProviderCapabilities {
  conversation_types: string[];
  supports_private_chat: boolean;
  supports_group_chat: boolean;
  supports_channel_chat: boolean;
  supports_mentions: boolean;
  supports_file_upload: boolean;
  supports_message_update: boolean;
  supports_interactive_card: boolean;
  supports_processing_message: boolean;
}

export type ChannelProviderCapabilitiesMap = Record<
  ChannelType,
  ChannelProviderCapabilities
>;

export interface TelegramWebhookConfigure {
  public_base_url: string;
  drop_pending_updates: boolean;
}

export interface TelegramWebhookResult {
  ok: boolean;
  webhook_url: string;
}

export interface ChannelHealthResult {
  ok: boolean;
  channel: string;
  connection_id?: string;
  bot_id?: string;
  username?: string | null;
  display_name?: string | null;
}
