type ChannelTranslationMap = Record<string, string>;

const en: ChannelTranslationMap = {
  "settings.nav.channels": "Channel Center",
  "channels.title": "Channel Center",
  "channels.description":
    "Run workflows, query knowledge bases, upload files, and handle interactions from Telegram, Feishu, DingTalk, and WeCom mobile clients.",
  "channels.addConnection": "Add connection",
  "channels.connections": "Channel connections",
  "channels.emptyConnections":
    "No connections yet. Select any available channel above to start configuring it.",
  "channels.selectConnection": "Select a connection to view its configuration.",
  "channels.provider.telegram": "Telegram",
  "channels.provider.feishu": "Feishu",
  "channels.provider.dingtalk": "DingTalk",
  "channels.provider.wecom": "WeCom",
  "channels.provider.available": "Available — click to create",
  "channels.provider.comingSoon": "Coming in a later phase",
  "channels.status.connected": "Connected",
  "channels.status.error": "Error",
  "channels.status.disconnected": "Disconnected",
  "channels.status.configuring": "Not configured",
  "channels.mode.stream": "Stream connection",
  "channels.webhook.feishu": "Feishu event subscription URL",
  "channels.webhook.wecom": "WeCom message server URL",
  "channels.webhook.dingtalk": "DingTalk HTTP callback compatibility URL",
  "channels.webhook.default": "Webhook URL",
  "channels.credentialsConfigured": "Configured credentials: {{keys}}",
  "channels.none": "None",
  "channels.accessMode": "Connection mode: {{mode}}",
  "channels.lastConnected": "Last connected: {{time}}",
  "channels.notTested": "Not tested",
  "channels.instructions.dingtalkStream":
    "In DingTalk Stream mode, the OpenXFlow server initiates and maintains the persistent connection. No public callback URL is required. Testing the connection also verifies that the Stream SDK is installed.",
  "channels.instructions.wecom":
    "Enter the URL below in the WeCom application's Message Receiving Server settings. Token and EncodingAESKey must exactly match this connection, and message encryption must use secure mode.",
  "channels.actions.testConnection": "Test connection",
  "channels.actions.configureWebhook": "Configure Webhook",
  "channels.actions.edit": "Edit",
  "channels.actions.delete": "Delete",
  "channels.actions.bind": "Bind",
  "channels.actions.unbind": "Unbind",
  "channels.actions.addBinding": "Add binding",
  "channels.actions.cancel": "Cancel",
  "channels.actions.saveConnection": "Save connection",
  "channels.actions.createConnection": "Create connection",
  "channels.actions.saveBinding": "Save binding",
  "channels.binding.title": "Bind mobile account",
  "channels.binding.description":
    "Send /bind to the bot in a private chat to receive a binding code, then enter it here to bind the current OpenXFlow account.",
  "channels.binding.placeholder": "Enter binding code",
  "channels.binding.empty": "No account bindings yet.",
  "channels.binding.channelUser":
    "Channel user: {{channelUser}} · OpenXFlow: {{openxflowUser}}",
  "channels.conversations.title": "Conversations and workflows",
  "channels.conversations.description":
    "Configure a default workflow, knowledge base, and file-upload permission for private chats or groups.",
  "channels.conversations.empty":
    "A basic conversation record is also created automatically when the bot receives a message or file from a bound user.",
  "channels.conversations.conversationId": "{{type}} · Conversation ID: {{id}}",
  "channels.conversations.summary":
    "Workflow: {{flow}} · Knowledge base: {{knowledgeBase}} · File upload: {{fileUpload}}",
  "channels.conversations.unbound": "Not bound",
  "channels.conversations.fileAllowed": "Allowed",
  "channels.conversations.fileDisabled": "Disabled",
  "channels.deleteFallback": "Channel configuration",
  "channels.toast.telegramConfigured":
    "Telegram connection and Webhook configured",
  "channels.toast.connectionSaved": "{{name}} connection saved",
  "channels.toast.connectionSaveFailed": "Failed to save channel connection",
  "channels.toast.connectionSucceeded": "Connection succeeded: {{name}}",
  "channels.toast.connectionTestFailed": "Channel connection test failed",
  "channels.toast.publicUrlRequired": "Enter the public OpenXFlow URL first",
  "channels.toast.publicUrlRequiredDetail":
    "Edit and save the connection; OpenXFlow will configure the Telegram Webhook automatically.",
  "channels.toast.webhookConfigured": "Webhook configured: {{url}}",
  "channels.toast.webhookFailed": "Webhook configuration failed",
  "channels.toast.accountBound": "Channel account bound",
  "channels.toast.bindingCodeFailed": "Failed to redeem binding code",
  "channels.toast.conversationSaved": "Conversation binding saved",
  "channels.toast.conversationSaveFailed":
    "Failed to save conversation binding",
  "channels.toast.connectionDeleted": "Channel connection deleted",
  "channels.toast.accountUnbound": "Channel account unbound",
  "channels.toast.deleteFailed": "Delete failed",
  "channels.error.requestFailed": "Request failed. Please try again later.",
  "channels.connectionDialog.editTitle": "Edit {{provider}} connection",
  "channels.connectionDialog.createTitle": "Add {{provider}} connection",
  "channels.connectionDialog.description":
    "Save application credentials, connection settings, and mobile file-upload limits. Credentials are encrypted and are not shown again after saving.",
  "channels.connectionDialog.name": "Connection name",
  "channels.connectionDialog.namePlaceholder":
    "For example: Production {{provider}}",
  "channels.connectionDialog.channelType": "Channel type",
  "channels.connectionDialog.telegramOption": "Telegram Bot",
  "channels.connectionDialog.feishuOption": "Feishu custom app",
  "channels.connectionDialog.dingtalkOption": "DingTalk internal bot",
  "channels.connectionDialog.wecomOption": "WeCom custom app",
  "channels.connectionDialog.keepToken":
    "Leave blank to keep the configured token",
  "channels.connectionDialog.keepValue":
    "Leave blank to keep the current value",
  "channels.connectionDialog.randomSecret": "Use a random string",
  "channels.connectionDialog.feishuHelp":
    "Feishu event subscriptions can be encrypted. When enabled, Verification Token and Encrypt Key must exactly match the event subscription settings in the Feishu developer console.",
  "channels.connectionDialog.feishuSecret": "Feishu app secret",
  "channels.connectionDialog.verificationTokenPlaceholder":
    "Event subscription Verification Token",
  "channels.connectionDialog.encryptKeyPlaceholder":
    "Optional event subscription Encrypt Key",
  "channels.connectionDialog.dingtalkHelp":
    "DingTalk uses a Stream connection by default and does not require a public callback URL. OpenXFlow maintains the connection and reconnects automatically.",
  "channels.connectionDialog.dingtalkSecret": "DingTalk app secret",
  "channels.connectionDialog.robotCodePlaceholder":
    "Usually the same as Client ID; leave blank to use Client ID",
  "channels.connectionDialog.wecomHelp":
    "WeCom requires an HTTPS callback and uses Token and EncodingAESKey for signature verification and AES decryption.",
  "channels.connectionDialog.corpId": "Enterprise ID (CorpID)",
  "channels.connectionDialog.agentId": "Application AgentID",
  "channels.connectionDialog.corpSecret": "Application Secret",
  "channels.connectionDialog.corpSecretPlaceholder": "WeCom application Secret",
  "channels.connectionDialog.callbackToken": "Callback Token",
  "channels.connectionDialog.callbackTokenPlaceholder": "WeCom callback Token",
  "channels.connectionDialog.encodingKeyPlaceholder":
    "43-character EncodingAESKey",
  "channels.connectionDialog.publicUrl": "Public OpenXFlow URL",
  "channels.connectionDialog.publicUrlStreamHelp":
    "Stream mode does not require this URL. Enter it only when using a signed HTTP callback.",
  "channels.connectionDialog.publicUrlWecomHelp":
    "WeCom requires a publicly accessible HTTPS URL for the message receiving server.",
  "channels.connectionDialog.publicUrlHelp":
    "This must be a publicly accessible HTTPS URL. The platform callback URL is generated after saving.",
  "channels.connectionDialog.maxFileSize": "Maximum file size (MB)",
  "channels.connectionDialog.allowedExtensions": "Allowed extensions",
  "channels.connectionDialog.enable": "Enable connection",
  "channels.connectionDialog.enableHelp":
    "When disabled, OpenXFlow stops receiving messages, running workflows, and parsing files for this connection.",
  "channels.conversationDialog.editTitle": "Edit conversation binding",
  "channels.conversationDialog.createTitle": "Add conversation binding",
  "channels.conversationDialog.description":
    "Bind a private chat or group to a default workflow and knowledge base so users can ask questions and upload files from mobile clients.",
  "channels.conversationDialog.chatId": "Channel conversation ID",
  "channels.conversationDialog.chatIdPlaceholder":
    "For example: -1001234567890",
  "channels.conversationDialog.type": "Conversation type",
  "channels.conversationDialog.private": "Private chat",
  "channels.conversationDialog.group": "Group",
  "channels.conversationDialog.supergroup": "Supergroup",
  "channels.conversationDialog.channel": "Channel",
  "channels.conversationDialog.displayName": "Display name",
  "channels.conversationDialog.displayNamePlaceholder":
    "For example: Engineering project group",
  "channels.conversationDialog.defaultWorkflow": "Default workflow",
  "channels.conversationDialog.noWorkflow": "No default workflow",
  "channels.conversationDialog.defaultKnowledgeBase": "Default knowledge base",
  "channels.conversationDialog.noKnowledgeBase": "No knowledge base",
  "channels.conversationDialog.chunks": "{{count}} chunks",
  "channels.conversationDialog.responseMode": "Group response mode",
  "channels.conversationDialog.mentionsOnly": "Only @mentions or commands",
  "channels.conversationDialog.allMessages": "Process all messages",
  "channels.conversationDialog.allowUpload": "Allow mobile file uploads",
  "channels.conversationDialog.allowUploadHelp":
    "Files are saved to the user's file area. If a knowledge base is bound, files are also parsed and ingested automatically.",
};

const zhHans: ChannelTranslationMap = {
  "settings.nav.channels": "渠道中心",
  "channels.title": "渠道中心",
  "channels.description":
    "在 Telegram、飞书、钉钉和企业微信移动端运行工作流、查询知识库、上传文件并处理互动操作。",
  "channels.addConnection": "新增连接",
  "channels.connections": "渠道连接",
  "channels.emptyConnections":
    "尚未创建连接。可从上方选择任一已开放渠道开始配置。",
  "channels.selectConnection": "选择一个连接查看配置详情。",
  "channels.provider.telegram": "Telegram",
  "channels.provider.feishu": "飞书",
  "channels.provider.dingtalk": "钉钉",
  "channels.provider.wecom": "企业微信",
  "channels.provider.available": "已开放，点击创建",
  "channels.provider.comingSoon": "后续阶段接入",
  "channels.status.connected": "已连接",
  "channels.status.error": "异常",
  "channels.status.disconnected": "已断开",
  "channels.status.configuring": "待配置",
  "channels.mode.stream": "Stream 长连接",
  "channels.webhook.feishu": "飞书事件订阅地址",
  "channels.webhook.wecom": "企业微信接收消息服务器 URL",
  "channels.webhook.dingtalk": "钉钉 HTTP 回调兼容地址",
  "channels.webhook.default": "Webhook 地址",
  "channels.credentialsConfigured": "已配置凭证：{{keys}}",
  "channels.none": "无",
  "channels.accessMode": "接入方式：{{mode}}",
  "channels.lastConnected": "最近连接：{{time}}",
  "channels.notTested": "尚未测试",
  "channels.instructions.dingtalkStream":
    "钉钉 Stream 模式由 OpenXFlow 服务端主动建立长连接，不需要配置公网回调地址。测试连接会同时检查服务器是否安装 Stream SDK。",
  "channels.instructions.wecom":
    "将下方 URL 填入企业微信应用“接收消息服务器”。Token 和 EncodingAESKey 必须与渠道连接中填写的值完全一致，消息加密模式请选择安全模式。",
  "channels.actions.testConnection": "测试连接",
  "channels.actions.configureWebhook": "配置 Webhook",
  "channels.actions.edit": "编辑",
  "channels.actions.delete": "删除",
  "channels.actions.bind": "绑定",
  "channels.actions.unbind": "解绑",
  "channels.actions.addBinding": "新增绑定",
  "channels.actions.cancel": "取消",
  "channels.actions.saveConnection": "保存连接",
  "channels.actions.createConnection": "创建连接",
  "channels.actions.saveBinding": "保存绑定",
  "channels.binding.title": "绑定手机账号",
  "channels.binding.description":
    "用户私聊机器人发送 /bind 后，将收到绑定码；在此输入即可绑定当前登录账号。",
  "channels.binding.placeholder": "输入绑定码",
  "channels.binding.empty": "还没有账号绑定记录。",
  "channels.binding.channelUser":
    "渠道用户：{{channelUser}} · OpenXFlow：{{openxflowUser}}",
  "channels.conversations.title": "会话与工作流",
  "channels.conversations.description":
    "为私聊或群聊配置默认工作流、知识库以及文件上传权限。",
  "channels.conversations.empty":
    "机器人收到已绑定用户的消息或文件后，也会自动创建基础会话记录。",
  "channels.conversations.conversationId": "{{type}} · 会话 ID：{{id}}",
  "channels.conversations.summary":
    "工作流：{{flow}} · 知识库：{{knowledgeBase}} · 文件上传：{{fileUpload}}",
  "channels.conversations.unbound": "未绑定",
  "channels.conversations.fileAllowed": "允许",
  "channels.conversations.fileDisabled": "关闭",
  "channels.deleteFallback": "渠道配置",
  "channels.toast.telegramConfigured": "Telegram 连接与 Webhook 已配置",
  "channels.toast.connectionSaved": "{{name}}连接已保存",
  "channels.toast.connectionSaveFailed": "保存渠道连接失败",
  "channels.toast.connectionSucceeded": "连接成功：{{name}}",
  "channels.toast.connectionTestFailed": "渠道连接测试失败",
  "channels.toast.publicUrlRequired": "请先填写 OpenXFlow 公开地址",
  "channels.toast.publicUrlRequiredDetail":
    "编辑连接后保存，系统会自动配置 Telegram Webhook。",
  "channels.toast.webhookConfigured": "Webhook 已配置：{{url}}",
  "channels.toast.webhookFailed": "Webhook 配置失败",
  "channels.toast.accountBound": "渠道账号绑定成功",
  "channels.toast.bindingCodeFailed": "绑定码兑换失败",
  "channels.toast.conversationSaved": "会话绑定已保存",
  "channels.toast.conversationSaveFailed": "保存会话绑定失败",
  "channels.toast.connectionDeleted": "渠道连接已删除",
  "channels.toast.accountUnbound": "渠道账号已解除绑定",
  "channels.toast.deleteFailed": "删除失败",
  "channels.error.requestFailed": "请求失败，请稍后重试。",
  "channels.connectionDialog.editTitle": "编辑{{provider}}连接",
  "channels.connectionDialog.createTitle": "新增{{provider}}连接",
  "channels.connectionDialog.description":
    "保存应用凭证、接入方式以及手机文件上传限制。凭证加密存储，保存后不会回显。",
  "channels.connectionDialog.name": "连接名称",
  "channels.connectionDialog.namePlaceholder": "例如：生产环境{{provider}}",
  "channels.connectionDialog.channelType": "渠道类型",
  "channels.connectionDialog.telegramOption": "Telegram Bot",
  "channels.connectionDialog.feishuOption": "飞书自建应用",
  "channels.connectionDialog.dingtalkOption": "钉钉企业内部机器人",
  "channels.connectionDialog.wecomOption": "企业微信自建应用",
  "channels.connectionDialog.keepToken": "留空保留已配置 Token",
  "channels.connectionDialog.keepValue": "留空保留原值",
  "channels.connectionDialog.randomSecret": "建议设置随机字符串",
  "channels.connectionDialog.feishuHelp":
    "飞书事件订阅可启用加密。启用后，Verification Token 和 Encrypt Key 必须与飞书开放平台中的事件订阅配置完全一致。",
  "channels.connectionDialog.feishuSecret": "飞书应用密钥",
  "channels.connectionDialog.verificationTokenPlaceholder":
    "事件订阅 Verification Token",
  "channels.connectionDialog.encryptKeyPlaceholder":
    "可选，事件订阅 Encrypt Key",
  "channels.connectionDialog.dingtalkHelp":
    "钉钉默认使用 Stream 长连接，不需要公网回调地址。服务会自动维护连接并在断线后重连。",
  "channels.connectionDialog.dingtalkSecret": "钉钉应用密钥",
  "channels.connectionDialog.robotCodePlaceholder":
    "通常与 Client ID 相同，留空自动使用 Client ID",
  "channels.connectionDialog.wecomHelp":
    "企业微信要求使用 HTTPS 回调，并使用 Token 与 EncodingAESKey 对回调进行签名校验和 AES 解密。",
  "channels.connectionDialog.corpId": "企业 ID（CorpID）",
  "channels.connectionDialog.agentId": "应用 AgentID",
  "channels.connectionDialog.corpSecret": "应用 Secret",
  "channels.connectionDialog.corpSecretPlaceholder": "企业微信应用 Secret",
  "channels.connectionDialog.callbackToken": "回调 Token",
  "channels.connectionDialog.callbackTokenPlaceholder": "企业微信回调 Token",
  "channels.connectionDialog.encodingKeyPlaceholder": "43 位 EncodingAESKey",
  "channels.connectionDialog.publicUrl": "OpenXFlow 公开地址",
  "channels.connectionDialog.publicUrlStreamHelp":
    "Stream 模式不需要该地址；仅在启用签名 HTTP 回调时填写。",
  "channels.connectionDialog.publicUrlWecomHelp":
    "企业微信必须配置外网可访问的 HTTPS 地址，用于保存接收消息服务器。",
  "channels.connectionDialog.publicUrlHelp":
    "必须是外网可访问的 HTTPS 地址，保存后会生成平台回调地址。",
  "channels.connectionDialog.maxFileSize": "单文件大小限制（MB）",
  "channels.connectionDialog.allowedExtensions": "允许的扩展名",
  "channels.connectionDialog.enable": "启用连接",
  "channels.connectionDialog.enableHelp":
    "关闭后停止接收消息、运行工作流和解析文件。",
  "channels.conversationDialog.editTitle": "编辑会话绑定",
  "channels.conversationDialog.createTitle": "新增会话绑定",
  "channels.conversationDialog.description":
    "将私聊或群聊绑定到默认工作流和知识库，用户可直接在手机端提问和上传资料。",
  "channels.conversationDialog.chatId": "渠道会话 ID",
  "channels.conversationDialog.chatIdPlaceholder": "例如：-1001234567890",
  "channels.conversationDialog.type": "会话类型",
  "channels.conversationDialog.private": "私聊",
  "channels.conversationDialog.group": "群聊",
  "channels.conversationDialog.supergroup": "超级群组",
  "channels.conversationDialog.channel": "频道",
  "channels.conversationDialog.displayName": "显示名称",
  "channels.conversationDialog.displayNamePlaceholder": "例如：研发项目群",
  "channels.conversationDialog.defaultWorkflow": "默认工作流",
  "channels.conversationDialog.noWorkflow": "不绑定默认工作流",
  "channels.conversationDialog.defaultKnowledgeBase": "默认知识库",
  "channels.conversationDialog.noKnowledgeBase": "不绑定知识库",
  "channels.conversationDialog.chunks": "{{count}} 个分块",
  "channels.conversationDialog.responseMode": "群聊响应模式",
  "channels.conversationDialog.mentionsOnly": "仅 @机器人或命令",
  "channels.conversationDialog.allMessages": "处理全部消息",
  "channels.conversationDialog.allowUpload": "允许手机上传文件",
  "channels.conversationDialog.allowUploadHelp":
    "开启后文件会保存到用户文件区；绑定知识库时还会自动解析入库。",
};

export const channelTranslations: Record<string, ChannelTranslationMap> = {
  en,
  "zh-Hans": zhHans,
};
