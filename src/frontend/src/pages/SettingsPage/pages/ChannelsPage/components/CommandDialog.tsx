import { useEffect, useMemo, useState } from "react";
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
import {
  type ChannelCommandScope,
  type ChannelWorkflowCommand,
  type ChannelWorkflowCommandCreate,
  type ChannelWorkflowCommandUpdate,
  useGetChannelConversations,
} from "@/controllers/API/queries/channels";
import useChannelCopy from "../use-channel-copy";
import ChannelResourceSelect from "./ChannelResourceSelect";

interface CommandDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  connectionId: string;
  command?: ChannelWorkflowCommand | null;
  loading?: boolean;
  onCreate: (payload: ChannelWorkflowCommandCreate) => Promise<void>;
  onUpdate: (payload: ChannelWorkflowCommandUpdate) => Promise<void>;
}

interface CommandFormState {
  command: string;
  aliases: string;
  description: string;
  scopeType: ChannelCommandScope;
  conversationBindingId: string;
  flowId: string;
  promptTemplate: string;
  inputRequired: boolean;
  allowAttachments: boolean;
  requireMention: boolean;
  enabled: boolean;
}

const DEFAULT_FORM: CommandFormState = {
  command: "",
  aliases: "",
  description: "",
  scopeType: "connection_shared",
  conversationBindingId: "",
  flowId: "",
  promptTemplate: "",
  inputRequired: false,
  allowAttachments: true,
  requireMention: false,
  enabled: true,
};

const SCOPE_LABELS: Record<ChannelCommandScope, string> = {
  connection_shared: "连接共享：所有用户和会话可用",
  conversation_shared: "会话共享：指定会话所有用户可用",
  identity_connection: "我的连接指令：仅自己在当前连接可用",
  identity_conversation: "我的会话指令：仅自己在指定会话可用",
};

export default function CommandDialog({
  open,
  onOpenChange,
  connectionId,
  command,
  loading = false,
  onCreate,
  onUpdate,
}: CommandDialogProps) {
  const copy = useChannelCopy();
  const [form, setForm] = useState<CommandFormState>(DEFAULT_FORM);
  const [conversationSearch, setConversationSearch] = useState("");
  const { data: conversationResult, isLoading: conversationsLoading } =
    useGetChannelConversations(
      {
        connectionId,
        page: 1,
        pageSize: 20,
        query: conversationSearch,
        sort: "-last_message_at",
      },
      { enabled: open && Boolean(connectionId) },
    );

  useEffect(() => {
    if (!open) return;
    if (!command) {
      setForm(DEFAULT_FORM);
      setConversationSearch("");
      return;
    }
    setForm({
      command: command.command,
      aliases: command.aliases.join(", "),
      description: command.description ?? "",
      scopeType: command.scope_type,
      conversationBindingId: command.conversation_binding_id ?? "",
      flowId: command.flow_id,
      promptTemplate: command.prompt_template ?? "",
      inputRequired: command.input_required,
      allowAttachments: command.allow_attachments,
      requireMention: command.require_mention,
      enabled: command.enabled,
    });
  }, [command, open]);

  const needsConversation = useMemo(
    () =>
      form.scopeType === "conversation_shared" ||
      form.scopeType === "identity_conversation",
    [form.scopeType],
  );

  const setField = <K extends keyof CommandFormState>(
    key: K,
    value: CommandFormState[K],
  ) => setForm((current) => ({ ...current, [key]: value }));

  const normalizeAliases = () =>
    form.aliases
      .split(/[,，\s]+/)
      .map((item) => item.trim())
      .filter(Boolean)
      .slice(0, 5);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const common = {
      command: form.command.trim(),
      aliases: normalizeAliases(),
      description: form.description.trim() || null,
      flow_id: form.flowId,
      prompt_template: form.promptTemplate.trim() || null,
      input_required: form.inputRequired,
      allow_attachments: form.allowAttachments,
      require_mention: form.requireMention,
      enabled: form.enabled,
      settings_data: {},
    };
    if (command) {
      await onUpdate(common);
      return;
    }
    await onCreate({
      ...common,
      scope_type: form.scopeType,
      conversation_binding_id: needsConversation
        ? form.conversationBindingId || null
        : null,
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {command ? copy("编辑指令") : copy("新增自定义指令")}
          </DialogTitle>
          <DialogDescription>
            {copy(
              "用户发送“/指令 内容”时，仅本次消息路由到指定工作流，不会改变默认工作流。",
            )}
          </DialogDescription>
        </DialogHeader>
        <form className="flex flex-col gap-5" onSubmit={handleSubmit}>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex flex-col gap-2 text-sm font-medium">
              {copy("指令名称")}
              <Input
                value={form.command}
                onChange={(event) => setField("command", event.target.value)}
                placeholder={copy("/code 或 /代码审查")}
                required
              />
              <span className="text-xs font-normal text-muted-foreground">
                {copy("支持中文、英文、数字、-、_，最多 32 个字符。")}
              </span>
            </label>
            <label className="flex flex-col gap-2 text-sm font-medium">
              {copy("别名")}
              <Input
                value={form.aliases}
                onChange={(event) => setField("aliases", event.target.value)}
                placeholder={copy("/review, /检查代码")}
              />
              <span className="text-xs font-normal text-muted-foreground">
                {copy("使用逗号或空格分隔，最多 5 个。")}
              </span>
            </label>
          </div>

          <label className="flex flex-col gap-2 text-sm font-medium">
            {copy("指令说明")}
            <Input
              value={form.description}
              onChange={(event) => setField("description", event.target.value)}
              placeholder={copy("用于 /commands 列表和无参数提示")}
            />
          </label>

          {!command && (
            <label className="flex flex-col gap-2 text-sm font-medium">
              {copy("生效范围")}
              <select
                className="primary-input h-10"
                value={form.scopeType}
                onChange={(event) =>
                  setField(
                    "scopeType",
                    event.target.value as ChannelCommandScope,
                  )
                }
              >
                {Object.entries(SCOPE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {copy(label)}
                  </option>
                ))}
              </select>
            </label>
          )}

          {needsConversation && !command && (
            <div className="flex flex-col gap-2">
              <label className="text-sm font-medium">{copy("指定会话")}</label>
              <Input
                value={conversationSearch}
                onChange={(event) => setConversationSearch(event.target.value)}
                placeholder={copy("先搜索会话名称或平台会话 ID")}
              />
              <select
                className="primary-input h-10"
                value={form.conversationBindingId}
                onChange={(event) =>
                  setField("conversationBindingId", event.target.value)
                }
                required
              >
                <option value="">
                  {conversationsLoading
                    ? copy("正在加载…")
                    : copy("请选择会话")}
                </option>
                {(conversationResult?.items ?? []).map((conversation) => (
                  <option key={conversation.id} value={conversation.id}>
                    {conversation.display_name ||
                      conversation.external_conversation_id}
                    {` · ${conversation.conversation_type}`}
                  </option>
                ))}
              </select>
            </div>
          )}

          <ChannelResourceSelect
            kind="flow"
            label={copy("目标工作流")}
            emptyLabel={copy("请选择工作流")}
            value={form.flowId}
            onChange={(value) => setField("flowId", value)}
            required
          />

          <label className="flex flex-col gap-2 text-sm font-medium">
            {copy("输入模板（可选）")}
            <textarea
              className="primary-input min-h-28 resize-y px-3 py-2"
              value={form.promptTemplate}
              onChange={(event) =>
                setField("promptTemplate", event.target.value)
              }
              placeholder={copy(
                "请按代码审查标准处理以下内容：\n{{input}}\n\n发送人：{{sender_name}}",
              )}
            />
            <span className="text-xs font-normal text-muted-foreground">
              {copy("支持模板变量")}: <code>{"{{input}}"}</code>,{" "}
              <code>{"{{sender_name}}"}</code>,{" "}
              <code>{"{{conversation_name}}"}</code>,{" "}
              <code>{"{{conversation_type}}"}</code>.
            </span>
          </label>

          <div className="grid gap-3 sm:grid-cols-2">
            <CommandSwitch
              title={copy("必须输入参数")}
              description={copy(
                "只有指令没有正文或附件时显示用法，不执行工作流。",
              )}
              checked={form.inputRequired}
              onCheckedChange={(checked) => setField("inputRequired", checked)}
            />
            <CommandSwitch
              title={copy("允许附件")}
              description={copy("允许图片和文件随指令一起提交给工作流。")}
              checked={form.allowAttachments}
              onCheckedChange={(checked) =>
                setField("allowAttachments", checked)
              }
            />
            <CommandSwitch
              title={copy("群聊必须 @机器人")}
              description={copy("在群聊使用此指令时仍要求明确提及机器人。")}
              checked={form.requireMention}
              onCheckedChange={(checked) => setField("requireMention", checked)}
            />
            <CommandSwitch
              title={copy("启用指令")}
              description={copy("关闭后保留配置，但不再匹配和展示。")}
              checked={form.enabled}
              onCheckedChange={(checked) => setField("enabled", checked)}
            />
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              {copy("取消")}
            </Button>
            <Button type="submit" loading={loading}>
              {copy("保存指令")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function CommandSwitch({
  title,
  description,
  checked,
  onCheckedChange,
}: {
  title: string;
  description: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between rounded-lg border p-4">
      <div className="pr-3">
        <div className="text-sm font-medium">{title}</div>
        <div className="mt-1 text-xs text-muted-foreground">{description}</div>
      </div>
      <Switch checked={checked} onCheckedChange={onCheckedChange} />
    </div>
  );
}
