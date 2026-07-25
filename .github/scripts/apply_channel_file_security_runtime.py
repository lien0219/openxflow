from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    (ROOT / path).write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str, *, label: str) -> None:
    content = read(path)
    if new and new in content:
        return
    if old not in content:
        raise RuntimeError(f"Missing file-security rollout target for {label}")
    write(path, content.replace(old, new, 1))


def replace_between(path: str, start: str, end: str, replacement: str, *, label: str) -> None:
    content = read(path)
    start_index = content.find(start)
    end_index = content.find(end, start_index)
    if start_index < 0 or end_index < 0:
        raise RuntimeError(f"Unable to locate file-security rollout block for {label}")
    write(path, content[:start_index] + replacement + content[end_index:])


HELPERS = '@dataclass(frozen=True)\nclass ChannelKnowledgeBaseAccess:\n    """Scoped resource-owner delegation for one explicitly configured KB."""\n\n    resource_owner: User\n    delegated: bool\n\n\ndef effective_channel_knowledge_base_id(\n    connection: ChannelConnection,\n    binding: ChannelConversationBinding | None,\n) -> UUID | None:\n    """Prefer a conversation override and otherwise use the connection default."""\n    if binding is not None and binding.knowledge_base_id is not None:\n        return binding.knowledge_base_id\n    return connection.default_knowledge_base_id\n\n\ndef resolve_channel_knowledge_base_access(\n    *,\n    connection: ChannelConnection,\n    binding: ChannelConversationBinding | None,\n    execution_user: User,\n    connection_owner: User | None,\n    knowledge_base: KnowledgeBaseRecord,\n) -> ChannelKnowledgeBaseAccess:\n    """Resolve the least-privileged identity allowed to mutate the target KB."""\n    if is_managed_channel_service_user(execution_user, connection.id):\n        explicitly_granted_ids = {\n            kb_id\n            for kb_id in (\n                connection.default_knowledge_base_id,\n                binding.knowledge_base_id if binding is not None else None,\n            )\n            if kb_id is not None\n        }\n        if (\n            connection_owner is None\n            or connection_owner.id != connection.user_id\n            or knowledge_base.user_id != connection_owner.id\n            or knowledge_base.id not in explicitly_granted_ids\n        ):\n            raise ValueError("服务身份只能写入连接或会话显式授权的所有者知识库。")\n        return ChannelKnowledgeBaseAccess(resource_owner=connection_owner, delegated=True)\n\n    if knowledge_base.user_id != execution_user.id:\n        raise ValueError("当前会话绑定的知识库不存在或不属于当前账号。")\n    return ChannelKnowledgeBaseAccess(resource_owner=execution_user, delegated=False)\n\n\n'
QUEUE_FUNCTION = '    async def _queue_knowledge_base_ingestion(\n        self,\n        *,\n        event: ChannelEvent,\n        user: User,\n        binding: ChannelConversationBinding | None,\n        kb_id: UUID,\n        asset: ChannelFileAsset,\n        filename: str,\n        content: bytes,\n    ) -> tuple[UUID, str]:\n        kb = await self.session.get(KnowledgeBaseRecord, kb_id)\n        if kb is None:\n            raise ValueError("当前会话配置的知识库不存在。")\n\n        connection_owner = await self.session.get(User, self.connection.user_id)\n        access = resolve_channel_knowledge_base_access(\n            connection=self.connection,\n            binding=binding,\n            execution_user=user,\n            connection_owner=connection_owner,\n            knowledge_base=kb,\n        )\n        resource_owner = access.resource_owner\n        await ensure_knowledge_base_permission(\n            resource_owner,\n            KnowledgeBaseAction.INGEST,\n            kb_id=kb.id,\n            kb_user_id=kb.user_id,\n            kb_name=kb.name,\n        )\n\n        kb_root = KBStorageHelper.get_root_path()\n        user_root = (kb_root / resource_owner.username).resolve()\n        kb_path = (user_root / kb.name).resolve()\n        validate_kb_path(user_root, kb_path)\n        if not kb_path.exists() or not kb_path.is_dir():\n            raise ValueError(f"知识库 {kb.name} 的存储目录不存在。")\n\n        metadata = KBAnalysisHelper.get_metadata(kb_path, fast=False)\n        model_selection = metadata.get("model_selection") if metadata else None\n        if not model_selection:\n            model_selection = kb.model_selection\n        if not model_selection or not model_selection.get("name") or not model_selection.get("provider"):\n            raise ValueError("知识库缺少有效的嵌入模型配置。")\n\n        job_service = get_job_service()\n        job_id = uuid4()\n        await job_service.create_job(\n            job_id=job_id,\n            flow_id=job_id,\n            job_type=JobType.INGESTION,\n            asset_id=kb.id,\n            asset_type="knowledge_base",\n            user_id=resource_owner.id,\n            dedupe_key=f"channel_file:{asset.id}",\n        )\n\n        asset.knowledge_base_id = kb.id\n        asset.ingestion_job_id = job_id\n        asset.status = ChannelFileStatus.INGESTING.value\n        asset.metadata_data = {\n            **asset.metadata_data,\n            "knowledge_base_access": {\n                "execution_user_id": str(user.id),\n                "resource_owner_user_id": str(resource_owner.id),\n                "delegated_service_identity": access.delegated,\n            },\n        }\n        asset.updated_at = _utc_now()\n        self.session.add(asset)\n        await self.session.flush()\n\n        task_service = get_task_service()\n        try:\n            await task_service.fire_and_forget_task(\n                run_channel_ingestion_and_notify,\n                asset_id=asset.id,\n                connection_id=self.connection.id,\n                job_id=job_id,\n                kb_name=kb.name,\n                kb_path=str(kb_path),\n                filename=filename,\n                content=content,\n                chunk_size=kb.chunk_size,\n                chunk_overlap=kb.chunk_overlap,\n                separator=kb.separator or "",\n                model_selection=dict(model_selection),\n                execution_user_id=user.id,\n                resource_owner_user_id=resource_owner.id,\n                delegated_service_identity=access.delegated,\n                target_id=event.conversation.external_conversation_id,\n            )\n        except Exception as exc:\n            await job_service.update_job_status(job_id, JobStatus.FAILED, finished_timestamp=True)\n            asset.status = ChannelFileStatus.FAILED.value\n            asset.error_message = f"Failed to schedule ingestion: {exc}"[:2000]\n            asset.updated_at = _utc_now()\n            self.session.add(asset)\n            await self.session.flush()\n            raise\n        return job_id, kb.name\n\n'
FILES = "src/backend/base/langflow/channels/services/files.py"

replace_once(
    FILES,
    "import asyncio\nfrom datetime import datetime, timezone\n",
    "import asyncio\nfrom dataclasses import dataclass\nfrom datetime import datetime, timezone\n",
    label="dataclass import",
)
replace_once(
    FILES,
    "from langflow.channels.domain.models import ChannelAttachment, ChannelEvent, ChannelMessage\n",
    "from langflow.channels.domain.models import ChannelAttachment, ChannelEvent, ChannelMessage\n"
    "from langflow.channels.services.file_security import BuiltinChannelFileScanner, ChannelFileScanner\n"
    "from langflow.channels.services.service_identity import is_managed_channel_service_user\n",
    label="file scanner and service identity imports",
)
replace_once(
    FILES,
    "\n\ndef _allowed_extensions(connection: ChannelConnection) -> set[str]:\n",
    "\n\n" + HELPERS + "def _allowed_extensions(connection: ChannelConnection) -> set[str]:\n",
    label="knowledge base delegation helpers",
)
for unsafe_extension in (".doc", ".ppt", ".xls"):
    replace_once(
        FILES,
        f'    "{unsafe_extension}",\n',
        "",
        label=f"remove unsafe legacy {unsafe_extension} default",
    )
replace_once(
    FILES,
    "    model_selection: dict[str, Any],\n    user_id: UUID,\n    target_id: str,\n",
    "    model_selection: dict[str, Any],\n"
    "    execution_user_id: UUID,\n"
    "    resource_owner_user_id: UUID,\n"
    "    delegated_service_identity: bool,\n"
    "    target_id: str,\n",
    label="ingestion identity parameters",
)
replace_once(
    FILES,
    "        user = await session.get(User, user_id)\n        connection = await session.get(ChannelConnection, connection_id)\n\n"
    "    if user is None or connection is None:\n",
    "        resource_owner = await session.get(User, resource_owner_user_id)\n"
    "        connection = await session.get(ChannelConnection, connection_id)\n\n"
    "    if resource_owner is None or connection is None:\n",
    label="load resource owner",
)
replace_once(
    FILES,
    "            current_user=user,\n            model_selection=model_selection,\n",
    "            current_user=resource_owner,\n"
    "            model_selection=model_selection,\n"
    "            source_metadata={\n"
    '                "channel_connection_id": str(connection_id),\n'
    '                "channel_file_asset_id": str(asset_id),\n'
    '                "execution_user_id": str(execution_user_id),\n'
    '                "resource_owner_user_id": str(resource_owner_user_id),\n'
    '                "delegated_service_identity": delegated_service_identity,\n'
    "            },\n",
    label="scoped ingestion metadata",
)
replace_once(
    FILES,
    "        adapter: ChannelAdapter,\n    ) -> None:\n"
    "        self.session = session\n"
    "        self.connection = connection\n"
    "        self.adapter = adapter\n",
    "        adapter: ChannelAdapter,\n"
    "        scanner: ChannelFileScanner | None = None,\n"
    "    ) -> None:\n"
    "        self.session = session\n"
    "        self.connection = connection\n"
    "        self.adapter = adapter\n"
    "        self.scanner = scanner or BuiltinChannelFileScanner()\n",
    label="injectable file scanner",
)
replace_once(
    FILES,
    '            if not content:\n                raise ValueError("文件内容为空。")\n\n'
    "            user_file, _stored_filename = await self._store_user_file(\n",
    '            if not content:\n                raise ValueError("文件内容为空。")\n\n'
    "            declared_mime_type = attachment.mime_type or provider_metadata.get(\"content_type\")\n"
    "            scan_result = self.scanner.scan(\n"
    "                filename=safe_filename,\n"
    "                content=content,\n"
    "                declared_mime_type=str(declared_mime_type) if declared_mime_type else None,\n"
    "            )\n\n"
    "            user_file, _stored_filename = await self._store_user_file(\n",
    label="scan before persistence",
)
replace_once(
    FILES,
    "            asset.mime_type = attachment.mime_type or provider_metadata.get(\"content_type\")\n"
    "            asset.status = ChannelFileStatus.STORED.value\n"
    "            asset.metadata_data = {**asset.metadata_data, **provider_metadata}\n",
    "            asset.mime_type = scan_result.detected_mime_type\n"
    "            asset.status = ChannelFileStatus.STORED.value\n"
    "            asset.metadata_data = {\n"
    "                **asset.metadata_data,\n"
    "                **provider_metadata,\n"
    '                "security_scan": scan_result.as_metadata(),\n'
    "            }\n",
    label="persist scan result",
)
replace_once(
    FILES,
    "            if binding is not None and binding.knowledge_base_id is not None:\n"
    "                job_id, kb_name = await self._queue_knowledge_base_ingestion(\n"
    "                    event=event,\n"
    "                    user=user,\n"
    "                    binding=binding,\n",
    "            knowledge_base_id = effective_channel_knowledge_base_id(self.connection, binding)\n"
    "            if knowledge_base_id is not None:\n"
    "                job_id, kb_name = await self._queue_knowledge_base_ingestion(\n"
    "                    event=event,\n"
    "                    user=user,\n"
    "                    binding=binding,\n"
    "                    kb_id=knowledge_base_id,\n",
    label="effective knowledge base fallback",
)
replace_between(
    FILES,
    "    async def _queue_knowledge_base_ingestion(\n",
    "    @staticmethod\n    def _existing_asset_message",
    QUEUE_FUNCTION,
    label="scoped knowledge base ingestion",
)
