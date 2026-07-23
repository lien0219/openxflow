import type {
  UseMutationOptions,
  UseMutationResult,
} from "@tanstack/react-query";

export type ChannelType = "telegram" | "feishu" | "dingtalk" | "wecom" | "mock";

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
  settings_data: Record<string, unknown>;
  credentials: Record<string, string>;
}

export interface ChannelConnectionUpdate {
  name?: string;
  enabled?: boolean;
  connection_mode?: string;
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
  settings_data: Record<string, unknown>;
  default_flow_id: string | null;
  knowledge_base_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChannelConversationBindingUpsert {
  external_conversation_id: string;
  conversation_type: string;
  display_name?: string | null;
  response_mode: string;
  allow_file_upload: boolean;
  settings_data: Record<string, unknown>;
  default_flow_id?: string | null;
  knowledge_base_id?: string | null;
}

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
