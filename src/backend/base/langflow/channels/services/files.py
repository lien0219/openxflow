"""Channel file persistence and knowledge-base ingestion orchestration."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from lfx.log.logger import logger
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.api.utils.kb_helpers import KBAnalysisHelper, KBIngestionHelper, KBStorageHelper
from langflow.channels.adapters.base import ChannelAdapter
from langflow.channels.adapters.factory import build_channel_adapter
from langflow.channels.domain.models import ChannelAttachment, ChannelEvent, ChannelMessage
from langflow.services.authorization import (
    FileAction,
    KnowledgeBaseAction,
    ensure_file_permission,
    ensure_knowledge_base_permission,
)
from langflow.services.database.models.channel.file_model import ChannelFileAsset, ChannelFileStatus
from langflow.services.database.models.channel.model import ChannelConnection, ChannelConversationBinding
from langflow.services.database.models.file.model import File as UserFile
from langflow.services.database.models.jobs.model import JobStatus, JobType
from langflow.services.database.models.knowledge_base.model import KnowledgeBaseRecord
from langflow.services.database.models.user.model import User
from langflow.services.deps import (
    get_job_service,
    get_settings_service,
    get_storage_service,
    get_task_service,
    session_scope,
)
from langflow.services.memory_base.kb_path_helpers import validate_kb_path

_DEFAULT_ALLOWED_EXTENSIONS = {
    ".csv",
    ".doc",
    ".docx",
    ".htm",
    ".html",
    ".json",
    ".markdown",
    ".md",
    ".pdf",
    ".ppt",
    ".pptx",
    ".rtf",
    ".txt",
    ".xls",
    ".xlsx",
    ".xml",
    ".yaml",
    ".yml",
}
_MAX_RECENT_FILES = 10


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def sanitize_channel_filename(filename: str) -> str:
    normalized = filename.strip()
    dangerous = ("..", "/", "\\", "\x00", "\n", "\r")
    if not normalized or any(token in normalized for token in dangerous):
        raise ValueError("文件名不安全，请重命名后重新上传。")
    if len(normalized.encode("utf-8")) > 255:
        raise ValueError("文件名过长，请缩短到 255 字节以内。")
    candidate = Path(normalized).name
    if candidate in {"", ".", ".."}:
        raise ValueError("文件名无效。")
    return candidate


def _allowed_extensions(connection: ChannelConnection) -> set[str]:
    configured = connection.settings_data.get("allowed_file_extensions")
    if not isinstance(configured, list):
        return set(_DEFAULT_ALLOWED_EXTENSIONS)
    allowed = {
        (value if value.startswith(".") else f".{value}").lower()
        for value in configured
        if isinstance(value, str) and value.strip()
    }
    return allowed or set(_DEFAULT_ALLOWED_EXTENSIONS)


def _max_file_size_bytes(connection: ChannelConnection) -> int:
    global_limit_mb = int(get_settings_service().settings.max_file_size_upload)
    configured = connection.settings_data.get("max_file_size_mb")
    if isinstance(configured, (int, float)) and not isinstance(configured, bool) and configured > 0:
        global_limit_mb = min(global_limit_mb, int(configured))
    return global_limit_mb * 1024 * 1024


async def resolve_owned_knowledge_base(
    session: AsyncSession,
    user_id: UUID,
    identifier: str,
) -> KnowledgeBaseRecord | None:
    normalized = identifier.strip()
    if not normalized:
        return None
    try:
        kb_id = UUID(normalized)
    except ValueError:
        statement = select(KnowledgeBaseRecord).where(
            KnowledgeBaseRecord.user_id == user_id,
            KnowledgeBaseRecord.name == normalized,
        )
    else:
        statement = select(KnowledgeBaseRecord).where(
            KnowledgeBaseRecord.user_id == user_id,
            KnowledgeBaseRecord.id == kb_id,
        )
    return (await session.exec(statement)).first()


async def list_owned_knowledge_bases(session: AsyncSession, user_id: UUID) -> list[KnowledgeBaseRecord]:
    statement = (
        select(KnowledgeBaseRecord)
        .where(KnowledgeBaseRecord.user_id == user_id)
        .order_by(col(KnowledgeBaseRecord.updated_at).desc())
    )
    return list((await session.exec(statement)).all())


async def _finalize_channel_file_asset(
    asset_id: UUID,
    status: ChannelFileStatus,
    error_message: str | None = None,
) -> None:
    # The background task can start a few milliseconds before the webhook
    # transaction commits. Retry the lookup briefly instead of silently losing
    # the terminal status update.
    for attempt in range(6):
        async with session_scope() as session:
            asset = await session.get(ChannelFileAsset, asset_id)
            if asset is not None:
                asset.status = status.value
                asset.error_message = error_message[:2000] if error_message else None
                asset.updated_at = _utc_now()
                session.add(asset)
                return
        if attempt < 5:
            await asyncio.sleep(0.1 * (2**attempt))
    await logger.aerror("Channel file asset %s was not visible after commit retries", asset_id)


async def run_channel_ingestion_and_notify(
    *,
    asset_id: UUID,
    connection_id: UUID,
    job_id: UUID,
    kb_name: str,
    kb_path: str,
    filename: str,
    content: bytes,
    chunk_size: int,
    chunk_overlap: int,
    separator: str,
    model_selection: dict[str, Any],
    user_id: UUID,
    target_id: str,
) -> None:
    """Run a KB ingestion job and notify the originating conversation."""
    async with session_scope() as session:
        user = await session.get(User, user_id)
        connection = await session.get(ChannelConnection, connection_id)

    if user is None or connection is None:
        await _finalize_channel_file_asset(
            asset_id,
            ChannelFileStatus.FAILED,
            "Channel user or connection no longer exists",
        )
        return

    adapter = build_channel_adapter(connection)
    job_service = get_job_service()
    resolved_path = Path(kb_path)
    try:
        await job_service.execute_with_status(
            job_id=job_id,
            run_coro_func=KBIngestionHelper.perform_ingestion,
            kb_name=kb_name,
            kb_path=resolved_path,
            files_data=[(filename, content)],
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separator=separator,
            source_name=f"{connection.channel_type}:{target_id}",
            current_user=user,
            model_selection=model_selection,
            task_job_id=job_id,
            job_service=job_service,
        )
    except Exception as exc:  # noqa: BLE001
        await _finalize_channel_file_asset(asset_id, ChannelFileStatus.FAILED, str(exc))
        try:
            await adapter.send_message(
                target_id,
                ChannelMessage(
                    title="知识库文件解析失败",
                    text=f"文件：{filename}\n知识库：{kb_name}\n错误：{str(exc)[:500]}",
                ),
            )
        except Exception:  # noqa: BLE001
            await logger.aexception("Failed to send channel ingestion failure notification")
    else:
        await _finalize_channel_file_asset(asset_id, ChannelFileStatus.READY)
        try:
            await adapter.send_message(
                target_id,
                ChannelMessage(
                    title="知识库文件解析完成",
                    text=f"文件：{filename}\n知识库：{kb_name}\n现在可以继续在该会话中提问。",
                ),
            )
        except Exception:  # noqa: BLE001
            await logger.aexception("Failed to send channel ingestion completion notification")


class ChannelFileService:
    """Store provider attachments and optionally ingest them into a bound KB."""

    def __init__(
        self,
        session: AsyncSession,
        connection: ChannelConnection,
        adapter: ChannelAdapter,
    ) -> None:
        self.session = session
        self.connection = connection
        self.adapter = adapter

    async def handle_attachment(
        self,
        *,
        event: ChannelEvent,
        user: User,
        binding: ChannelConversationBinding | None,
        attachment: ChannelAttachment,
    ) -> ChannelMessage:
        if attachment.external_file_id is None:
            return ChannelMessage(text="该附件没有可下载的文件标识，暂时无法处理。")

        existing = await self._find_existing_asset(event, attachment.external_file_id)
        if existing is not None:
            return self._existing_asset_message(existing)

        asset = ChannelFileAsset(
            connection_id=event.connection_id,
            openxflow_user_id=user.id,
            external_conversation_id=event.conversation.external_conversation_id,
            external_message_id=event.message.external_message_id,
            external_file_id=attachment.external_file_id,
            filename=attachment.filename,
            mime_type=attachment.mime_type,
            size_bytes=attachment.size_bytes or 0,
            metadata_data=dict(attachment.metadata),
        )
        self.session.add(asset)
        await self.session.flush()

        try:
            safe_filename = sanitize_channel_filename(attachment.filename)
            suffix = Path(safe_filename).suffix.lower()
            allowed = _allowed_extensions(self.connection)
            if suffix not in allowed:
                allowed_text = "、".join(sorted(allowed))
                raise ValueError(f"暂不支持 {suffix or '无扩展名'} 文件。允许格式：{allowed_text}")

            declared_size = attachment.size_bytes or 0
            max_size = _max_file_size_bytes(self.connection)
            if declared_size and declared_size > max_size:
                raise ValueError(f"文件超过上传限制（最大 {max_size // 1024 // 1024}MB）。")

            content, provider_metadata = await self.adapter.download_file(attachment.external_file_id)
            if len(content) > max_size:
                raise ValueError(f"文件超过上传限制（最大 {max_size // 1024 // 1024}MB）。")
            if not content:
                raise ValueError("文件内容为空。")

            user_file, _stored_filename = await self._store_user_file(
                user=user,
                filename=safe_filename,
                content=content,
            )
            asset.user_file_id = user_file.id
            asset.filename = safe_filename
            asset.size_bytes = len(content)
            asset.mime_type = attachment.mime_type or provider_metadata.get("content_type")
            asset.status = ChannelFileStatus.STORED.value
            asset.metadata_data = {**asset.metadata_data, **provider_metadata}
            asset.updated_at = _utc_now()
            self.session.add(asset)
            await self.session.flush()

            event.message.metadata.setdefault("stored_files", []).append(
                {
                    "channel_file_asset_id": str(asset.id),
                    "user_file_id": str(user_file.id),
                    "filename": safe_filename,
                    "path": user_file.path,
                    "size_bytes": len(content),
                }
            )

            if binding is not None and binding.knowledge_base_id is not None:
                job_id, kb_name = await self._queue_knowledge_base_ingestion(
                    event=event,
                    user=user,
                    binding=binding,
                    asset=asset,
                    filename=safe_filename,
                    content=content,
                )
                return ChannelMessage(
                    title="文件已进入知识库解析队列",
                    text=(
                        f"文件：{safe_filename}\n"
                        f"知识库：{kb_name}\n"
                        f"任务：{job_id}\n\n"
                        "解析完成后机器人会主动通知。发送 /files 可查看最近文件状态。"
                    ),
                )

            return ChannelMessage(
                title="文件已保存",
                text=(
                    f"文件：{safe_filename}\n"
                    f"文件 ID：{user_file.id}\n\n"
                    "当前会话未绑定知识库。发送 /knowledge 查看知识库，"
                    "再使用 /use-kb <知识库名称> 完成绑定。"
                ),
            )
        except Exception as exc:  # noqa: BLE001
            asset.status = ChannelFileStatus.FAILED.value
            asset.error_message = str(exc)[:2000]
            asset.updated_at = _utc_now()
            self.session.add(asset)
            await self.session.flush()
            await logger.aexception("Channel attachment processing failed: %s", attachment.filename)
            return ChannelMessage(title="文件处理失败", text=str(exc))

    async def list_recent_assets(
        self,
        *,
        user_id: UUID,
        external_conversation_id: str,
        limit: int = _MAX_RECENT_FILES,
    ) -> list[ChannelFileAsset]:
        statement = (
            select(ChannelFileAsset)
            .where(
                ChannelFileAsset.connection_id == self.connection.id,
                ChannelFileAsset.openxflow_user_id == user_id,
                ChannelFileAsset.external_conversation_id == external_conversation_id,
            )
            .order_by(col(ChannelFileAsset.created_at).desc())
            .limit(limit)
        )
        return list((await self.session.exec(statement)).all())

    async def _find_existing_asset(
        self,
        event: ChannelEvent,
        external_file_id: str,
    ) -> ChannelFileAsset | None:
        statement = select(ChannelFileAsset).where(
            ChannelFileAsset.connection_id == event.connection_id,
            ChannelFileAsset.external_message_id == event.message.external_message_id,
            ChannelFileAsset.external_file_id == external_file_id,
        )
        return (await self.session.exec(statement)).first()

    async def _store_user_file(
        self,
        *,
        user: User,
        filename: str,
        content: bytes,
    ) -> tuple[UserFile, str]:
        await ensure_file_permission(user, FileAction.CREATE, file_user_id=user.id)
        display_name, stored_filename = await self._allocate_unique_filename(user.id, filename)
        storage_service = get_storage_service()
        await storage_service.save_file(
            flow_id=str(user.id),
            file_name=stored_filename,
            data=content,
        )
        try:
            size = await storage_service.get_file_size(flow_id=str(user.id), file_name=stored_filename)
            user_file = UserFile(
                id=uuid4(),
                user_id=user.id,
                name=display_name,
                path=f"{user.id}/{stored_filename}",
                size=size,
                provider=f"channel:{self.connection.channel_type}",
            )
            self.session.add(user_file)
            await self.session.flush()
            await self.session.refresh(user_file)
            return user_file, stored_filename
        except Exception:
            try:
                await storage_service.delete_file(flow_id=str(user.id), file_name=stored_filename)
            except Exception:  # noqa: BLE001
                await logger.aexception("Failed to clean up channel file %s", stored_filename)
            raise

    async def _allocate_unique_filename(self, user_id: UUID, filename: str) -> tuple[str, str]:
        path = Path(filename)
        root = path.stem or path.name
        suffix = path.suffix
        counter = 0
        while True:
            display_name = root if counter == 0 else f"{root} ({counter})"
            statement = select(UserFile.id).where(
                UserFile.user_id == user_id,
                UserFile.name == display_name,
            )
            if (await self.session.exec(statement)).first() is None:
                return display_name, f"{display_name}{suffix}"
            counter += 1

    async def _queue_knowledge_base_ingestion(
        self,
        *,
        event: ChannelEvent,
        user: User,
        binding: ChannelConversationBinding,
        asset: ChannelFileAsset,
        filename: str,
        content: bytes,
    ) -> tuple[UUID, str]:
        kb = await self.session.get(KnowledgeBaseRecord, binding.knowledge_base_id)
        if kb is None or kb.user_id != user.id:
            raise ValueError("当前会话绑定的知识库不存在或不属于当前账号。")
        await ensure_knowledge_base_permission(
            user,
            KnowledgeBaseAction.INGEST,
            kb_id=kb.id,
            kb_user_id=kb.user_id,
            kb_name=kb.name,
        )

        kb_root = KBStorageHelper.get_root_path()
        user_root = (kb_root / user.username).resolve()
        kb_path = (user_root / kb.name).resolve()
        validate_kb_path(user_root, kb_path)
        if not kb_path.exists() or not kb_path.is_dir():
            raise ValueError(f"知识库 {kb.name} 的存储目录不存在。")

        metadata = KBAnalysisHelper.get_metadata(kb_path, fast=False)
        model_selection = metadata.get("model_selection") if metadata else None
        if not model_selection:
            model_selection = kb.model_selection
        if not model_selection or not model_selection.get("name") or not model_selection.get("provider"):
            raise ValueError("知识库缺少有效的嵌入模型配置。")

        job_service = get_job_service()
        job_id = uuid4()
        await job_service.create_job(
            job_id=job_id,
            flow_id=job_id,
            job_type=JobType.INGESTION,
            asset_id=kb.id,
            asset_type="knowledge_base",
            user_id=user.id,
            dedupe_key=f"channel_file:{asset.id}",
        )

        asset.knowledge_base_id = kb.id
        asset.ingestion_job_id = job_id
        asset.status = ChannelFileStatus.INGESTING.value
        asset.updated_at = _utc_now()
        self.session.add(asset)
        await self.session.flush()

        task_service = get_task_service()
        try:
            await task_service.fire_and_forget_task(
                run_channel_ingestion_and_notify,
                asset_id=asset.id,
                connection_id=self.connection.id,
                job_id=job_id,
                kb_name=kb.name,
                kb_path=str(kb_path),
                filename=filename,
                content=content,
                chunk_size=kb.chunk_size,
                chunk_overlap=kb.chunk_overlap,
                separator=kb.separator or "",
                model_selection=dict(model_selection),
                user_id=user.id,
                target_id=event.conversation.external_conversation_id,
            )
        except Exception as exc:
            await job_service.update_job_status(job_id, JobStatus.FAILED, finished_timestamp=True)
            asset.status = ChannelFileStatus.FAILED.value
            asset.error_message = f"Failed to schedule ingestion: {exc}"[:2000]
            asset.updated_at = _utc_now()
            self.session.add(asset)
            await self.session.flush()
            raise
        return job_id, kb.name

    @staticmethod
    def _existing_asset_message(asset: ChannelFileAsset) -> ChannelMessage:
        labels = {
            ChannelFileStatus.RECEIVED.value: "接收中",
            ChannelFileStatus.STORED.value: "已保存",
            ChannelFileStatus.INGESTING.value: "解析中",
            ChannelFileStatus.READY.value: "已完成",
            ChannelFileStatus.FAILED.value: "失败",
        }
        status_label = labels.get(asset.status, asset.status)
        return ChannelMessage(
            title="文件已处理",
            text=f"文件：{asset.filename}\n状态：{status_label}\n文件记录：{asset.id}",
        )
