# OpenXFlow Channel Gateway Routing

OpenXFlow uses one provider-neutral routing model for Telegram, Feishu, DingTalk, and Enterprise WeChat. Provider adapters normalize platform events; the channel service owns discovery, identity resolution, routing, permissions, file handling, and execution history.

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
| Enterprise WeChat | `private` |

The platform conversation ID and type are discovered values and are read-only in the settings UI. Historical manually entered records are labeled separately so administrators can distinguish them from provider-discovered conversations and replace them after the real platform conversation appears.

## Default routing

A channel connection can define:

- a global default workflow;
- a global default knowledge base;
- automatic conversation discovery;
- behavior when no workflow is configured;
- default group-response and file-upload policies;
- whether bound users may create personal commands.

Each discovered conversation uses one of three route modes:

- `inherit`: use the connection default workflow;
- `override`: use the conversation workflow;
- `disabled`: do not execute a workflow for ordinary messages.

Conversation states include `pending`, `inherited`, `overridden`, `ignored`, `disabled`, and `unavailable`.

## Custom commands

A message in the following form executes the workflow associated with the command for that message only:

```text
/code review this change
```

It does not replace the conversation default workflow.

Supported command scopes are:

1. `identity_conversation` — personal command in one conversation;
2. `conversation_shared` — shared command in one conversation;
3. `identity_connection` — personal command across the connection;
4. `connection_shared` — shared command across the connection.

The same order is used as the resolution priority. A command may define aliases, a prompt template, required input, attachment policy, group mention policy, and an enabled state.

Public system commands are intentionally limited to:

```text
/help
/bind
/commands
```

`/flow` remains an owner or superuser diagnostic command and is not advertised. `/run` is no longer a system command.

## Files and knowledge bases

A conversation-specific knowledge base takes precedence over the connection default knowledge base. Files are persisted first, then ingested when an effective knowledge base is available and the bound user has ingestion permission.

## Paginated management APIs

Large collections are server-paginated:

- conversations;
- identities;
- custom commands;
- execution logs;
- workflow options;
- knowledge-base options.

The default page size is 20 and the maximum is 100. Conversation endpoints support search, provider-type filtering, route-state filtering, and sorting by recent activity.

## Settings UI

Each channel connection exposes the same tabs:

- Overview
- Default routing
- Conversations
- Commands
- Accounts
- Execution logs

Provider capability metadata controls which conversation types and feature settings appear. This keeps the product model consistent while preserving provider-specific behavior. Channel management labels, dialogs, filters, empty states, pagination controls, and validation messages use the existing localization layer so Chinese and English interfaces remain consistent.

## Database migrations

Run both channel routing migrations before enabling the updated UI and command routing:

```text
b9f2d7e6c4a1
c0a3e8f7d5b2
```

The first migration adds connection and conversation routing/discovery fields. The second adds custom command and execution audit tables. Apply both migrations and restart the backend before beginning provider-level manual acceptance.
