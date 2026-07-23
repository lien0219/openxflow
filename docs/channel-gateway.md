# OpenXFlow Channel Gateway

OpenXFlow Channel Gateway connects Telegram, Feishu, DingTalk, and Enterprise WeChat to workflows, knowledge bases, file ingestion, and account binding.

## Runtime environment variables

| Variable | Default | Description |
| --- | ---: | --- |
| `LANGFLOW_CHANNEL_STREAMS_ENABLED` | `true` | Enables lifecycle-managed Stream clients such as DingTalk Stream. Accepted true values are `1`, `true`, `yes`, and `on`; accepted false values are `0`, `false`, `no`, and `off`. Unrecognized values fall back to `true`. |
| `LANGFLOW_CHANNEL_WEBHOOK_MAX_CONCURRENCY` | `16` | Maximum provider webhook jobs executing concurrently in one application process. Durable worker count is independently configured but cannot exceed this value. |
| `LANGFLOW_CHANNEL_WEBHOOK_MAX_PENDING` | `128` | Maximum accepted in-memory webhook jobs when durable processing is disabled. Values below the concurrency limit are automatically raised to match it. |
| `LANGFLOW_CHANNEL_WEBHOOK_MAX_PENDING_BYTES` | `67108864` | Maximum retained callback-body bytes for the in-memory fallback path. |
| `LANGFLOW_CHANNEL_WEBHOOK_MAX_BODY_BYTES` | `1048576` | Maximum accepted provider callback body size. Requests above this limit return HTTP `413` before signature parsing. |
| `LANGFLOW_CHANNEL_WEBHOOK_QUEUE_TIMEOUT_SECONDS` | `0` | Maximum wait for an execution slot in the in-memory fallback path. `0` disables queue timeout. |
| `LANGFLOW_CHANNEL_WEBHOOK_TASK_TIMEOUT_SECONDS` | `300` | Maximum execution time for one HTTP webhook job. Durable job leases are normalized to exceed this timeout by at least 30 seconds. |
| `LANGFLOW_CHANNEL_WEBHOOK_DURABLE_ENABLED` | `true` | Persists validated HTTP callbacks in the database before returning a successful provider acknowledgement. |
| `LANGFLOW_CHANNEL_WEBHOOK_JOB_WORKERS` | `4` | Durable consumer tasks started per application process. Values above `MAX_CONCURRENCY` are reduced to that limit. |
| `LANGFLOW_CHANNEL_WEBHOOK_JOB_POLL_SECONDS` | `0.5` | Delay before an idle durable consumer polls the database again. |
| `LANGFLOW_CHANNEL_WEBHOOK_JOB_LEASE_SECONDS` | `600` | Requested processing lease. Values shorter than task timeout plus 30 seconds are raised automatically. |
| `LANGFLOW_CHANNEL_WEBHOOK_JOB_MAX_ATTEMPTS` | `5` | Maximum durable job processing attempts before terminal failure. |
| `LANGFLOW_CHANNEL_WEBHOOK_JOB_RETRY_BASE_SECONDS` | `2` | Initial durable job retry delay. |
| `LANGFLOW_CHANNEL_WEBHOOK_JOB_RETRY_MAX_SECONDS` | `300` | Maximum durable job retry delay. Values below the base delay are raised to the base delay. |
| `LANGFLOW_CHANNEL_WEBHOOK_JOB_CLEANUP_INTERVAL_SECONDS` | `60` | Interval between durable queue depth refresh and retention cleanup cycles. |
| `LANGFLOW_CHANNEL_WEBHOOK_JOB_COMPLETED_RETENTION_DAYS` | `7` | Number of days completed jobs remain available for diagnostics and duplicate-event history. |
| `LANGFLOW_CHANNEL_WEBHOOK_JOB_FAILED_RETENTION_DAYS` | `30` | Number of days terminally failed jobs remain available for investigation. |
| `LANGFLOW_CHANNEL_WEBHOOK_JOB_CLEANUP_BATCH_SIZE` | `500` | Maximum terminal jobs deleted by one maintenance cycle across completed and failed statuses. |
| `LANGFLOW_CHANNEL_HTTP_MAX_ATTEMPTS` | `3` | Maximum attempts for transient outbound provider failures. |
| `LANGFLOW_CHANNEL_HTTP_BASE_DELAY_SECONDS` | `0.5` | Initial exponential-backoff delay. |
| `LANGFLOW_CHANNEL_HTTP_MAX_DELAY_SECONDS` | `8` | Maximum retry delay, including provider `Retry-After` values. |
| `LANGFLOW_CHANNEL_HTTP_JITTER_RATIO` | `0.2` | Random retry jitter from `0` to `1`; set to `0` for deterministic delays. |

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
export LANGFLOW_CHANNEL_HTTP_MAX_ATTEMPTS=3
export LANGFLOW_CHANNEL_HTTP_BASE_DELAY_SECONDS=0.5
export LANGFLOW_CHANNEL_HTTP_MAX_DELAY_SECONDS=8
export LANGFLOW_CHANNEL_HTTP_JITTER_RATIO=0.2
```

## Durable webhook acknowledgement model

Durable processing is enabled by default. HTTP providers are handled in three stages:

1. The request handler loads the enabled connection, enforces the callback body limit, verifies the provider signature, decrypts encrypted events when configured, and parses the normalized event.
2. OpenXFlow inserts the original headers and payload into `channel_webhook_job` and commits the transaction. A unique constraint on `(connection_id, external_event_id)` turns provider retries into idempotent successful acknowledgements instead of duplicate jobs.
3. Only after the insert or duplicate detection completes successfully does OpenXFlow return the provider acknowledgement. Database errors propagate to the HTTP request, so the provider can retry rather than receiving a false success.

Each application process starts the configured number of durable consumers. A consumer atomically changes one ready job from `pending` to `processing`, increments its one-based attempt count, and records a worker UUID with a lease expiry. Completion requires the same lease owner. Failed jobs return to `pending` with bounded exponential backoff until `max_attempts`; exhausted jobs enter terminal `failed` status.

If a process exits while handling a callback, it does not write a completion or retry transition. After the lease expires, another worker can claim the job. A `ChannelEventReceipt` left in `processing` by the crashed process is reset to `failed` before replay, allowing the persistent event deduplicator to reclaim the same event.

The durable lease is normalized to at least:

```text
LANGFLOW_CHANNEL_WEBHOOK_TASK_TIMEOUT_SECONDS + 30 seconds
```

This prevents a normally executing job from being reclaimed before its configured execution timeout. Durable execution uses the same task timeout and execution-duration Histogram as the in-memory path.

A process-local maintenance task runs immediately at startup and then at the configured cleanup interval. It refreshes shared queue depths and deletes at most one configured batch of expired terminal jobs. Completed jobs use `completed_at` for retention; terminal failures use their latest `updated_at`. Pending and processing jobs are never removed by retention cleanup. Multiple application processes may run maintenance safely because deletes are idempotent and bounded.

Run migration `f7d0b5c3e4a6` before enabling provider callbacks. Returning a successful provider acknowledgement before this table exists is intentionally impossible because the database insert fails.

## In-memory fallback

Set:

```bash
export LANGFLOW_CHANNEL_WEBHOOK_DURABLE_ENABLED=false
```

to use the previous process-local fallback. In that mode, each accepted callback receives an opaque limiter reservation token. Completion, cancellation, or background-task registration failure must consume that exact token. Tokens are single-use and scoped to their issuing limiter.

When either the pending-job limit or retained-payload byte limit is full, the fallback returns:

```http
HTTP/1.1 503 Service Unavailable
Retry-After: 1
```

The provider event is not acknowledged as successful. Capacity rejections are classified once as pending-only, payload-bytes-only, or both. Queue timeout applies only to this fallback. Because in-memory tasks cannot survive process termination, this mode is intended for rollback and development rather than production reliability.

## Request-body protection

When the request body exceeds the configured limit, OpenXFlow returns:

```http
HTTP/1.1 413 Request Entity Too Large
```

The size is checked first from `Content-Length` when supplied and again while the body is streamed. Reading stops as soon as accumulated bytes exceed the configured limit, protecting deployments when clients omit or falsify `Content-Length`.

When a client disconnects before the streamed request body is complete, OpenXFlow returns HTTP `400` where the transport still permits a response. The partial body is discarded before adapter construction, signature verification, durable insertion, reservation, or execution. The event increments `client_disconnected_total` but does not increment accepted, rejected-capacity, succeeded, or failed counters.

## Capacity guidance

A practical durable starting point is:

```text
job workers per process <= database connections allocated to channel work
lease seconds >= task timeout seconds + 30
max attempts = number of safe whole-event replays
cleanup batch size sized to avoid long delete transactions
```

Every durable consumer uses short database sessions during claim and state transitions, while workflow execution may acquire additional sessions. Do not assign the entire application connection pool to channel consumers. Start with four consumers per process and lower the value for small database pools.

For the in-memory fallback:

```text
max_pending = max_concurrency × 8
max_pending_bytes = expected average callback size × max_pending × safety factor
```

Capacity is per application process. Durable Job rows are shared by all workers and protected by conditional lease updates; in-memory capacity counters remain process-local.

## Outbound retry policy

OpenXFlow retries only transient outbound errors:

- connection, DNS, and timeout failures;
- HTTP `408`, `425`, and `429`;
- HTTP `5xx` responses;
- provider business errors that explicitly indicate rate limiting, temporary unavailability, system busy, or timeout.

Authentication errors, permission errors, and normal `4xx` validation failures are not retried. Provider `Retry-After` headers and recognized business-error retry delays take precedence over exponential backoff, subject to the configured maximum delay.

Access-token recovery is separate from transient retry. Feishu, DingTalk, and Enterprise WeChat responses that explicitly reject an access token trigger one synchronized token refresh and one replay. A second authentication rejection is returned immediately, unrelated business errors are not replayed by token recovery, and concurrent failures reuse the first successful refresh. The same behavior applies to Feishu resource downloads and Enterprise WeChat media downloads.

## Runtime diagnostics and metrics

Authenticated users can inspect the current process at:

```text
GET /api/v1/channel-runtime/
```

The response separates Stream configuration and runtime state, in-memory webhook limiter state, durable webhook configuration and process-local worker outcomes, and outbound retry policy. `durable_webhook_jobs` includes worker, polling, lease, retry and retention configuration; running managers and consumers; the last observed shared queue depths; and claimed, completed, retried, terminally failed, cleaned, claim-error and maintenance-error totals.

Prometheus text exposition is available at:

```text
GET /api/v1/channel-runtime/metrics
```

Important durable worker metrics are:

- `openxflow_channel_webhook_job_running_managers`
- `openxflow_channel_webhook_job_consumer_tasks`
- `openxflow_channel_webhook_job_pending`
- `openxflow_channel_webhook_job_processing`
- `openxflow_channel_webhook_job_completed_retained`
- `openxflow_channel_webhook_job_failed_retained`
- `openxflow_channel_webhook_job_claimed_total`
- `openxflow_channel_webhook_job_completed_total`
- `openxflow_channel_webhook_job_retried_total`
- `openxflow_channel_webhook_job_failed_total`
- `openxflow_channel_webhook_job_claim_errors_total`
- `openxflow_channel_webhook_job_cleaned_total`
- `openxflow_channel_webhook_job_maintenance_errors_total`

Other exported metrics include:

- Stream manager, leader, managed-client, synchronization, connection, reconnect and callback metrics;
- `openxflow_channel_stream_callback_duration_seconds`;
- `openxflow_channel_webhook_queue_wait_duration_seconds`;
- `openxflow_channel_webhook_execution_duration_seconds`;
- in-memory pending, active, retained-byte and rejection metrics;
- outbound provider attempts, retries and failures;
- provider token rejection, refresh and replay counters.

Duration Histograms use fixed second-based buckets from `0.005` through `300`, plus `+Inf`, and expose standard `_bucket`, `_count`, and `_sum` series. They have no connection, user, message, URL, or provider labels. Token recovery metrics use only the bounded `provider` label.

Most metrics are process-local. Durable queue depth Gauges are cached snapshots of the shared database observed by each process's maintenance task. When scraping multiple workers, do not sum those depth Gauges because every worker may report the same database rows. Use one worker's recent sample or a Prometheus aggregation such as `max` after confirming maintenance is healthy. Outcome Counters remain process-local and should be summed across workers.

## DingTalk Stream deployment

DingTalk connections with `connection_mode=stream` are maintained by one elected application worker. Other workers continue serving HTTP without opening duplicate Stream connections. `streams_enabled=true` only means that the process may start Stream management; it does not prove that it owns the leader lock. Inspect `stream_runtime.leader_managers` and `stream_runtime.managed_clients`, or matching Prometheus Gauges, on every worker.

A healthy Leader periodically increases `successful_sync_total` and keeps `last_successful_sync_timestamp_seconds` recent. Database failures increase `sync_errors_total` but no longer terminate the Manager. A growing `connection_errors_total` with `reconnect_attempts_total` indicates repeated SDK-client failures and exponential reconnect backoff.

Stream callback success and failure counters represent provider-visible callback outcomes. Normal application shutdown cancellation is excluded. The callback duration Histogram covers event normalization, workflow dispatch, provider response work and connection-status update before returning the SDK acknowledgement.

The runtime requires:

```bash
pip install "dingtalk-stream>=0.24.3,<0.25.0"
```

The dependency is declared in `src/backend/base/pyproject.toml`; the workspace `uv.lock` still must be regenerated in a network-enabled environment before release packaging.

## Feishu encrypted events

When Feishu event encryption is enabled, save:

```json
{
  "app_id": "cli_xxx",
  "app_secret": "xxx",
  "verification_token": "xxx",
  "encrypt_key": "xxx"
}
```

OpenXFlow supports encrypted URL verification, message events, and card actions. Events are decrypted before token verification and normalization. Leaving `Verification Token` or `Encrypt Key` blank while editing preserves the stored encrypted credential.

## Enterprise WeChat callbacks

Enterprise WeChat requires an HTTPS callback URL and Safe Mode encryption. Configure the callback URL shown in Channel Center together with the same callback Token and 43-character EncodingAESKey saved in OpenXFlow.

## Multi-worker recommendations

- Run migration `f7d0b5c3e4a6` before enabling provider callbacks.
- Reserve database-pool capacity for normal API and UI traffic.
- Keep one shared public callback URL per connection.
- Keep durable processing enabled in production unless intentionally rolling back.
- Tune `JOB_WORKERS`, polling interval and cleanup batch size for the database pool and callback rate.
- Disable `LANGFLOW_CHANNEL_STREAMS_ENABLED` on HTTP-only workers when another deployment owns Stream connections.
- Monitor durable queue depth, claim errors, maintenance errors, retries, terminal failures, stale processing leases, cleanup throughput, Stream ownership, callback latency, provider retries, token refresh failures, database saturation and file-ingestion backlog.
