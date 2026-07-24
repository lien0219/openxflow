import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
  type ChannelConnection,
  type ChannelProviderCapabilities,
  type ChannelUnconfiguredBehavior,
  useUpdateChannelConnection,
} from "@/controllers/API/queries/channels";
import useAlertStore from "@/stores/alertStore";
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
  defaultResponseMode: string;
  defaultAllowFileUpload: boolean;
}

export default function DefaultRoutingTab({
  connection,
  capabilities,
}: DefaultRoutingTabProps) {
  const setSuccessData = useAlertStore((state) => state.setSuccessData);
  const setErrorData = useAlertStore((state) => state.setErrorData);
  const updateConnection = useUpdateChannelConnection();
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
          default_response_mode: form.defaultResponseMode,
          default_allow_file_upload: form.defaultAllowFileUpload,
        },
      });
      setSuccessData({ title: "默认路由设置已保存" });
    } catch (error) {
      setErrorData({
        title: "默认路由保存失败",
        list: [error instanceof Error ? error.message : String(error)],
      });
    }
  };

  return (
    <div className="flex flex-col gap-5 rounded-xl border p-5">
      <div>
        <h3 className="font-semibold">连接默认路由</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          没有单独覆盖的私聊或群聊会继承这里配置的工作流和知识库。
        </p>
      </div>

      <ChannelResourceSelect
        kind="flow"
        label="全局默认工作流"
        emptyLabel="不设置全局默认工作流"
        value={form.defaultFlowId}
        onChange={(value) =>
          setForm((current) => ({ ...current, defaultFlowId: value }))
        }
      />

      <ChannelResourceSelect
        kind="knowledge-base"
        label="全局默认知识库"
        emptyLabel="不设置全局默认知识库"
        value={form.defaultKnowledgeBaseId}
        onChange={(value) =>
          setForm((current) => ({
            ...current,
            defaultKnowledgeBaseId: value,
          }))
        }
      />

      <label className="flex flex-col gap-2 text-sm font-medium">
        没有可用默认工作流时
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
          <option value="notify_pending">首次提示待配置</option>
          <option value="ignore">静默忽略</option>
          <option value="use_global_default">优先使用全局默认工作流</option>
        </select>
      </label>

      <div className="grid gap-3 md:grid-cols-2">
        <SettingSwitch
          title="自动发现会话"
          description="收到新私聊或群聊消息时自动记录真实平台会话 ID。"
          checked={form.autoDiscoverConversations}
          onCheckedChange={(checked) =>
            setForm((current) => ({
              ...current,
              autoDiscoverConversations: checked,
            }))
          }
        />
        <SettingSwitch
          title="待配置提示"
          description="无默认工作流时向会话发送一次配置提示。"
          checked={form.pendingNoticeEnabled}
          onCheckedChange={(checked) =>
            setForm((current) => ({
              ...current,
              pendingNoticeEnabled: checked,
            }))
          }
        />
        <SettingSwitch
          title="允许个人指令"
          description="绑定用户可创建仅对自己生效的工作流指令。"
          checked={form.personalCommandsEnabled}
          onCheckedChange={(checked) =>
            setForm((current) => ({
              ...current,
              personalCommandsEnabled: checked,
            }))
          }
        />
        {capabilities?.supports_file_upload && (
          <SettingSwitch
            title="默认允许文件上传"
            description="新发现会话默认允许接收和处理文件。"
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

      {capabilities?.supports_group_chat &&
        capabilities.supports_mentions && (
          <label className="flex flex-col gap-2 text-sm font-medium">
            新群聊默认响应模式
            <select
              className="primary-input h-10"
              value={form.defaultResponseMode}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  defaultResponseMode: event.target.value,
                }))
              }
            >
              <option value="mentions_only">仅 @机器人或指令时响应</option>
              <option value="all_messages">响应所有消息</option>
            </select>
          </label>
        )}

      <div className="flex justify-end">
        <Button
          variant="primary"
          onClick={handleSave}
          loading={updateConnection.isPending}
        >
          保存默认路由
        </Button>
      </div>
    </div>
  );
}

function formFromConnection(
  connection: ChannelConnection,
): RoutingFormState {
  return {
    defaultFlowId: connection.default_flow_id ?? "",
    defaultKnowledgeBaseId: connection.default_knowledge_base_id ?? "",
    autoDiscoverConversations: connection.auto_discover_conversations,
    unconfiguredBehavior: connection.unconfigured_behavior,
    pendingNoticeEnabled: connection.pending_notice_enabled,
    personalCommandsEnabled: connection.personal_commands_enabled,
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
