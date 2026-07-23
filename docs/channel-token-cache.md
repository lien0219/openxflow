# Channel Provider Token Cache

OpenXFlow caches Feishu, DingTalk, and Enterprise WeChat access tokens in each application process. Production channel connections are created through the resilient adapters:

- `ResilientEncryptedFeishuChannelAdapter`;
- `ResilientDingTalkChannelAdapter`;
- `ResilientWeComChannelAdapter`.

## Cache-key isolation

A token cache key contains:

```text
provider + normalized API base URL + public application identifier + SHA-256 secret fingerprint
```

The raw App Secret, Client Secret, or Corp Secret is never stored in the key. Rotating a secret therefore creates a new cache key and cannot reuse a token obtained with the previous secret.

Cache state is process-local. Multiple application processes may each hold a valid token for the same provider application.

## Refresh synchronization

Refresh locks are isolated by both the current asyncio event loop and the credential cache key.

- Concurrent requests using the same credentials share one refresh result.
- Concurrent forced refreshes using the same credentials are coalesced.
- Different provider applications do not block one another.
- Different secrets for the same public application identifier use different locks.
- Reloaders and test clients using separate event loops do not reuse loop-bound locks.

Each event loop retains at most 256 idle credential locks per provider adapter. Active holders and waiters are never pruned. Cancelled waiters release their usage count without releasing a lock they never acquired.

## Provider response validation

Token endpoint responses must be JSON objects and include a non-empty token. Lifetime fields are validated as positive finite numbers:

| Provider | Lifetime field |
| --- | --- |
| Feishu | `expire` |
| DingTalk | `expireIn` |
| Enterprise WeChat | `expires_in` |

Boolean, null, non-numeric, non-finite, zero, and negative lifetime values are rejected with the provider-specific API error rather than leaking `ValueError`, `TypeError`, or `OverflowError`.

## Rejected-token recovery

An explicit access-token rejection triggers at most one synchronized refresh and one replay. Other requests waiting on the same credential key reuse the refresh winner. A second rejection is returned to the caller and is not replayed again.

Authentication recovery is separate from transient HTTP retry. Normal permission, validation, and business errors do not trigger token refresh.

## Secret rotation procedure

1. Update the channel connection with the new provider secret.
2. Save the connection so newly constructed adapters use the new secret fingerprint.
3. Run the connection health check.
4. Confirm token-refresh failure metrics remain stable.
5. Revoke the old secret at the provider after all application instances have reloaded the new connection.

The old process-local cache entry expires naturally and is unreachable from adapters constructed with the new secret.

## Metrics

The authenticated channel metrics endpoint exposes two groups of provider-bounded counters.

Token-cache behavior:

```text
openxflow_channel_token_cache_hits_total
openxflow_channel_token_cache_misses_total
openxflow_channel_token_cache_forced_refreshes_total
openxflow_channel_token_cache_coalesced_refreshes_total
openxflow_channel_token_cache_refresh_succeeded_total
openxflow_channel_token_cache_refresh_failed_total
```

Rejected-token recovery:

```text
openxflow_channel_token_rejections_total
openxflow_channel_token_refresh_succeeded_total
openxflow_channel_token_refresh_failed_total
openxflow_channel_token_replays_total
```

All counters use only the fixed `provider` label. No application identifier, connection identifier, cache key, secret fingerprint, or raw credential is exported.

Operational interpretation:

- A rising cache-miss rate with few hits can indicate short token lifetimes, frequent process restarts, or excessive forced health checks.
- A rising coalesced-refresh count is expected during bursts and demonstrates that duplicate Provider token requests were avoided.
- Cache refresh failures indicate Provider, credential, DNS, network, or response-validation problems before a business API call can proceed.
- Rejection recovery failures indicate that a Provider explicitly rejected a cached token and the replacement-token request also failed.

Process-local counters should be summed across application workers. Ratios such as hits divided by hits plus misses should use matching worker and time windows.
