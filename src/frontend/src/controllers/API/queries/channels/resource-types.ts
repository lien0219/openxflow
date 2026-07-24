export interface ChannelFlowOption {
  id: string;
  name: string;
  endpoint_name: string | null;
  description: string | null;
  folder_id: string | null;
}

export interface ChannelFlowOptionPage {
  items: ChannelFlowOption[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface ChannelKnowledgeBaseOption {
  id: string;
  name: string;
  status: string;
  chunks: number;
}

export interface ChannelKnowledgeBaseOptionPage {
  items: ChannelKnowledgeBaseOption[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface ChannelResourceQuery {
  page?: number;
  pageSize?: number;
  query?: string;
}
