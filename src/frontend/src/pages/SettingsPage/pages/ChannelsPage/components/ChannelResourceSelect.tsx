import { useEffect, useMemo, useState } from "react";
import { Input } from "@/components/ui/input";
import {
  type ChannelFlowOption,
  type ChannelKnowledgeBaseOption,
  useGetChannelFlowOptions,
  useGetChannelKnowledgeBaseOptions,
} from "@/controllers/API/queries/channels";

type ResourceKind = "flow" | "knowledge-base";

interface ChannelResourceSelectProps {
  kind: ResourceKind;
  value: string;
  onChange: (value: string) => void;
  label: string;
  emptyLabel: string;
  required?: boolean;
  disabled?: boolean;
}

export default function ChannelResourceSelect({
  kind,
  value,
  onChange,
  label,
  emptyLabel,
  required = false,
  disabled = false,
}: ChannelResourceSelectProps) {
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch(searchInput.trim());
      setPage(1);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const flowQuery = useGetChannelFlowOptions(
    { page, pageSize: 20, query: search },
    { enabled: kind === "flow" && !disabled },
  );
  const knowledgeBaseQuery = useGetChannelKnowledgeBaseOptions(
    { page, pageSize: 20, query: search },
    { enabled: kind === "knowledge-base" && !disabled },
  );

  const result = kind === "flow" ? flowQuery.data : knowledgeBaseQuery.data;
  const isLoading =
    kind === "flow" ? flowQuery.isLoading : knowledgeBaseQuery.isLoading;

  const items = useMemo(() => result?.items ?? [], [result?.items]) as Array<
    ChannelFlowOption | ChannelKnowledgeBaseOption
  >;
  const selectedInPage = items.some((item) => item.id === value);

  return (
    <label className="flex flex-col gap-2 text-sm font-medium">
      {label}
      <Input
        value={searchInput}
        onChange={(event) => setSearchInput(event.target.value)}
        placeholder={`搜索${label}`}
        disabled={disabled}
      />
      <select
        className="primary-input h-10"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        required={required}
        disabled={disabled}
      >
        <option value="">{isLoading ? "正在加载…" : emptyLabel}</option>
        {value && !selectedInPage && (
          <option value={value}>当前已选择 · {value.slice(0, 8)}</option>
        )}
        {items.map((item) => (
          <option key={item.id} value={item.id}>
            {formatResourceOption(kind, item)}
          </option>
        ))}
      </select>
      {(result?.total_pages ?? 0) > 1 && (
        <div className="flex items-center justify-end gap-2 text-xs font-normal text-muted-foreground">
          <button
            type="button"
            className="hover:text-foreground disabled:opacity-40"
            disabled={page <= 1}
            onClick={() => setPage((current) => Math.max(1, current - 1))}
          >
            上一页
          </button>
          <span>
            {page} / {result?.total_pages}
          </span>
          <button
            type="button"
            className="hover:text-foreground disabled:opacity-40"
            disabled={page >= (result?.total_pages ?? 0)}
            onClick={() => setPage((current) => current + 1)}
          >
            下一页
          </button>
        </div>
      )}
    </label>
  );
}

function formatResourceOption(
  kind: ResourceKind,
  item: ChannelFlowOption | ChannelKnowledgeBaseOption,
): string {
  if (kind === "flow") {
    const flow = item as ChannelFlowOption;
    return flow.endpoint_name
      ? `${flow.name} (${flow.endpoint_name})`
      : flow.name;
  }
  const knowledgeBase = item as ChannelKnowledgeBaseOption;
  return `${knowledgeBase.name} (${knowledgeBase.chunks} 个分块 · ${knowledgeBase.status})`;
}
