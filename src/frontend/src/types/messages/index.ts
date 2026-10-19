import type { ContentBlockItem, PropertiesType } from "../chat";

type Message = {
  flow_id: string;
  text: string;
  sender: string;
  sender_name: string;
  session_id: string;
  timestamp: string;
  files: Array<string>;
  id: string | null; // null for placeholder messages
  edit: boolean;
  background_color: string;
  text_color: string;
  category?: string;
  properties?: PropertiesType;
  content_blocks?: ContentBlockItem[];
};

export type { Message };
