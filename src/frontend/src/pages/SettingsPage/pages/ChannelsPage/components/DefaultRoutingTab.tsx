import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  type ChannelConnection,
  type ChannelProviderCapabilities,
  type ChannelResponseMode,
  type ChannelUnconfiguredBehavior,
  useUpdateChannelConnection,
} from "@/controllers/API/queries/channels";
import useAlertStore from "@/stores/alertStore";
import useChannelCopy from "../use-channel-copy";
import ChannelResourceSelect from "./ChannelResourceSelect";

interface DefaultRoutingTabProps {
  connection: ChannelConnection;
  capabilities?: ChannelProviderCapabilities;
}

interface RoutingFormState {
  defaultFlowId: string;
  defaultKnowledgeBaseId: string;
  autoDiscoverConversations: boolean;
  unconfiguredBehavior: ChannelUnconfiguredBehavior;
  pendingNoticeEnabled: boolean;
  personalCommandsEnabled: boolean;
  userFlowSelectionEnabled: boolean;
  flowSelectionTtlHours: string;
  systemCommandRequireMention: boolean;
  defaultResponseMode: ChannelResponseMode;
  defaultAllowFileUpload: boolean;
}

export default function DefaultRoutingTab({
  connection,
  capabilities,
}: DefaultRoutingTabProps) {
  const setSuccessData = useAlertStore((state) => state.setSuccessData);
  const setErrorData = useAlertStore((state) => state.setErrorData);
  const updateConnection = useUpdateChannelConnection();
  const copy = useChannelCopy();
  const [form, setForm] = useState<RoutingFormState>(() =>
    formFromConnection(connection),
  );

  useEffect(() => {
    setForm(formFromConnection(connection));
  }, [connection]);

  const handleSave = async () => {
    try {
      await updateConnection.mutateAsync({
        connectionId: connection.id,
        payload: {
          default_flow_id: form.defaultFlowId || null,
          default_knowledge_base_id: form.defaultKnowledgeBaseId || null,
          auto_discover_conversations: form.autoDiscoverConversations,
          unconfigured_behavior: form.unconfiguredBehavior,
          pending_notice_enabled: form.pendingNoticeEnabled,
          personal_commands_enabled: form.personalCommandsEnabled,
          user_flow_selection_enabled: form.userFlowSelectionEnabled,
          flow_selection_ttl_hours: Math.min(
            8760,
            Math.max(0, Number(form.flowSelectionTtlHours) || 0),
          ),
          settings_data: {
            ...connection.settings_data,
            system_command_require_mention: form.systemCommandRequireMention,
          },
          default_response_mode: form.defaultResponseMode,
          default_allow_file_upload: form.defaultAllowFileUpload,
        },
      });
      setSuccessData({ title: copy("默认路由设置已保存") });
    } catch (error) {
      setErrorData({
        title: copy("默认路由保存失败"),
        list: [error instanceof Error ? error.message : String(error)],
      });
    }
  };

  return (
    <div className="flex flex-col gap-5 rounded-xl border p-5">
      <div>
        <h3 className="font-semibold">{copy("连接默认路由")}</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          {copy("没有单独覆盖的私聊或群聊会继承这里配置的工作流和知识库。")}
        </p>
      </div>

      <ChannelResourceSelect
        kind="flow"
        label={copy("全局默认工作流")}
        emptyLabel={copy("不设置全局默认工作流")}
        value={form.defaultFlowId}
        onChange={(value) =>
          setForm((current) => ({ ...current, defaultFlowId: value }))
        }
      />

      <ChannelResourceSelect
        kind="knowledge-base"
        label={copy("全局默认知识库")}
        emptyLabel={copy("不设置全局默认知识库")}
        value={form.defaultKnowledgeBaseId}
        onChange={(value) =>
          setForm((current) => ({
            ...current,
            defaultKnowledgeBaseId: value,
          }))
        }
      />

      <label className="flex flex-col gap-2 text-sm font-medium">
        {copy("没有可用默认工作流时")}
        <select
          className="primary-input h-10"
          value={form.unconfiguredBehavior}
          onChange={(event) =>
            setForm((current) => ({
              ...current,
              unconfiguredBehavior: event.target
                .value as ChannelUnconfiguredBehavior,
            }))
          }
        >
          <option value="notify_pending">{copy("首次提示待配置")}</option>
          <option value="ignore">{copy("静默忽略")}</option>
          <option value="use_global_default">
            {copy("优先使用全局默认工作流")}
          </option>
        </select>
      </label>

      <div className="grid gap-3 md:grid-cols-2">
        <SettingSwitch
          title={copy("自动发现会话")}
          description={copy("收到新私聊或群聊消息时自动记录真实平台会话 ID。")}
          checked={form.autoDiscoverConversations}
          onCheckedChange={(checked) =>
            setForm((current) => ({
              ...current,
              autoDiscoverConversations: checked,
            }))
          }
        />
        <SettingSwitch
          title={copy("待配置提示")}
          description={copy("无默认工作流时向会话发送一次配置提示。")}
          checked={form.pendingNoticeEnabled}
          onCheckedChange={(checked) =>
            setForm((current) => ({
              ...current,
              pendingNoticeEnabled: checked,
            }))
          }
        />
        <SettingSwitch
          title={copy("允许用户切换工作流")}
          description={copy(
            "用户可按成员、会话和线程持久选择管理员允许的业务工作流。",
          )}
          checked={form.userFlowSelectionEnabled}
          onCheckedChange={(checked) =>
            setForm((current) => ({
              ...current,
              userFlowSelectionEnabled: checked,
            }))
          }
        />
        <SettingSwitch
          title={copy("允许个人指令")}
          description={copy("绑定用户可创建仅对自己生效的工作流指令。")}
          checked={form.personalCommandsEnabled}
          onCheckedChange={(checked) =>
            setForm((current) => ({
              ...current,
              personalCommandsEnabled: checked,
            }))
          }
        />
        {capabilities?.supports_group_chat &&
          capabilities.supports_mentions && (
            <SettingSwitch
              title={copy("群聊系统指令必须 @机器人")}
              description={copy(
                "避免群内多个机器人同时响应 /help、/commands 等系统指令；Telegram 的 /command@bot_name 视为已明确指定。",
              )}
              checked={form.systemCommandRequireMention}
              onCheckedChange={(checked) =>
                setForm((current) => ({
                  ...current,
                  systemCommandRequireMention: checked,
                }))
              }
            />
          )}
        {capabilities?.supports_file_upload && (
          <SettingSwitch
            title={copy("默认允许文件上传")}
            description={copy("新发现会话默认允许接收和处理文件。")}
            checked={form.defaultAllowFileUpload}
            onCheckedChange={(checked) =>
              setForm((current) => ({
                ...current,
                defaultAllowFileUpload: checked,
              }))
            }
          />
        )}
      </div>

      {form.userFlowSelectionEnabled && (
        <label className="flex flex-col gap-2 text-sm font-medium">
          {copy("工作流选择有效期（小时）")}
          <Input
            type="number"
            min={0}
            max={8760}
            value={form.flowSelectionTtlHours}
            onChange={(event) =>
              setForm((current) => ({
                ...current,
                flowSelectionTtlHours: event.target.value,
              }))
            }
          />
          <span className="text-xs font-normal text-muted-foreground">
            {copy("设置为 0 表示永久有效，直到用户恢复默认或管理员撤销。")}
          </span>
        </label>
      )}

      {capabilities?.supports_group_chat && capabilities.supports_mentions && (
        <label className="flex flex-col gap-2 text-sm font-medium">
          {copy("新群聊默认响应模式")}
          <select
            className="primary-input h-10"
            value={form.defaultResponseMode}
            onChange={(event) =>
              setForm((current) => ({
                ...current,
                defaultResponseMode: event.target.value as ChannelResponseMode,
              }))
            }
          >
            <option value="mention_only">
              {copy("仅 @机器人或指令时响应")}
            </option>
            <option value="all_messages">{copy("响应所有消息")}</option>
            <option value="commands_only">{copy("仅响应指令")}</option>
            <option value="disabled">{copy("完全停用响应")}</option>
          </select>
        </label>
      )}

      <div className="flex justify-end">
        <Button
          variant="primary"
          onClick={handleSave}
          loading={updateConnection.isPending}
        >
          {copy("保存默认路由")}
        </Button>
      </div>
    </div>
  );
}

function formFromConnection(connection: ChannelConnection): RoutingFormState {
  return {
    defaultFlowId: connection.default_flow_id ?? "",
    defaultKnowledgeBaseId: connection.default_knowledge_base_id ?? "",
    autoDiscoverConversations: connection.auto_discover_conversations,
    unconfiguredBehavior: connection.unconfigured_behavior,
    pendingNoticeEnabled: connection.pending_notice_enabled,
    personalCommandsEnabled: connection.personal_commands_enabled,
    userFlowSelectionEnabled: connection.user_flow_selection_enabled,
    flowSelectionTtlHours: String(connection.flow_selection_ttl_hours),
    systemCommandRequireMention:
      connection.settings_data.system_command_require_mention !== false,
    defaultResponseMode: connection.default_response_mode,
    defaultAllowFileUpload: connection.default_allow_file_upload,
  };
}

function SettingSwitch({
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
      <div className="pr-4">
        <div className="text-sm font-medium">{title}</div>
        <div className="mt-1 text-xs text-muted-foreground">{description}</div>
      </div>
      <Switch checked={checked} onCheckedChange={onCheckedChange} />
    </div>
  );
}
