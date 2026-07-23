# OpenXFlow Channel Gateway

OpenXFlow Channel Gateway connects Telegram, Feishu, DingTalk, and Enterprise WeChat to workflows, knowledge bases, file ingestion, and account binding.

## Runtime environment variables

| Variable | Default | Description |
| --- | ---: | --- |
| `LANGFLOW_CHANNEL_STREAMS_ENABLED` | `true` | Enables lifecycle-managed Stream clients such as DingTalk Stream. Accepted true values are `1`, `true`, `yes`, and `on`; accepted false values are `0`, `false`, `no`, and `off`. Unrecognized values fall back to `true`. |
| `LANGFLOW_CHANNEL_WEBHOOK_MAX_CONCURRENCY` | `16` | Maximum provider webhook jobs executing concurrently in one application process. |
| `LANGFLOW_CHANNEL_WEBHOOK_MAX_PENDING` | `128` | Maximum accepted webhook jobs, including executing and waiting jobs, in one application process. Values below the concurrency limit are automatically raised to match it. |
| `LANGFLOW_CHANNEL_WEBHOOK_MAX_PENDING_BYTES` | `67108864` | Maximum retained callback-body bytes across all accepted webhook jobs in one application process. |
| `LANGFLOW_CHANNEL_WEBHOOK_MAX_BODY_BYTES` | `1048576` | Maximum accepted provider callback body size. Requests above this limit return HTTP `413` before signature parsing. |
| `LANGFLOW_CHANNEL_WEBHOOK_TASK_TIMEOUT_SECONDS` | `300` | Maximum execution time for one webhook job after it obtains a concurrency slot. Queue wait time is not counted. |
| `LANGFLOW_CHANNEL_HTTP_MAX_ATTEMPTS` | `3` | Maximum attempts for transient outbound provider failures. |
| `LANGFLOW_CHANNEL_HTTP_BASE_DELAY_SECONDS` | `0.5` | Initial exponential-backoff delay. |
| `LANGFLOW_CHANNEL_HTTP_MAX_DELAY_SECONDS` | `8` | Maximum retry delay, including provider `Retry-After` values. |
| `LANGFLOW_CHANNEL_HTTP_JITTER_RATIO` | `0.2` | Random retry jitter from `0` to `1`; set to `0` for deterministic delays. |

Example:

```bash
export LANGFLOW_CHANNEL_STREAMS_ENABLED=true
export LANGFLOW_CHANNEL_WEBHOOK_MAX_CONCURRENCY=16
export LANGFLOW_CHANNEL_WEBHOOK_MAX_PENDING=128
export LANGFLOW_CHANNEL_WEBHOOK_MAX_PENDING_BYTES=67108864
export LANGFLOW_CHANNEL_WEBHOOK_MAX_BODY_BYTES=1048576
export LANGFLOW_CHANNEL_WEBHOOK_TASK_TIMEOUT_SECONDS=300
export LANGFLOW_CHANNEL_HTTP_MAX_ATTEMPTS=3
export LANGFLOW_CHANNEL_HTTP_BASE_DELAY_SECONDS=0.5
export LANGFLOW_CHANNEL_HTTP_MAX_DELAY_SECONDS=8
export LANGFLOW_CHANNEL_HTTP_JITTER_RATIO=0.2
```

## Webhook acknowledgement model

HTTP providers are handled in two stages:

1. The request handler loads the enabled connection, checks the callback body size, verifies the provider signature, decrypts encrypted events when configured, and parses the normalized event structure.
2. After validation, it atomically reserves both queue-count capacity and retained-payload byte capacity before returning the provider acknowledgement. Workflow execution, file download, knowledge-base ingestion, and the provider reply run in an isolated database session with a bounded execution timeout.

When the request body exceeds the configured limit, OpenXFlow returns:

```http
HTTP/1.1 413 Request Entity Too Large
```

The size is checked first from `Content-Length` when supplied and again while the body is streamed. Reading stops as soon as the accumulated bytes exceed the configured limit, which protects deployments when clients omit or falsify `Content-Length`.

When a client disconnects before the streamed request body is complete, OpenXFlow returns HTTP `400` where the transport still permits a response. The partial body is discarded before adapter construction, signature verification, queue reservation, or background execution.

When either the pending-job limit or the pending-payload byte limit is full, OpenXFlow returns:

```http
HTTP/1.1 503 Service Unavailable
Retry-After: 1
```

The error detail includes both current job usage and current retained-body byte usage. The event is **not** acknowledged as successful in this case. The provider may retry it. This avoids accepting and silently dropping callbacks during overload.

Queue wait time does not consume `LANGFLOW_CHANNEL_WEBHOOK_TASK_TIMEOUT_SECONDS`. The timeout starts only after a job obtains a concurrency slot and begins provider-event processing. A running job that exceeds the limit is cancelled, counted as failed, and releases its pending count and retained payload bytes. External application cancellation also releases both capacities but is not counted as a business failure. Because the provider has already received its successful acknowledgement, timeout recovery still depends on provider retries or a future durable queue.

## Capacity guidance

A practical starting point is:

```text
max_concurrency = available database connections allocated to channel work
max_pending = max_concurrency × 8
max_pending_bytes = expected average callback body size × max_pending × safety factor
```

Decrease concurrency when workflows are database-heavy or when the deployment has a small connection pool. Increase pending capacity only when the process has enough memory for retained request payloads and the expected workflow latency is bounded.

`LANGFLOW_CHANNEL_WEBHOOK_MAX_PENDING` is normalized to at least `LANGFLOW_CHANNEL_WEBHOOK_MAX_CONCURRENCY`. This prevents an invalid environment-variable combination from crashing the application during module import, but operators should still configure the values explicitly and monitor the runtime diagnostics endpoint.

The count and byte limits are independent. A process may reject a new callback while fewer than `MAX_PENDING` jobs are retained when those jobs already consume `MAX_PENDING_BYTES`. This prevents a burst of large but individually valid callback bodies from consuming memory proportional to `MAX_PENDING × MAX_BODY_BYTES`.

Capacity is per application process. With four HTTP workers and the defaults, the deployment can execute up to 64 channel jobs concurrently, retain up to 512 accepted jobs, and retain up to 256 MiB of callback bodies across all workers.

## Outbound retry policy

OpenXFlow retries only transient outbound errors:

- connection, DNS, and timeout failures;
- HTTP `408`, `425`, and `429`;
- HTTP `5xx` responses;
- provider business errors that explicitly indicate rate limiting, temporary unavailability, system busy, or timeout.

Authentication errors, permission errors, and normal `4xx` validation failures are not retried. Provider `Retry-After` headers and recognized business-error retry delays take precedence over exponential backoff, subject to the configured maximum delay.

## Runtime diagnostics and metrics

Authenticated users can inspect the current process at:

```text
GET /api/v1/channel-runtime/
```

The JSON response includes the parsed `streams_enabled` state for the current process, active, queued, accepted, rejected, succeeded, and failed webhook counts, current retained payload bytes, the pending-payload byte limit, the active per-request body-size and task-timeout limits, and the outbound retry policy.

Prometheus text exposition is available at:

```text
GET /api/v1/channel-runtime/metrics
```

This endpoint is also authenticated. It exports:

- `openxflow_channel_webhook_pending`
- `openxflow_channel_webhook_active`
- `openxflow_channel_webhook_queued`
- `openxflow_channel_webhook_pending_bytes`
- `openxflow_channel_webhook_max_pending`
- `openxflow_channel_webhook_max_pending_bytes`
- `openxflow_channel_webhook_max_concurrency`
- `openxflow_channel_webhook_accepted_total`
- `openxflow_channel_webhook_rejected_total`
- `openxflow_channel_webhook_succeeded_total`
- `openxflow_channel_webhook_failed_total`
- `openxflow_channel_outbound_attempts_total`
- `openxflow_channel_outbound_succeeded_total`
- `openxflow_channel_outbound_retries_total`
- `openxflow_channel_outbound_failed_total`

Metrics are process-local. In a multi-worker deployment, scrape every worker or aggregate them through the deployment's existing Prometheus multiprocess strategy.

## DingTalk Stream deployment

DingTalk connections with `connection_mode=stream` are maintained by one elected application worker. Other workers continue serving HTTP without opening duplicate Stream connections. Use `GET /api/v1/channel-runtime/` on each worker to confirm its parsed `streams_enabled` state.

The runtime requires the official Python package:

```bash
pip install "dingtalk-stream>=0.24.3"
```

The dependency must also be present in the generated application lock file before release packaging. A connection health check fails explicitly when credentials are valid but the Stream SDK is unavailable.

## Feishu encrypted events

When Feishu event encryption is enabled, save all of the following credentials on the channel connection:

```json
{
  "app_id": "cli_xxx",
  "app_secret": "xxx",
  "verification_token": "xxx",
  "encrypt_key": "xxx"
}
```

OpenXFlow supports encrypted URL verification, message events, and card action events. Events are decrypted before token verification and normalization. Channel Center exposes both `Verification Token` and `Encrypt Key`; leaving either field blank while editing preserves the stored encrypted credential.

## Enterprise WeChat callbacks

Enterprise WeChat requires an HTTPS callback URL and Safe Mode encryption. Configure the callback URL shown in Channel Center together with the same callback Token and 43-character EncodingAESKey saved in OpenXFlow.

## Multi-worker recommendations

- Reserve database-pool capacity for normal API and UI traffic instead of assigning the entire pool to channel jobs.
- Run database migrations before enabling provider callbacks.
- Keep only one shared public callback URL per connection.
- Disable `LANGFLOW_CHANNEL_STREAMS_ENABLED` on dedicated HTTP-only workers when Stream ownership is handled by another deployment.
- Monitor `400`, `413`, and `503` callback responses, pending payload bytes, provider retries, webhook timeout failures, workflow duration, database-pool saturation, and file-ingestion backlog.
