import { useCallback } from "react";
import { useTranslation } from "react-i18next";

type CopyParams = Record<string, string | number>;

const ENGLISH_COPY: Record<string, string> = {
  "搜索渠道用户名称或渠道用户 ID":
    "Search channel user name or channel user ID",
  "共 {{count}} 个绑定账号": "{{count}} linked accounts",
  "{{count}} 条": "{{count}} per page",
  上一页: "Previous",
  下一页: "Next",
  搜索: "Search {{label}}",
  "正在加载…": "Loading…",
  "当前已选择 · {{id}}": "Currently selected · {{id}}",
  "{{count}} 个分块": "{{count}} chunks",
  "连接共享：所有用户和会话可用":
    "Connection shared: available to all users and conversations",
  "会话共享：指定会话所有用户可用":
    "Conversation shared: available to all users in the selected conversation",
  "我的连接指令：仅自己在当前连接可用":
    "My connection command: available only to me on this connection",
  "我的会话指令：仅自己在指定会话可用":
    "My conversation command: available only to me in the selected conversation",
  编辑指令: "Edit command",
  新增自定义指令: "Create custom command",
  "用户发送“/指令 内容”时，仅本次消息路由到指定工作流，不会改变默认工作流。":
    "When a user sends “/command content”, only that message is routed to the selected workflow. The default workflow is unchanged.",
  指令名称: "Command name",
  "/code 或 /代码审查": "/code or /review",
  "支持中文、英文、数字、-、_，最多 32 个字符。":
    "Supports Chinese, English, numbers, hyphens, and underscores, up to 32 characters.",
  别名: "Aliases",
  "/review, /检查代码": "/review, /check-code",
  "使用逗号或空格分隔，最多 5 个。":
    "Separate with commas or spaces, up to 5 aliases.",
  指令说明: "Command description",
  "用于 /commands 列表和无参数提示":
    "Shown in /commands and missing-input prompts",
  生效范围: "Scope",
  指定会话: "Conversation",
  "先搜索会话名称或平台会话 ID":
    "Search by conversation name or platform conversation ID",
  请选择会话: "Select a conversation",
  目标工作流: "Target workflow",
  请选择工作流: "Select a workflow",
  "输入模板（可选）": "Input template (optional)",
  "请按代码审查标准处理以下内容：\n{{input}}\n\n发送人：{{sender_name}}":
    "Review the following content using code review standards:\n{{input}}\n\nSender: {{sender_name}}",
  支持模板变量: "Supports template variables",
  必须输入参数: "Require input",
  "只有指令没有正文或附件时显示用法，不执行工作流。":
    "Show usage instead of running the workflow when the command has no text or attachment.",
  允许附件: "Allow attachments",
  "允许图片和文件随指令一起提交给工作流。":
    "Allow images and files to be submitted with the command.",
  "群聊必须 @机器人": "Require @mention in groups",
  "在群聊使用此指令时仍要求明确提及机器人。":
    "Require an explicit bot mention when using this command in a group.",
  启用指令: "Enable command",
  "关闭后保留配置，但不再匹配和展示。":
    "Keep the configuration but stop matching and displaying the command.",
  取消: "Cancel",
  保存指令: "Save command",
  连接共享: "Connection shared",
  会话共享: "Conversation shared",
  我的连接指令: "My connection command",
  我的会话指令: "My conversation command",
  自定义指令已创建: "Custom command created",
  创建指令失败: "Failed to create command",
  自定义指令已更新: "Custom command updated",
  更新指令失败: "Failed to update command",
  自定义指令已删除: "Custom command deleted",
  删除指令失败: "Failed to delete command",
  自定义指令中心: "Custom commands",
  "普通消息使用默认工作流；“/指令 内容”仅本次路由到指定工作流。":
    "Normal messages use the default workflow; “/command content” routes only that message to the selected workflow.",
  新增指令: "New command",
  搜索指令名称或说明: "Search command name or description",
  全部作用域: "All scopes",
  "暂无匹配指令。可创建连接共享、会话共享或仅自己可用的个人指令。":
    "No matching commands. Create connection-shared, conversation-shared, or personal commands.",
  指令: "Command",
  作用域: "Scope",
  工作流: "Workflow",
  策略: "Policy",
  最近使用: "Last used",
  操作: "Actions",
  无说明: "No description",
  别名列表: "Aliases: {{aliases}}",
  已启用: "Enabled",
  已停用: "Disabled",
  必须输入: "Require input",
  "群聊需@": "Group @ required",
  尚未使用: "Never used",
  编辑: "Edit",
  删除: "Delete",
  "共 {{count}} 条指令": "{{count}} commands",
  "会话由渠道消息自动发现，平台会话 ID 和会话类型不可手工修改。":
    "Conversations are discovered from channel messages. Platform conversation IDs and types cannot be edited manually.",
  默认路由方式: "Default routing mode",
  继承渠道连接默认工作流: "Inherit the connection default workflow",
  使用此会话独立工作流: "Use a workflow specific to this conversation",
  禁用普通消息工作流: "Disable normal-message workflows",
  忽略当前会话: "Ignore this conversation",
  "开启后保留会话记录和配置，但机器人不再响应此会话。":
    "Keep the conversation record and settings, but stop the bot from responding in this conversation.",
  待配置: "Pending configuration",
  继承全局: "Inherit global settings",
  独立配置: "Custom routing",
  已忽略: "Ignored",
  不可访问: "Unavailable",
  请选择批量覆盖工作流: "Select a workflow for batch override",
  "批量设置独立工作流前必须选择目标工作流。":
    "Select a target workflow before applying a batch workflow override.",
  "已更新 {{count}} 个会话": "Updated {{count}} conversations",
  批量更新会话失败: "Failed to update conversations",
  会话管理: "Conversation management",
  "会话由渠道消息自动发现，平台会话 ID 和类型只读，不再手工新增。":
    "Conversations are discovered automatically from channel messages. Platform conversation IDs and types are read-only.",
  搜索会话名称或平台会话ID:
    "Search conversation name or platform conversation ID",
  全部会话类型: "All conversation types",
  全部状态: "All statuses",
  全部路由方式: "All routing modes",
  禁用普通消息: "Disable normal messages",
  "已选择 {{count}} 个会话": "{{count}} conversations selected",
  改为继承全局: "Inherit global settings",
  设置独立工作流: "Set custom workflow",
  忽略会话: "Ignore conversations",
  恢复会话: "Restore conversations",
  停用会话: "Disable conversations",
  启用并继承全局: "Enable and inherit global settings",
  应用: "Apply",
  取消选择: "Clear selection",
  批量覆盖工作流: "Batch workflow override",
  请选择目标工作流: "Select a target workflow",
  "暂无匹配会话。用户或群聊第一次给机器人发消息后会自动出现在这里。":
    "No matching conversations. A user or group appears here after sending the bot its first message.",
  选择当前页全部会话: "Select all conversations on this page",
  会话: "Conversation",
  类型: "Type",
  状态: "Status",
  路由: "Routing",
  最近活跃: "Last active",
  "选择 {{name}}": "Select {{name}}",
  "共 {{count}} 个会话": "{{count}} conversations",
  普通消息已停用: "Normal messages disabled",
  "独立工作流 · {{id}}": "Custom workflow · {{id}}",
  独立工作流未设置: "Custom workflow not set",
  "继承全局 · {{id}}": "Inherit global · {{id}}",
  继承全局但未设置: "Inherit global, but no workflow is set",
  历史手工记录: "Historical manual record",
  默认路由设置已保存: "Default routing settings saved",
  默认路由保存失败: "Failed to save default routing settings",
  连接默认路由: "Connection default routing",
  "没有单独覆盖的私聊或群聊会继承这里配置的工作流和知识库。":
    "Private and group conversations without overrides inherit the workflow and knowledge base configured here.",
  全局默认工作流: "Global default workflow",
  不设置全局默认工作流: "No global default workflow",
  全局默认知识库: "Global default knowledge base",
  不设置全局默认知识库: "No global default knowledge base",
  没有可用默认工作流时: "When no default workflow is available",
  首次提示待配置: "Notify once that configuration is required",
  静默忽略: "Ignore silently",
  优先使用全局默认工作流: "Prefer the global default workflow",
  自动发现会话: "Auto-discover conversations",
  "收到新私聊或群聊消息时自动记录真实平台会话 ID。":
    "Record the real platform conversation ID when a new private or group message arrives.",
  待配置提示: "Pending-configuration notice",
  "无默认工作流时向会话发送一次配置提示。":
    "Send one configuration notice when no default workflow is available.",
  允许个人指令: "Allow personal commands",
  "绑定用户可创建仅对自己生效的工作流指令。":
    "Linked users may create workflow commands that apply only to themselves.",
  默认允许文件上传: "Allow file uploads by default",
  "新发现会话默认允许接收和处理文件。":
    "Newly discovered conversations may receive and process files by default.",
  新群聊默认响应模式: "Default response mode for new group conversations",
  "仅 @机器人或指令时响应": "Respond only to @mentions or commands",
  响应所有消息: "Respond to all messages",
  保存默认路由: "Save default routing",
  默认工作流: "Default workflow",
  自定义指令: "Custom command",
  管理员调试: "Administrator debug",
  文件处理: "File processing",
  执行中: "Running",
  成功: "Succeeded",
  失败: "Failed",
  渠道运行记录: "Channel execution logs",
  "查看默认路由、指令路由和管理员调试触发的工作流执行结果。":
    "Review workflow executions triggered by default routing, command routing, and administrator debugging.",
  全部执行状态: "All execution statuses",
  全部触发方式: "All trigger types",
  当前筛选条件下暂无运行记录: "No execution logs match the current filters.",
  时间: "Time",
  触发方式: "Trigger",
  "会话 / 用户": "Conversation / user",
  耗时: "Duration",
  错误: "Error",
  工作流已删除: "Workflow deleted",
  "会话：{{id}}": "Conversation: {{id}}",
  "用户：{{id}}": "User: {{id}}",
  "共 {{count}} 条记录": "{{count}} records",
  概览: "Overview",
  默认路由: "Default routing",
  账号: "Accounts",
  运行记录: "Execution logs",
  飞书: "Feishu",
  钉钉: "DingTalk",
  企业微信: "WeCom",
};

function interpolate(template: string, params?: CopyParams): string {
  if (!params) return template;
  return Object.entries(params).reduce(
    (result, [key, value]) => result.replaceAll(`{{${key}}}`, String(value)),
    template,
  );
}

export function resolveChannelCopy(
  language: string,
  source: string,
  params?: CopyParams,
): string {
  const isChinese = language.toLowerCase().startsWith("zh");
  return interpolate(
    isChinese ? source : (ENGLISH_COPY[source] ?? source),
    params,
  );
}

export default function useChannelCopy() {
  const { i18n } = useTranslation();
  const language = i18n.resolvedLanguage ?? i18n.language;

  return useCallback(
    (source: string, params?: CopyParams) =>
      resolveChannelCopy(language, source, params),
    [language],
  );
}
