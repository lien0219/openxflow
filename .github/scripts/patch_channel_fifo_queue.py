from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def patch(path: str, old: str, new: str, *, label: str) -> None:
    target = ROOT / path
    content = target.read_text(encoding="utf-8")
    if new and new in content:
        return
    if old not in content:
        raise RuntimeError(f"Missing FIFO hardening target for {label}")
    target.write_text(content.replace(old, new, 1), encoding="utf-8")


patch(
    "src/backend/base/langflow/channels/services/webhook_jobs.py",
    "        per_queue_concurrency = int(limits[1]) if limits is not None else 1\n",
    "",
    label="unused per-queue concurrency",
)
patch(
    "src/backend/base/langflow/channels/services/webhook_jobs.py",
    """            serialized_queue = ":conversation:" in candidate.queue_key
            queue_limit = 1 if serialized_queue else max(1, per_queue_concurrency)
""",
    """            # Every normalized context key is FIFO. Different members or
            # conversations still receive distinct keys and can run in parallel.
            queue_limit = 1
""",
    label="strict FIFO claim",
)
patch(
    "src/backend/base/langflow/channels/services/webhook_jobs.py",
    """            sa.update(ChannelWebhookJob)
            .where(ChannelWebhookJob.id == candidate_id, _claimable(now))
""",
    """            sa.update(ChannelWebhookJob)
            .where(ChannelWebhookJob.id == candidate_id, _claimable(now))
            .execution_options(synchronize_session=False)
""",
    label="timezone-safe atomic claim",
)
patch(
    "src/backend/base/langflow/channels/services/webhook_jobs.py",
    """        await session.commit()
        return await session.get(ChannelWebhookJob, candidate_id)
""",
    """        await session.commit()
        await session.refresh(candidate)
        return candidate
""",
    label="fresh claimed job state",
)
patch(
    "src/backend/base/langflow/channels/services/webhook_processing.py",
    """            if queue_wait_ms > connection.queue_timeout_seconds * 1000:
                return ChannelMessage(text="当前请求排队时间过长，任务已取消，请稍后重试。")
            return await dispatcher.handle(event)
""",
    """            if queue_wait_ms > connection.queue_timeout_seconds * 1000:
                return ChannelMessage(text="当前请求排队时间过长，任务已取消，请稍后重试。")
            try:
                async with asyncio.timeout(connection.task_timeout_seconds):
                    return await dispatcher.handle(event)
            except TimeoutError:
                return ChannelMessage(text="当前任务执行超时，请缩小问题范围后重试。")
""",
    label="connection task timeout",
)
patch(
    "src/backend/base/langflow/channels/adapters/factory.py",
    """            stream_authenticated=connection.connection_mode == "stream",
""",
    """            stream_authenticated=getattr(connection, "connection_mode", "webhook") == "stream",
""",
    label="legacy DingTalk connection mode",
)
