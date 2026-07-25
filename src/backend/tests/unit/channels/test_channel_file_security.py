from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from langflow.channels.services.file_security import BuiltinChannelFileScanner
from langflow.channels.services.files import (
    effective_channel_knowledge_base_id,
    resolve_channel_knowledge_base_access,
)


def _office_archive(*, document_path: str = "word/document.xml", extra: dict[str, bytes] | None = None) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", b"<Types />")
        archive.writestr(document_path, b"<document>Hello</document>")
        for name, content in (extra or {}).items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_scanner_accepts_pdf_and_records_hash() -> None:
    result = BuiltinChannelFileScanner().scan(
        filename="report.pdf",
        content=b"%PDF-1.7\n1 0 obj\n",
        declared_mime_type="application/octet-stream",
    )

    assert result.detected_mime_type == "application/pdf"
    assert result.metadata["sha256"]
    assert result.metadata["declared_mime_type"] == "application/octet-stream"


@pytest.mark.parametrize("payload", [b"MZ" + b"0" * 32, b"\x7fELF" + b"0" * 32])
def test_scanner_rejects_executable_disguised_as_document(payload: bytes) -> None:
    with pytest.raises(ValueError, match="可执行文件"):
        BuiltinChannelFileScanner().scan(filename="invoice.pdf", content=payload)


def test_scanner_accepts_minimal_docx() -> None:
    result = BuiltinChannelFileScanner().scan(filename="notes.docx", content=_office_archive())

    assert result.metadata["archive_entries"] == 2
    assert result.detected_mime_type.endswith("wordprocessingml.document")


def test_scanner_rejects_archive_path_traversal() -> None:
    content = _office_archive(extra={"../outside.txt": b"escape"})

    with pytest.raises(ValueError, match="不安全的路径"):
        BuiltinChannelFileScanner().scan(filename="notes.docx", content=content)


def test_scanner_rejects_office_macros() -> None:
    content = _office_archive(extra={"word/vbaProject.bin": b"macro"})

    with pytest.raises(ValueError, match="宏"):
        BuiltinChannelFileScanner().scan(filename="notes.docx", content=content)


def test_scanner_rejects_high_compression_ratio() -> None:
    content = _office_archive(extra={"word/large.txt": b"0" * 50_000})
    scanner = BuiltinChannelFileScanner(max_archive_ratio=5)

    with pytest.raises(ValueError, match="压缩比"):
        scanner.scan(filename="notes.docx", content=content)


def test_scanner_rejects_binary_content_with_text_extension() -> None:
    with pytest.raises(ValueError, match="NUL"):
        BuiltinChannelFileScanner().scan(filename="notes.txt", content=b"hello\x00world")


def test_effective_kb_prefers_conversation_override_then_connection_default() -> None:
    default_id = uuid4()
    override_id = uuid4()
    connection = SimpleNamespace(default_knowledge_base_id=default_id)

    assert (
        effective_channel_knowledge_base_id(connection, SimpleNamespace(knowledge_base_id=override_id))
        == override_id
    )
    assert effective_channel_knowledge_base_id(connection, None) == default_id


def test_service_identity_receives_only_explicit_owner_kb_delegation() -> None:
    connection_id = uuid4()
    owner = SimpleNamespace(id=uuid4())
    knowledge_base = SimpleNamespace(id=uuid4(), user_id=owner.id)
    connection = SimpleNamespace(
        id=connection_id,
        user_id=owner.id,
        default_knowledge_base_id=knowledge_base.id,
    )
    service_user = SimpleNamespace(
        id=uuid4(),
        optins={
            "channel_service_identity": True,
            "channel_connection_id": str(connection_id),
        },
    )

    access = resolve_channel_knowledge_base_access(
        connection=connection,
        binding=None,
        execution_user=service_user,
        connection_owner=owner,
        knowledge_base=knowledge_base,
    )

    assert access.resource_owner is owner
    assert access.delegated is True


def test_service_identity_cannot_ingest_into_unscoped_owner_kb() -> None:
    connection_id = uuid4()
    owner = SimpleNamespace(id=uuid4())
    connection = SimpleNamespace(
        id=connection_id,
        user_id=owner.id,
        default_knowledge_base_id=None,
    )
    service_user = SimpleNamespace(
        id=uuid4(),
        optins={
            "channel_service_identity": True,
            "channel_connection_id": str(connection_id),
        },
    )
    knowledge_base = SimpleNamespace(id=uuid4(), user_id=owner.id)

    with pytest.raises(ValueError, match="显式授权"):
        resolve_channel_knowledge_base_access(
            connection=connection,
            binding=None,
            execution_user=service_user,
            connection_owner=owner,
            knowledge_base=knowledge_base,
        )


def test_personal_identity_must_own_target_kb() -> None:
    connection = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        default_knowledge_base_id=None,
    )
    personal_user = SimpleNamespace(id=uuid4(), optins={})
    owner = SimpleNamespace(id=connection.user_id)
    foreign_kb = SimpleNamespace(id=uuid4(), user_id=uuid4())

    with pytest.raises(ValueError, match="不属于当前账号"):
        resolve_channel_knowledge_base_access(
            connection=connection,
            binding=SimpleNamespace(knowledge_base_id=foreign_kb.id),
            execution_user=personal_user,
            connection_owner=owner,
            knowledge_base=foreign_kb,
        )
