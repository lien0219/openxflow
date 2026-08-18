import type { ChannelConversationBinding } from "./types";

export type ChannelConversationBatchAction =
  | "inherit"
  | "override"
  | "ignore"
  | "restore"
  | "disable"
  | "enable";

export interface ChannelConversationBatchRequest {
  conversation_ids: string[];
  action: ChannelConversationBatchAction;
  default_flow_id?: string | null;
}

export interface ChannelConversationBatchResponse {
  updated: number;
  items: ChannelConversationBinding[];
}
