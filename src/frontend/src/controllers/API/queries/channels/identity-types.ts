import type { ChannelIdentity } from "./types";

export interface ChannelIdentityPage {
  items: ChannelIdentity[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface ChannelIdentityPageQuery {
  connectionId: string;
  page?: number;
  pageSize?: number;
  query?: string;
  status?: string;
}
