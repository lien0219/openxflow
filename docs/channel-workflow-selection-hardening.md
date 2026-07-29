# Channel Workflow Selection Production Hardening

This document describes the production controls added on top of persistent per-member channel workflow selection.

## Security and routing

- Group system commands can require an explicit bot target.
- Feishu, DingTalk, and Enterprise WeChat group commands use platform mentions.
- Telegram commands in the form `/command@bot_name` are treated as explicitly targeted.
- Private conversations do not require a mention.
- Explicit custom commands remain one-shot and do not replace the member's current workflow.
- Persistent selections are re-authorized before every ordinary message.

The setting is available under **Channel Center → Default routing → Group system commands must mention the bot**. It is enabled by default for mention-capable group providers and stored in connection `settings_data` as `system_command_require_mention`.

## Audit coverage

The channel configuration audit records the following selection lifecycle events:

- user selection or replacement;
- user restore to default;
- expiry;
- command deletion or disablement;
- permission or scope changes;
- administrator revocation;
- administrator cleanup;
- scheduled system cleanup.

Audit payloads contain resource identifiers and routing state, but do not contain provider secrets, model credentials, authorization headers, or decrypted global variables.

## Management query

The active-selection management API returns server-side joined display information:

- member display name and external user ID;
- conversation display name, external conversation ID, and type;
- command, flow ID, workflow name, and endpoint;
- execution identity type;
- selection, last-used, and expiry timestamps.

The endpoint supports server pagination and text search across member, conversation, command, workflow name, and endpoint. The frontend no longer loads the first 100 commands, conversations, and identities to reconstruct rows.

## Lifecycle maintenance

Expired selections are removed in bounded batches by the backend lifecycle task. PostgreSQL workers use `FOR UPDATE SKIP LOCKED`; SQLite remains compatible with the documented single-process local acceptance mode.

Environment variables:

```text
LANGFLOW_CHANNEL_FLOW_SELECTION_CLEANUP_INTERVAL_SECONDS=3600
LANGFLOW_CHANNEL_FLOW_SELECTION_CLEANUP_BATCH_SIZE=500
LANGFLOW_CHANNEL_FLOW_SELECTION_CLEANUP_MAX_BATCHES=20
```

Limits are clamped at runtime:

- interval: 60 seconds to 7 days;
- batch size: 1 to 1000;
- batches per cycle: 1 to 100.

The administrator cleanup endpoint remains available for immediate cleanup.

## Database indexes

Migration `c7e2f4a9b1d3` adds indexes for:

```text
connection_id + expires_at
connection_id + channel_identity_id + updated_at
workflow_command_id + updated_at
```

These complement the existing unique selection scope and lookup indexes.

## User experience

`/current-flow` now reports the workflow name, command, execution identity, effective conversation scope, remaining validity, and endpoint when available.

`/commands` can expose quick actions for commands that administrators explicitly allow as persistent selections. Selecting one sends `/use-flow <command>`; explicit command execution remains available separately.

## Acceptance checklist

1. Enable user workflow selection and group system-command mention enforcement.
2. Mark at least two custom commands as eligible for persistent selection.
3. Verify `/commands`, `/use-flow`, `/current-flow`, explicit one-shot commands, and `/use-flow default` in private chat.
4. Verify two group members maintain independent selections.
5. Verify a group system command without a mention is ignored and the mentioned form is processed.
6. Verify selection state survives a backend restart.
7. Disable an active command and verify automatic fallback plus an audit record.
8. Revoke one selection in Channel Center and verify an administrator audit record.
9. Create an expired test record or use a short TTL and verify scheduled or manual cleanup.
10. Verify the active-selection list search and pagination without auxiliary command, conversation, or identity requests.
