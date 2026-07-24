import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
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
  ChannelConversationBindingUpdate,
  ChannelConversationRouteMode,
} from "@/controllers/API/queries/channels";
import ChannelResourceSelect from "./ChannelResourceSelect";

interface ConversationBindingDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  binding?: ChannelConversationBinding | null;
  supportsMentions?: boolean;
  supportsFileUpload?: boolean;
  loading?: boolean;
  onSubmit: (payload: ChannelConversationBindingUpdate) => Promise<void>;
}

interface ConversationFormState {
  displayName: string;
  routeMode: ChannelConversationRouteMode;
  responseMode: string;
  defaultFlowId: string;
  knowledgeBaseId: string;
  allowFileUpload: boolean;
  ignored: boolean;
}

export default function ConversationBindingDialog({
  open,
  onOpenChange,
  binding,
  supportsMentions = true,
  supportsFileUpload = true,
  loading = false,
  onSubmit,
}: ConversationBindingDialogProps) {
  const { t } = useTranslation();
  const [form, setForm] = useState<ConversationFormState>({
    displayName: "",
    routeMode: "inherit",
    responseMode: "mentions_only",
    defaultFlowId: "",
    knowledgeBaseId: "",
    allowFileUpload: true,
    ignored: false,
  });

  useEffect(() => {
    if (!open || !binding) return;
    setForm({
      displayName: binding.display_name ?? "",
      routeMode: binding.route_mode,
      responseMode: binding.response_mode,
      defaultFlowId: binding.default_flow_id ?? "",
      knowledgeBaseId: binding.knowledge_base_id ?? "",
      allowFileUpload: binding.allow_file_upload,
      ignored: binding.status === "ignored",
    });
  }, [binding, open]);

  const setField = <K extends keyof ConversationFormState>(
    key: K,
    value: ConversationFormState[K],
  ) => setForm((current) => ({ ...current, [key]: value }));

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!binding) return;
    await onSubmit({
      display_name: form.displayName.trim() || null,
      route_mode: form.routeMode,
      response_mode: form.responseMode,
      allow_file_upload: form.allowFileUpload,
      settings_data: binding.settings_data,
      default_flow_id:
        form.routeMode === "override" ? form.defaultFlowId || null : null,
      knowledge_base_id: form.knowledgeBaseId || null,
      status: form.ignored
        ? "ignored"
        : binding.status === "ignored"
          ? "pending"
          : undefined,
    });
  };

  if (!binding) return null;

  const isGroupConversation = binding.conversation_type !== "private";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t("channels.conversationDialog.editTitle")}</DialogTitle>
          <DialogDescription>
            会话由渠道消息自动发现，平台会话 ID 和会话类型不可手工修改。
          </DialogDescription>
        </DialogHeader>
        <form className="flex flex-col gap-5" onSubmit={handleSubmit}>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex flex-col gap-2 text-sm font-medium">
              {t("channels.conversationDialog.chatId")}
              <Input value={binding.external_conversation_id} disabled />
            </label>
            <label className="flex flex-col gap-2 text-sm font-medium">
              {t("channels.conversationDialog.type")}
              <Input
                value={t(
                  `channels.conversationDialog.${binding.conversation_type}`,
                  { defaultValue: binding.conversation_type },
                )}
                disabled
              />
            </label>
          </div>

          <label className="flex flex-col gap-2 text-sm font-medium">
            {t("channels.conversationDialog.displayName")}
            <Input
              value={form.displayName}
              onChange={(event) => setField("displayName", event.target.value)}
              placeholder={t(
                "channels.conversationDialog.displayNamePlaceholder",
              )}
            />
          </label>

          <label className="flex flex-col gap-2 text-sm font-medium">
            默认路由方式
            <select
              className="primary-input h-10"
              value={form.routeMode}
              onChange={(event) =>
                setField(
                  "routeMode",
                  event.target.value as ChannelConversationRouteMode,
                )
              }
            >
              <option value="inherit">继承渠道连接默认工作流</option>
              <option value="override">使用此会话独立工作流</option>
              <option value="disabled">禁用普通消息工作流</option>
            </select>
          </label>

          {form.routeMode === "override" && (
            <ChannelResourceSelect
              kind="flow"
              label={t("channels.conversationDialog.defaultWorkflow")}
              emptyLabel={t("channels.conversationDialog.noWorkflow")}
              value={form.defaultFlowId}
              onChange={(value) => setField("defaultFlowId", value)}
              required
            />
          )}

          <ChannelResourceSelect
            kind="knowledge-base"
            label={t("channels.conversationDialog.defaultKnowledgeBase")}
            emptyLabel={t("channels.conversationDialog.noKnowledgeBase")}
            value={form.knowledgeBaseId}
            onChange={(value) => setField("knowledgeBaseId", value)}
          />

          {isGroupConversation && supportsMentions && (
            <label className="flex flex-col gap-2 text-sm font-medium">
              {t("channels.conversationDialog.responseMode")}
              <select
                className="primary-input h-10"
                value={form.responseMode}
                onChange={(event) =>
                  setField("responseMode", event.target.value)
                }
              >
                <option value="mentions_only">
                  {t("channels.conversationDialog.mentionsOnly")}
                </option>
                <option value="all_messages">
                  {t("channels.conversationDialog.allMessages")}
                </option>
              </select>
            </label>
          )}

          {supportsFileUpload && (
            <div className="flex items-center justify-between rounded-lg border p-4">
              <div>
                <div className="text-sm font-medium">
                  {t("channels.conversationDialog.allowUpload")}
                </div>
                <div className="text-xs text-muted-foreground">
                  {t("channels.conversationDialog.allowUploadHelp")}
                </div>
              </div>
              <Switch
                checked={form.allowFileUpload}
                onCheckedChange={(checked) =>
                  setField("allowFileUpload", checked)
                }
              />
            </div>
          )}

          <div className="flex items-center justify-between rounded-lg border p-4">
            <div>
              <div className="text-sm font-medium">忽略当前会话</div>
              <div className="text-xs text-muted-foreground">
                开启后保留会话记录和配置，但机器人不再响应此会话。
              </div>
            </div>
            <Switch
              checked={form.ignored}
              onCheckedChange={(checked) => setField("ignored", checked)}
            />
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              {t("channels.actions.cancel")}
            </Button>
            <Button type="submit" loading={loading}>
              {t("channels.actions.saveBinding")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
