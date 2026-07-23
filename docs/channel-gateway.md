# OpenXFlow Channel Gateway

OpenXFlow Channel Gateway connects Telegram, Feishu, DingTalk, and Enterprise WeChat to workflows, knowledge bases, file ingestion, and account binding.

## Runtime environment variables

| Variable | Default | Description |
| --- | ---: | --- |
| `LANGFLOW_CHANNEL_STREAMS_ENABLED` | `true` | Enables lifecycle-managed Stream clients such as DingTalk Stream. |
| `LANGFLOW_CHANNEL_WEBHOOK_MAX_CONCURRENCY` | `16` | Maximum webhook jobs executing concurrently in one process. |
| `LANGFLOW_CHANNEL_WEBHOOK_MAX_PENDING` | `128` | Maximum accepted in-memory jobs when durable processing is disabled. |
| `LANGFLOW_CHANNEL_WEBHOOK_MAX_PENDING_BYTES` | `67108864` | Maximum retained callback-body bytes for the in-memory fallback. |
| `LANGFLOW_CHANNEL_WEBHOOK_MAX_BODY_BYTES` | `1048576` | Maximum accepted callback body size. |
| `LANGFLOW_CHANNEL_WEBHOOK_QUEUE_TIMEOUT_SECONDS` | `0` | Maximum in-memory queue wait; `0` disables it. |
| `LANGFLOW_CHANNEL_WEBHOOK_TASK_TIMEOUT_SECONDS` | `300` | Maximum execution time for one webhook job. |
| `LANGFLOW_CHANNEL_WEBHOOK_DURABLE_ENABLED` | `true` | Persists validated callbacks before returning a provider acknowledgement. |
| `LANGFLOW_CHANNEL_WEBHOOK_JOB_WORKERS` | `4` | Durable consumers per process, capped by maximum concurrency. |
| `LANGFLOW_CHANNEL_WEBHOOK_JOB_POLL_SECONDS` | `0.5` | Idle database poll delay. |
| `LANGFLOW_CHANNEL_WEBHOOK_JOB_LEASE_SECONDS` | `600` | Requested processing lease, raised to task timeout plus 30 seconds when needed. |
| `LANGFLOW_CHANNEL_WEBHOOK_JOB_MAX_ATTEMPTS` | `5` | Maximum durable processing attempts. |
| `LANGFLOW_CHANNEL_WEBHOOK_JOB_RETRY_BASE_SECONDS` | `2` | Initial retry delay. |
| `LANGFLOW_CHANNEL_WEBHOOK_JOB_RETRY_MAX_SECONDS` | `300` | Maximum retry delay. |
| `LANGFLOW_CHANNEL_WEBHOOK_JOB_CLEANUP_INTERVAL_SECONDS` | `60` | Queue-depth refresh and cleanup interval. |
| `LANGFLOW_CHANNEL_WEBHOOK_JOB_COMPLETED_RETENTION_DAYS` | `7` | Completed-job retention. |
| `LANGFLOW_CHANNEL_WEBHOOK_JOB_FAILED_RETENTION_DAYS` | `30` | Terminal failed-job retention. |
| `LANGFLOW_CHANNEL_WEBHOOK_JOB_CLEANUP_BATCH_SIZE` | `500` | Maximum rows removed by one cleanup cycle. |
| `LANGFLOW_CHANNEL_OUTBOUND_DELIVERY_RETENTION_DAYS` | `30` | Retention for terminal outbound delivery receipts. |
| `LANGFLOW_CHANNEL_HTTP_MAX_ATTEMPTS` | `3` | Maximum transient outbound attempts. |
| `LANGFLOW_CHANNEL_HTTP_BASE_DELAY_SECONDS` | `0.5` | Initial outbound retry delay. |
| `LANGFLOW_CHANNEL_HTTP_MAX_DELAY_SECONDS` | `8` | Maximum outbound retry delay. |
| `LANGFLOW_CHANNEL_HTTP_JITTER_RATIO` | `0.2` | Random retry jitter ratio. |

Example:

```bash
export LANGFLOW_CHANNEL_STREAMS_ENABLED=true
export LANGFLOW_CHANNEL_WEBHOOK_MAX_CONCURRENCY=16
export LANGFLOW_CHANNEL_WEBHOOK_MAX_BODY_BYTES=1048576
export LANGFLOW_CHANNEL_WEBHOOK_TASK_TIMEOUT_SECONDS=300
export LANGFLOW_CHANNEL_WEBHOOK_DURABLE_ENABLED=true
export LANGFLOW_CHANNEL_WEBHOOK_JOB_WORKERS=4
export LANGFLOW_CHANNEL_WEBHOOK_JOB_POLL_SECONDS=0.5
export LANGFLOW_CHANNEL_WEBHOOK_JOB_LEASE_SECONDS=600
export LANGFLOW_CHANNEL_WEBHOOK_JOB_MAX_ATTEMPTS=5
export LANGFLOW_CHANNEL_WEBHOOK_JOB_RETRY_BASE_SECONDS=2
export LANGFLOW_CHANNEL_WEBHOOK_JOB_RETRY_MAX_SECONDS=300
export LANGFLOW_CHANNEL_WEBHOOK_JOB_CLEANUP_INTERVAL_SECONDS=60
export LANGFLOW_CHANNEL_WEBHOOK_JOB_COMPLETED_RETENTION_DAYS=7
export LANGFLOW_CHANNEL_WEBHOOK_JOB_FAILED_RETENTION_DAYS=30
export LANGFLOW_CHANNEL_WEBHOOK_JOB_CLEANUP_BATCH_SIZE=500
export LANGFLOW_CHANNEL_OUTBOUND_DELIVERY_RETENTION_DAYS=30
export LANGFLOW_CHANNEL_HTTP_MAX_ATTEMPTS=3
export LANGFLOW_CHANNEL_HTTP_BASE_DELAY_SECONDS=0.5
export LANGFLOW_CHANNEL_HTTP_MAX_DELAY_SECONDS=8
export LANGFLOW_CHANNEL_HTTP_JITTER_RATIO=0.2
```

## Durable webhook acknowledgement model

Durable processing is enabled by default:

1. The request handler enforces the body limit, verifies the provider signature, decrypts encrypted events when configured, and parses the normalized event.
2. OpenXFlow commits the event identifier, channel type, original payload, an internal preverified marker, and optional non-sensitive `content-type` to `channel_webhook_job`.
3. Only after insert or duplicate detection succeeds does OpenXFlow return the provider acknowledgement.

Provider verification secrets are not persisted. This includes Telegram secret tokens, DingTalk signatures, Enterprise WeChat signature parameters, authorization headers, cookies, and proxy headers.

The job unique key is:

```text
connection_id + external_event_id
```

Provider retries therefore return a successful acknowledgement without creating duplicate jobs. Database failures propagate to the HTTP request so the provider can retry.

Each process starts the configured number of consumers. A consumer atomically changes a ready job to `processing`, increments the attempt count, and records a worker UUID and lease expiry. Failed jobs return to `pending` with bounded exponential backoff; exhausted jobs enter terminal `failed` status.

If a process exits during execution, another worker may reclaim the job after the lease expires. A crash-left `ChannelEventReceipt` in `processing` is reset to `failed` before replay so the deduplicator can reclaim the event.

The lease is normalized to at least:

```text
LANGFLOW_CHANNEL_WEBHOOK_TASK_TIMEOUT_SECONDS + 30 seconds
```

Completed and terminal failed jobs are cleaned in bounded oldest-first batches. Pending and processing jobs are never removed by retention cleanup.

Run migration `f7d0b5c3e4a6` before enabling durable callbacks.

## Durable outbound delivery guard

Durable jobs use at-least-once execution. Provider acknowledgements and business replies therefore need a separate at-most-once guard.

Migration `a8e1c6d4f5b7` creates `channel_outbound_delivery`. The unique key is:

```text
connection_id + external_event_id + delivery_kind
```

The bounded `delivery_kind` values are:

```text
acknowledgement
response
```

This allows one provider interaction acknowledgement and one business response for the same inbound event while suppressing duplicates of either type.

Delivery states:

- `reserved`: this event and delivery kind own the provider-delivery slot;
- `sent`: the provider call returned successfully;
- `failed`: the provider call explicitly failed and a later replay may reserve it again.

A `reserved` or `sent` row suppresses a later duplicate delivery. A failed row is reacquired through a conditional update so only one competing worker can retry it.

Crash-window policy is deliberately conservative:

- Provider succeeds, then the application exits before writing `sent`: the row remains `reserved`, so replay suppresses a duplicate;
- the application exits after `reserved` but before the Provider request: replay also suppresses the delivery, so one message may be lost;
- Provider explicitly fails and `failed` is committed: replay may retry;
- writing the failed state also fails: the original Provider exception remains the primary error and the state failure is logged and counted;
- writing `sent` fails after Provider success: the job fails, but the retained `reserved` row suppresses a duplicate Provider call on replay.

Terminal `sent` and `failed` receipts are retained for `LANGFLOW_CHANNEL_OUTBOUND_DELIVERY_RETENTION_DAYS` and then removed in bounded oldest-first batches. `reserved` receipts are never automatically deleted because they represent an ambiguous Provider outcome. Retention must cover the provider's maximum retry window and the desired investigation period. After a terminal receipt is deleted, an extremely late provider replay can acquire a new delivery slot.

Run both migrations before enabling durable callbacks:

```text
f7d0b5c3e4a6
→ a8e1c6d4f5b7
```

## In-memory fallback

Set:

```bash
export LANGFLOW_CHANNEL_WEBHOOK_DURABLE_ENABLED=false
```

to restore the process-local reservation path. This path uses bounded pending-job and retained-payload capacity. When full it returns:

```http
HTTP/1.1 503 Service Unavailable
Retry-After: 1
```

The event is not acknowledged as successful. Queue timeout applies only to this fallback. In-memory tasks cannot survive process termination and are intended for development or emergency rollback.

## Request-body protection

Requests larger than the configured body limit return HTTP `413`. The limit is checked from `Content-Length` when present and again while streaming the body. A disconnected upload is discarded before signature verification, durable insertion, reservation, or execution and increments the client-disconnect counter.

## Outbound retry policy

OpenXFlow retries only transient failures:

- connection, DNS, and timeout failures;
- HTTP `408`, `425`, and `429`;
- HTTP `5xx`;
- provider errors explicitly indicating rate limiting, temporary unavailability, system busy, or timeout.

Authentication, permission, and normal validation errors are not retried. Provider `Retry-After` values take precedence over exponential backoff within the configured maximum.

Token recovery is separate from transient retry. Feishu, DingTalk, and Enterprise WeChat authentication rejections trigger one synchronized refresh and one replay. The same recovery applies to supported provider downloads.

## Runtime diagnostics and metrics

Authenticated diagnostics:

```text
GET /api/v1/channel-runtime/
GET /api/v1/channel-runtime/metrics
```

`durable_webhook_jobs` exposes worker, lease, retry, cleanup, and retention settings together with process-local outcomes and cached shared queue depths.

`outbound_delivery` exposes aggregate process totals:

- `reserved_total`;
- `suppressed_total`;
- `sent_total`;
- `failed_total`;
- `state_errors_total`;
- `cleaned_total`.

Prometheus outbound delivery counters are:

- `openxflow_channel_outbound_delivery_reserved_total`;
- `openxflow_channel_outbound_delivery_suppressed_total`;
- `openxflow_channel_outbound_delivery_sent_total`;
- `openxflow_channel_outbound_delivery_failed_total`;
- `openxflow_channel_outbound_delivery_state_errors_total`;
- `openxflow_channel_outbound_delivery_cleaned_total`.

Each uses the fixed label:

```text
delivery_kind="acknowledgement|response"
```

No connection, event, user, or message identifiers are exported as labels.

Other metrics include:

- durable worker manager, consumer, depth, claim, retry, failure, cleanup, and maintenance metrics;
- Stream manager, leader, client, synchronization, reconnect, and callback metrics;
- Stream callback, webhook queue-wait, and webhook execution Histograms;
- in-memory capacity and rejection metrics;
- outbound retry and provider token-recovery metrics.

Duration Histograms use fixed second buckets from `0.005` through `300`, plus `+Inf`. Durable queue-depth Gauges are cached snapshots of the shared database. Do not sum those Gauges across workers; use a recent sample or an aggregation such as `max`. Process-local outcome Counters should be summed across workers.

## DingTalk Stream deployment

DingTalk `connection_mode=stream` connections are owned by one elected application worker. Other workers continue serving HTTP without opening duplicate Stream clients. Inspect Leader and managed-client runtime fields rather than treating `streams_enabled=true` as proof of ownership.

A healthy Leader advances successful synchronization counters and keeps the last-successful timestamp recent. Database synchronization failures do not terminate the Manager. SDK connection failures increase connection-error and reconnect counters.

The runtime requires:

```bash
pip install "dingtalk-stream>=0.24.3,<0.25.0"
```

The dependency is declared in `src/backend/base/pyproject.toml`; regenerate `uv.lock` in a network-enabled environment before release packaging.

## Feishu encrypted events

When Feishu encryption is enabled, configure `app_id`, `app_secret`, `verification_token`, and `encrypt_key`. Encrypted URL verification, message events, and card actions are decrypted before token verification and normalization.

## Enterprise WeChat callbacks

Enterprise WeChat requires HTTPS and Safe Mode encryption. Configure the callback URL with the same callback Token and 43-character EncodingAESKey stored in OpenXFlow.

## Multi-worker recommendations

- Run migrations `f7d0b5c3e4a6` and `a8e1c6d4f5b7` before enabling durable callbacks.
- Reserve database-pool capacity for normal API and UI traffic.
- Start with four durable consumers per process and reduce for small pools.
- Keep one shared public callback URL per connection.
- Keep durable processing enabled in production unless intentionally rolling back.
- Size outbound-delivery retention for provider retry windows and incident investigation.
- Disable Stream management on HTTP-only workers when another deployment owns Stream connections.
- Monitor queue depth, stale leases, retries, terminal failures, cleanup throughput, delivery suppression, state errors, Stream ownership, callback latency, provider retries, token refresh failures, database saturation, and file-ingestion backlog.
