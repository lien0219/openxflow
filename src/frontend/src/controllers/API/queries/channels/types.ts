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
export type ChannelCommandScope =
  | "connection_shared"
  | "conversation_shared"
  | "identity_connection"
  | "identity_conversation";
export type ChannelAccessPolicy = "shared" | "bound_only" | "hybrid";
export type ChannelAccessPolicyOverride = ChannelAccessPolicy | "inherit";
export type ChannelContextMode = "isolated" | "shared";
export type ChannelContextModeOverride = ChannelContextMode | "inherit";
export type ChannelResponseMode =
  | "mention_only"
  | "all_messages"
  | "commands_only"
  | "disabled";
export type ChannelExecutionStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "timeout"
  | "cancelled"
  | "delivery_failed";
export type ChannelExecutionIdentityType = "service" | "bound_user";
export type ChannelExecutionTrigger =
  | "default"
  | "command"
  | "admin_flow"
  | "file";
export type ChannelMessageDirection = "inbound" | "outbound";
export type ChannelMessageStatus =
  | "received"
  | "processed"
  | "pending"
  | "sent"
  | "failed";
export type ChannelMessageKind =
  | "inbound"
  | "response"
  | "processing"
  | "system";
export type ChannelOutboundDeliveryStatus = "reserved" | "sent" | "failed";

export type ChannelMutationHook<Variables, Data, Error = unknown> = (
  options?: Omit<
    UseMutationOptions<Data, Error, Variables>,
    "mutationFn" | "mutationKey"
  >,
) => UseMutationResult<Data, Error, Variables>;

export interface ChannelConnection {
  id: string;
  user_id: string;
  service_user_id: string | null;
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
  default_response_mode: ChannelResponseMode;
  default_allow_file_upload: boolean;
  access_policy: ChannelAccessPolicy;
  default_context_mode: ChannelContextMode;
  max_concurrency: number;
  per_user_concurrency: number;
  per_user_queue_limit: number;
  rate_limit_per_minute: number;
  daily_quota: number;
  task_timeout_seconds: number;
  queue_timeout_seconds: number;
  shared_context_window: number;
  context_retention_days: number;
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
  default_response_mode?: ChannelResponseMode;
  default_allow_file_upload?: boolean;
  access_policy?: ChannelAccessPolicy;
  default_context_mode?: ChannelContextMode;
  max_concurrency?: number;
  per_user_concurrency?: number;
  per_user_queue_limit?: number;
  rate_limit_per_minute?: number;
  daily_quota?: number;
  task_timeout_seconds?: number;
  queue_timeout_seconds?: number;
  shared_context_window?: number;
  context_retention_days?: number;
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
  default_response_mode?: ChannelResponseMode;
  default_allow_file_upload?: boolean;
  access_policy?: ChannelAccessPolicy;
  default_context_mode?: ChannelContextMode;
  max_concurrency?: number;
  per_user_concurrency?: number;
  per_user_queue_limit?: number;
  rate_limit_per_minute?: number;
  daily_quota?: number;
  task_timeout_seconds?: number;
  queue_timeout_seconds?: number;
  shared_context_window?: number;
  context_retention_days?: number;
  settings_data?: Record<string, unknown>;
  credentials?: Record<string, string>;
}

export interface ChannelIdentity {
  id: string;
  connection_id: string;
  openxflow_user_id: string | null;
  external_user_id: string;
  external_tenant_id: string;
  external_union_id: string | null;
  display_name: string | null;
  status: string;
  profile_data: Record<string, unknown>;
  first_seen_at: string;
  last_seen_at: string;
  last_message_at: string;
  bound_at: string | null;
  updated_at: string;
}

export interface ChannelConversationBinding {
  id: string;
  connection_id: string;
  external_conversation_id: string;
  conversation_type: string;
  display_name: string | null;
  response_mode: ChannelResponseMode;
  allow_file_upload: boolean;
  route_mode: ChannelConversationRouteMode;
  status: ChannelConversationStatus;
  source: ChannelConversationSource;
  access_policy: ChannelAccessPolicyOverride;
  context_mode: ChannelContextModeOverride;
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
  response_mode: ChannelResponseMode;
  allow_file_upload: boolean;
  route_mode?: ChannelConversationRouteMode;
  status?: ChannelConversationStatus;
  source?: ChannelConversationSource;
  access_policy?: ChannelAccessPolicyOverride;
  context_mode?: ChannelContextModeOverride;
  settings_data: Record<string, unknown>;
  provider_metadata?: Record<string, unknown>;
  default_flow_id?: string | null;
  knowledge_base_id?: string | null;
}

export interface ChannelConversationBindingUpdate {
  display_name?: string | null;
  response_mode?: ChannelResponseMode;
  allow_file_upload?: boolean;
  route_mode?: ChannelConversationRouteMode;
  status?: ChannelConversationStatus;
  access_policy?: ChannelAccessPolicyOverride;
  context_mode?: ChannelContextModeOverride;
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
  supports_reply_reference: boolean;
  supports_file_upload: boolean;
  supports_message_update: boolean;
  supports_processing_indicator: boolean;
  supports_processing_message: boolean;
  supports_interactive_card: boolean;
  supports_threads: boolean;
  supports_streaming_connection: boolean;
  processing_message_type: string;
  processing_message_metadata: Record<string, unknown>;
}

export type ChannelProviderCapabilitiesMap = Record<
  ChannelType,
  ChannelProviderCapabilities
>;

export interface ChannelWorkflowCommand {
  id: string;
  connection_id: string;
  conversation_binding_id: string | null;
  owner_user_id: string | null;
  created_by: string;
  flow_id: string;
  command: string;
  normalized_command: string;
  aliases: string[];
  description: string | null;
  scope_type: ChannelCommandScope;
  scope_key: string;
  prompt_template: string | null;
  input_required: boolean;
  allow_attachments: boolean;
  require_mention: boolean;
  enabled: boolean;
  settings_data: Record<string, unknown>;
  last_used_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChannelWorkflowCommandPage {
  items: ChannelWorkflowCommand[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface ChannelWorkflowCommandCreate {
  command: string;
  aliases: string[];
  description?: string | null;
  scope_type: ChannelCommandScope;
  conversation_binding_id?: string | null;
  flow_id: string;
  prompt_template?: string | null;
  input_required: boolean;
  allow_attachments: boolean;
  require_mention: boolean;
  enabled: boolean;
  settings_data: Record<string, unknown>;
}

export interface ChannelWorkflowCommandUpdate {
  command?: string;
  aliases?: string[];
  description?: string | null;
  flow_id?: string;
  prompt_template?: string | null;
  input_required?: boolean;
  allow_attachments?: boolean;
  require_mention?: boolean;
  enabled?: boolean;
  settings_data?: Record<string, unknown>;
}

export interface ChannelCommandQuery {
  connectionId: string;
  page?: number;
  pageSize?: number;
  query?: string;
  scopeType?: ChannelCommandScope | "";
  enabled?: boolean;
}

export interface ChannelExecutionLog {
  id: string;
  connection_id: string;
  conversation_binding_id: string | null;
  openxflow_user_id: string | null;
  external_user_id: string | null;
  session_id: string | null;
  execution_identity_type: ChannelExecutionIdentityType;
  flow_id: string | null;
  external_event_id: string;
  trigger_type: ChannelExecutionTrigger;
  command_name: string | null;
  status: ChannelExecutionStatus;
  queue_wait_ms: number | null;
  duration_ms: number | null;
  delivery_duration_ms: number | null;
  retry_count: number;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface ChannelExecutionLogPage {
  items: ChannelExecutionLog[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface ChannelExecutionQuery {
  connectionId: string;
  page?: number;
  pageSize?: number;
  conversationBindingId?: string;
  openxflowUserId?: string;
  externalUserId?: string;
  sessionId?: string;
  executionIdentityType?: ChannelExecutionIdentityType | "";
  flowId?: string;
  errorCode?: string;
  query?: string;
  status?: ChannelExecutionStatus | "";
  triggerType?: ChannelExecutionTrigger | "";
  createdFrom?: string;
  createdTo?: string;
}

export interface ChannelMessageRecord {
  id: string;
  connection_id: string;
  conversation_binding_id: string | null;
  execution_id: string | null;
  external_event_id: string;
  external_message_id: string | null;
  provider_message_id: string | null;
  external_conversation_id: string;
  conversation_scope_id: string;
  external_user_id: string | null;
  sender_name: string | null;
  direction: ChannelMessageDirection;
  message_kind: ChannelMessageKind;
  message_type: string;
  status: ChannelMessageStatus;
  text: string | null;
  has_attachments: boolean;
  attachment_count: number;
  reply_to_message_id: string | null;
  error_code: string | null;
  error_message: string | null;
  metadata_data: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  delivered_at: string | null;
}

export interface ChannelMessageRecordPage {
  items: ChannelMessageRecord[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface ChannelMessageQuery {
  connectionId: string;
  page?: number;
  pageSize?: number;
  query?: string;
  direction?: ChannelMessageDirection | "";
  status?: ChannelMessageStatus | "";
  conversationBindingId?: string;
  externalConversationId?: string;
  externalUserId?: string;
  createdFrom?: string;
  createdTo?: string;
}

export interface ChannelOutboundDelivery {
  id: string;
  connection_id: string;
  external_event_id: string;
  delivery_kind: string;
  response_digest: string;
  status: ChannelOutboundDeliveryStatus;
  attempts: number;
  provider_message_id: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
  sent_at: string | null;
}

export interface ChannelOutboundDeliveryPage {
  items: ChannelOutboundDelivery[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface ChannelDeliveryQuery {
  connectionId: string;
  page?: number;
  pageSize?: number;
  query?: string;
  status?: ChannelOutboundDeliveryStatus | "";
  deliveryKind?: string;
  createdFrom?: string;
  createdTo?: string;
}

export interface ChannelRetryDeliveryResult {
  delivery_id: string;
  webhook_job_id: string;
  status: string;
  already_queued: boolean;
}

export interface ChannelConfigurationAudit {
  id: string;
  connection_id: string | null;
  connection_reference: string;
  actor_user_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  before_data: Record<string, unknown>;
  after_data: Record<string, unknown>;
  changes_data: Record<string, unknown>;
  created_at: string;
}

export interface ChannelConfigurationAuditPage {
  items: ChannelConfigurationAudit[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface ChannelAuditQuery {
  connectionId: string;
  page?: number;
  pageSize?: number;
  action?: string;
  resourceType?: string;
  actorUserId?: string;
  createdFrom?: string;
  createdTo?: string;
}

export interface ChannelConnectionOverview {
  window_hours: number;
  started_at: string;
  ended_at: string;
  active_conversations: number;
  unique_external_users: number;
  inbound_messages: number;
  outbound_messages: number;
  failed_messages: number;
  queued_jobs: number;
  processing_jobs: number;
  failed_jobs: number;
  sent_deliveries: number;
  failed_deliveries: number;
  reserved_deliveries: number;
  execution_counts: Record<ChannelExecutionStatus, number>;
  execution_success_rate: number;
  average_execution_duration_ms: number | null;
  p95_execution_duration_ms: number | null;
  average_queue_wait_ms: number | null;
  p95_queue_wait_ms: number | null;
}

export interface ChannelOverviewQuery {
  connectionId: string;
  windowHours?: number;
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
