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
  ChannelConversationBindingUpsert,
} from "@/controllers/API/queries/channels";
import type { KnowledgeBaseInfo } from "@/controllers/API/queries/knowledge-bases/use-get-knowledge-bases";
import type { FlowType } from "@/types/flow";
import { formatWorkflowOptionLabel } from "../utils";

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
  const { t } = useTranslation();
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
          <DialogTitle>
            {binding
              ? t("channels.conversationDialog.editTitle")
              : t("channels.conversationDialog.createTitle")}
          </DialogTitle>
          <DialogDescription>
            {t("channels.conversationDialog.description")}
          </DialogDescription>
        </DialogHeader>
        <form className="flex flex-col gap-5" onSubmit={handleSubmit}>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex flex-col gap-2 text-sm font-medium">
              {t("channels.conversationDialog.chatId")}
              <Input
                value={form.externalConversationId}
                onChange={(event) =>
                  setField("externalConversationId", event.target.value)
                }
                placeholder={t("channels.conversationDialog.chatIdPlaceholder")}
                disabled={Boolean(binding)}
                required
              />
            </label>
            <label className="flex flex-col gap-2 text-sm font-medium">
              {t("channels.conversationDialog.type")}
              <select
                className="primary-input h-10"
                value={form.conversationType}
                onChange={(event) =>
                  setField("conversationType", event.target.value)
                }
              >
                <option value="private">
                  {t("channels.conversationDialog.private")}
                </option>
                <option value="group">
                  {t("channels.conversationDialog.group")}
                </option>
                <option value="supergroup">
                  {t("channels.conversationDialog.supergroup")}
                </option>
                <option value="channel">
                  {t("channels.conversationDialog.channel")}
                </option>
              </select>
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
            {t("channels.conversationDialog.defaultWorkflow")}
            <select
              className="primary-input h-10"
              value={form.defaultFlowId}
              onChange={(event) =>
                setField("defaultFlowId", event.target.value)
              }
            >
              <option value="">
                {t("channels.conversationDialog.noWorkflow")}
              </option>
              {flows.map((flow) => (
                <option key={flow.id} value={flow.id}>
                  {formatWorkflowOptionLabel(flow)}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-2 text-sm font-medium">
            {t("channels.conversationDialog.defaultKnowledgeBase")}
            <select
              className="primary-input h-10"
              value={form.knowledgeBaseId}
              onChange={(event) =>
                setField("knowledgeBaseId", event.target.value)
              }
            >
              <option value="">
                {t("channels.conversationDialog.noKnowledgeBase")}
              </option>
              {knowledgeBases.map((knowledgeBase) => (
                <option key={knowledgeBase.id} value={knowledgeBase.id}>
                  {knowledgeBase.name} (
                  {t("channels.conversationDialog.chunks", {
                    count: knowledgeBase.chunks,
                  })}
                  )
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-2 text-sm font-medium">
            {t("channels.conversationDialog.responseMode")}
            <select
              className="primary-input h-10"
              value={form.responseMode}
              onChange={(event) => setField("responseMode", event.target.value)}
            >
              <option value="mentions_only">
                {t("channels.conversationDialog.mentionsOnly")}
              </option>
              <option value="all_messages">
                {t("channels.conversationDialog.allMessages")}
              </option>
            </select>
          </label>

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
