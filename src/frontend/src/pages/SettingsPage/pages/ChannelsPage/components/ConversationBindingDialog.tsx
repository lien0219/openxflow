import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import type {
  ChannelConversationBinding,
  ChannelConversationBindingUpsert,
} from "@/controllers/API/queries/channels";
import type { KnowledgeBaseInfo } from "@/controllers/API/queries/knowledge-bases/use-get-knowledge-bases";
import type { FlowType } from "@/types/flow";

interface ConversationBindingDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  binding?: ChannelConversationBinding | null;
  flows: FlowType[];
  knowledgeBases: KnowledgeBaseInfo[];
  loading?: boolean;
  onSubmit: (payload: ChannelConversationBindingUpsert) => Promise<void>;
}

interface ConversationFormState {
  externalConversationId: string;
  conversationType: string;
  displayName: string;
  responseMode: string;
  defaultFlowId: string;
  knowledgeBaseId: string;
  allowFileUpload: boolean;
}

export default function ConversationBindingDialog({
  open,
  onOpenChange,
  binding,
  flows,
  knowledgeBases,
  loading = false,
  onSubmit,
}: ConversationBindingDialogProps) {
  const [form, setForm] = useState<ConversationFormState>({
    externalConversationId: "",
    conversationType: "private",
    displayName: "",
    responseMode: "mentions_only",
    defaultFlowId: "",
    knowledgeBaseId: "",
    allowFileUpload: true,
  });

  useEffect(() => {
    if (!open) return;
    setForm({
      externalConversationId: binding?.external_conversation_id ?? "",
      conversationType: binding?.conversation_type ?? "private",
      displayName: binding?.display_name ?? "",
      responseMode: binding?.response_mode ?? "mentions_only",
      defaultFlowId: binding?.default_flow_id ?? "",
      knowledgeBaseId: binding?.knowledge_base_id ?? "",
      allowFileUpload: binding?.allow_file_upload ?? true,
    });
  }, [binding, open]);

  const setField = <K extends keyof ConversationFormState>(
    key: K,
    value: ConversationFormState[K],
  ) => setForm((current) => ({ ...current, [key]: value }));

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!form.externalConversationId.trim()) return;
    await onSubmit({
      external_conversation_id: form.externalConversationId.trim(),
      conversation_type: form.conversationType,
      display_name: form.displayName.trim() || null,
      response_mode: form.responseMode,
      allow_file_upload: form.allowFileUpload,
      settings_data: binding?.settings_data ?? {},
      default_flow_id: form.defaultFlowId || null,
      knowledge_base_id: form.knowledgeBaseId || null,
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{binding ? "编辑会话绑定" : "新增会话绑定"}</DialogTitle>
          <DialogDescription>
            将 Telegram
            私聊或群聊绑定到默认工作流和知识库，用户可直接在手机端提问和上传资料。
          </DialogDescription>
        </DialogHeader>
        <form className="flex flex-col gap-5" onSubmit={handleSubmit}>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex flex-col gap-2 text-sm font-medium">
              Telegram Chat ID
              <Input
                value={form.externalConversationId}
                onChange={(event) =>
                  setField("externalConversationId", event.target.value)
                }
                placeholder="例如：-1001234567890"
                disabled={Boolean(binding)}
                required
              />
            </label>
            <label className="flex flex-col gap-2 text-sm font-medium">
              会话类型
              <select
                className="primary-input h-10"
                value={form.conversationType}
                onChange={(event) =>
                  setField("conversationType", event.target.value)
                }
              >
                <option value="private">私聊</option>
                <option value="group">群聊</option>
                <option value="supergroup">超级群组</option>
                <option value="channel">频道</option>
              </select>
            </label>
          </div>

          <label className="flex flex-col gap-2 text-sm font-medium">
            显示名称
            <Input
              value={form.displayName}
              onChange={(event) => setField("displayName", event.target.value)}
              placeholder="例如：研发项目群"
            />
          </label>

          <label className="flex flex-col gap-2 text-sm font-medium">
            默认工作流
            <select
              className="primary-input h-10"
              value={form.defaultFlowId}
              onChange={(event) =>
                setField("defaultFlowId", event.target.value)
              }
            >
              <option value="">不绑定默认工作流</option>
              {flows.map((flow) => (
                <option key={flow.id} value={flow.id}>
                  {flow.name}
                  {flow.endpoint_name ? ` (${flow.endpoint_name})` : ""}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-2 text-sm font-medium">
            默认知识库
            <select
              className="primary-input h-10"
              value={form.knowledgeBaseId}
              onChange={(event) =>
                setField("knowledgeBaseId", event.target.value)
              }
            >
              <option value="">不绑定知识库</option>
              {knowledgeBases.map((knowledgeBase) => (
                <option key={knowledgeBase.id} value={knowledgeBase.id}>
                  {knowledgeBase.name}（{knowledgeBase.chunks} 个分块）
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-2 text-sm font-medium">
            群聊响应模式
            <select
              className="primary-input h-10"
              value={form.responseMode}
              onChange={(event) => setField("responseMode", event.target.value)}
            >
              <option value="mentions_only">仅 @机器人或命令</option>
              <option value="all_messages">处理全部消息</option>
            </select>
          </label>

          <div className="flex items-center justify-between rounded-lg border p-4">
            <div>
              <div className="text-sm font-medium">允许手机上传文件</div>
              <div className="text-xs text-muted-foreground">
                开启后文件会保存到用户文件区；绑定知识库时还会自动解析入库。
              </div>
            </div>
            <Switch
              checked={form.allowFileUpload}
              onCheckedChange={(checked) =>
                setField("allowFileUpload", checked)
              }
            />
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              取消
            </Button>
            <Button type="submit" loading={loading}>
              保存绑定
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
