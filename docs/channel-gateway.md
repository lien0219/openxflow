# OpenXFlow Channel Gateway

OpenXFlow Channel Gateway connects Telegram, Feishu, DingTalk, and Enterprise WeChat to workflows, knowledge bases, file ingestion, and account binding.

## Runtime environment variables

| Variable | Default | Description |
| --- | ---: | --- |
| `LANGFLOW_CHANNEL_STREAMS_ENABLED` | `true` | Enables lifecycle-managed Stream clients such as DingTalk Stream. Set to `false` for workers that should only serve HTTP. |
| `LANGFLOW_CHANNEL_WEBHOOK_MAX_CONCURRENCY` | `16` | Maximum provider webhook jobs executing concurrently in one application process. |
| `LANGFLOW_CHANNEL_WEBHOOK_MAX_PENDING` | `128` | Maximum accepted webhook jobs, including executing and waiting jobs, in one application process. Must be greater than or equal to the concurrency value. |

Example:

```bash
export LANGFLOW_CHANNEL_STREAMS_ENABLED=true
export LANGFLOW_CHANNEL_WEBHOOK_MAX_CONCURRENCY=16
export LANGFLOW_CHANNEL_WEBHOOK_MAX_PENDING=128
```

## Webhook acknowledgement model

HTTP providers are handled in two stages:

1. The request handler loads the enabled connection, verifies the provider signature, decrypts encrypted events when configured, and parses the normalized event structure.
2. After validation, it reserves queue capacity and returns the provider acknowledgement. Workflow execution, file download, knowledge-base ingestion, and the provider reply run in an isolated database session.

When the local queue is full, OpenXFlow returns:

```http
HTTP/1.1 503 Service Unavailable
Retry-After: 1
```

The event is **not** acknowledged as successful in this case. The provider may retry it. This avoids accepting and silently dropping callbacks during overload.

## Capacity guidance

A practical starting point is:

```text
max_concurrency = available database connections allocated to channel work
max_pending = max_concurrency × 8
```

Decrease concurrency when workflows are database-heavy or when the deployment has a small connection pool. Increase pending capacity only when the process has enough memory for retained request payloads and the expected workflow latency is bounded.

Capacity is per application process. With four HTTP workers and the defaults, the deployment can execute up to 64 channel jobs concurrently and retain up to 512 accepted jobs in total.

## DingTalk Stream deployment

DingTalk connections with `connection_mode=stream` are maintained by one elected application worker. Other workers continue serving HTTP without opening duplicate Stream connections.

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

OpenXFlow supports encrypted URL verification, message events, and card action events. Events are decrypted before token verification and normalization.

## Enterprise WeChat callbacks

Enterprise WeChat requires an HTTPS callback URL and Safe Mode encryption. Configure the callback URL shown in Channel Center together with the same callback Token and 43-character EncodingAESKey saved in OpenXFlow.

## Multi-worker recommendations

- Reserve database-pool capacity for normal API and UI traffic instead of assigning the entire pool to channel jobs.
- Run database migrations before enabling provider callbacks.
- Keep only one shared public callback URL per connection.
- Disable `LANGFLOW_CHANNEL_STREAMS_ENABLED` on dedicated HTTP-only workers when Stream ownership is handled by another deployment.
- Monitor `503` callback responses, provider retries, workflow duration, database-pool saturation, and file-ingestion backlog.
