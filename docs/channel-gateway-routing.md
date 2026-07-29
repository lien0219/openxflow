# OpenXFlow Channel Gateway Routing

OpenXFlow uses one provider-neutral routing model for Telegram, Feishu, DingTalk, and Enterprise WeChat. Provider adapters normalize platform events; the channel service owns discovery, identity resolution, routing, permissions, file handling, workflow selection, and execution history.

## Conversation discovery

When a supported provider sends an event, OpenXFlow records or refreshes the conversation before applying group-response filters. The unique identity is:

```text
connection_id + external_conversation_id
```

Provider conversation types are normalized as follows:

| Provider | Conversation types |
| --- | --- |
| Telegram | `private`, `group`, `supergroup`, `channel` |
| Feishu | `private`, `group` |
| DingTalk | `private`, `group` |
| Enterprise WeChat | `private`, `group` when supported by the configured mode |

The platform conversation ID and type are discovered values and are read-only in the settings UI. Historical manually entered records are labeled separately so administrators can distinguish them from provider-discovered conversations and replace them after the real platform conversation appears. Only records labeled as historical manual entries can be permanently deleted; provider-discovered conversations use ignore or disable actions instead.

## Default routing

A channel connection can define:

- a global default workflow;
- a global default knowledge base;
- automatic conversation discovery;
- behavior when no workflow is configured;
- default group-response and file-upload policies;
- whether bound users may create personal commands;
- whether members may persistently select an allowed workflow;
- how long a persistent workflow selection remains valid.

Each discovered conversation uses one of three route modes:

- `inherit`: use the connection default workflow;
- `override`: use the conversation workflow;
- `disabled`: do not execute a workflow for ordinary messages.

Conversation states include `pending`, `inherited`, `overridden`, `ignored`, `disabled`, and `unavailable`.

The ordinary-message routing priority is:

1. a valid active workflow selected by the current channel identity in the current conversation and thread;
2. the conversation override workflow;
3. the connection default workflow;
4. the configured unconfigured-route behavior.

Before invoking a workflow, the dispatcher commits conversation discovery and the running execution record. The workflow job service uses a separate database session, so this boundary prevents a pending channel write from blocking job creation on local SQLite databases. The final execution status is committed after the workflow finishes.

## Custom commands

A message in the following form executes the workflow associated with the command for that message only:

```text
/code review this change
```

An explicit custom command never changes the member's persistent workflow selection.

Supported command scopes are:

1. `identity_conversation` — personal command in one conversation;
2. `conversation_shared` — shared command in one conversation;
3. `identity_connection` — personal command across the connection;
4. `connection_shared` — shared command across the connection.

The same order is used as the resolution priority. A command may define aliases, a prompt template, required input, attachment policy, group mention policy, an enabled state, and whether users may set it as their current workflow.

## Persistent workflow selection

Administrators enable user workflow selection in the connection's Default routing settings and explicitly mark eligible commands with **Allow as current workflow**. The default is fail-closed: existing commands remain single-use until an administrator opts them in.

Users switch and inspect their current workflow with:

```text
/use-flow /summary
/current-flow
/use-flow default
```

Chinese aliases `/切换工作流` and `/当前工作流` are also supported.

A durable selection is keyed by:

```text
connection_id
+ conversation_binding_id
+ channel_identity_id
+ conversation_scope_id
```

This keeps private chats, groups, members, Feishu threads, and Telegram topics independent. Unbound members may select shared commands under `shared` or `hybrid` access policies. Personal commands still require a bound OpenXFlow account.

Every ordinary message revalidates the selected command against its enabled state, current scope, ownership, access policy, and expiry. Invalid selections are removed and the message falls back to the existing default route. Deleting a command or channel identity removes dependent selections through database foreign keys.

Shared selections execute with the channel service identity. Personal selections execute with the bound user identity. The selection record never stores or grants an execution principal.

## Workflow context isolation

The channel workflow session identifier includes the effective workflow key in addition to provider, connection, conversation, thread, and member/shared context dimensions. Switching between summary, translation, and knowledge workflows therefore creates independent workflow memory sessions.

Group shared-context reads are also filtered by `session_id`, backed by the composite index:

```text
conversation_binding_id + session_id + created_at
```

The durable FIFO queue key intentionally does not include the workflow ID. This preserves strict ordering between `/use-flow` and the ordinary message that follows it.

## System commands

Public and policy-controlled system commands include:

```text
/help
/bind
/commands
/whoami
/files
/knowledge
/use-flow
/current-flow
```

Administrative commands include `/flow`, `/use-kb`, and `/status`. `/flow` remains a one-shot owner or superuser diagnostic command and does not modify the current workflow. `/run` is not a system command.

## Files and knowledge bases

A conversation-specific knowledge base takes precedence over the connection default knowledge base. Files are persisted first, then ingested when an effective knowledge base is available and the execution identity has the required permission.

Ordinary attachment uploads continue through the file and knowledge-base pipeline. Persistently selecting a workflow does not automatically pass raw attachments to that workflow; attachment-to-active-workflow routing is a separate capability.

## Execution records and management APIs

Executions triggered through a persistent selection use `trigger_type=selected` and record the command ID, active selection ID, and selection scope alongside the effective workflow and execution identity.

Large collections are server-paginated, including:

- conversations;
- identities;
- custom commands;
- active workflow selections;
- execution logs;
- workflow options;
- knowledge-base options.

Active-selection management APIs are:

```text
GET    /channels/{connection_id}/flow-selections
DELETE /channels/{connection_id}/flow-selections/{selection_id}
POST   /channels/{connection_id}/flow-selections/cleanup
```

The Commands tab exposes the same administration flow: view active member selections, resolve their command, conversation and thread, revoke one selection, or clean up expired selections.

## Settings UI

Each channel connection exposes the same tabs:

- Overview
- Default routing
- Conversations
- Commands
- Accounts
- Messages
- Deliveries
- Execution logs
- Audit

Provider capability metadata controls which conversation types and feature settings appear. This keeps the product model consistent while preserving provider-specific behavior. Channel management labels, dialogs, filters, empty states, pagination controls, and validation messages use the existing localization layer so Chinese and English interfaces remain consistent.

## Runtime compatibility

Channel routing models remain importable on the repository's supported Python matrix. Models and migrations are compatible with SQLite for local single-process acceptance and PostgreSQL for production deployments. Selection state is database-backed and survives backend restarts.

## Database migrations

Apply the complete channel routing migration chain before enabling the updated UI and command routing. The persistent workflow selection schema is introduced by:

```text
a1f4c7e9d2b6
```

It follows `b5d8e1f3a6c9`, adds the active-selection table, connection and command policy fields, execution audit references, and the workflow-scoped context index. Apply all pending migrations and restart the backend before beginning provider-level manual acceptance.
