"""Fail-closed content validation for files received from chat providers."""

from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

_TEXT_EXTENSIONS = {
    ".csv",
    ".htm",
    ".html",
    ".json",
    ".markdown",
    ".md",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
_OFFICE_ARCHIVE_MARKERS = {
    ".docx": "word/document.xml",
    ".xlsx": "xl/workbook.xml",
    ".pptx": "ppt/presentation.xml",
}
_LEGACY_OFFICE_EXTENSIONS = {".doc", ".xls", ".ppt"}
_EXECUTABLE_SIGNATURES = (
    (b"MZ", "Windows PE"),
    (b"\x7fELF", "ELF"),
    (b"\xfe\xed\xfa\xce", "Mach-O"),
    (b"\xce\xfa\xed\xfe", "Mach-O"),
    (b"\xfe\xed\xfa\xcf", "Mach-O"),
    (b"\xcf\xfa\xed\xfe", "Mach-O"),
    (b"\xca\xfe\xba\xbe", "Java class"),
    (b"\x00asm", "WebAssembly"),
)
_MACRO_MARKERS = ("vbaproject.bin", "vbadata.xml", "xl/macrosheets/", "word/vba", "ppt/vba")
_OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


@dataclass(frozen=True)
class ChannelFileScanResult:
    """Normalized result persisted with the channel file asset."""

    detected_mime_type: str
    scanner: str = "builtin"
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_metadata(self) -> dict[str, Any]:
        return {
            "scanner": self.scanner,
            "detected_mime_type": self.detected_mime_type,
            **self.metadata,
        }


class ChannelFileScanner(Protocol):
    """Extension point for built-in or external antivirus scanners."""

    def scan(
        self,
        *,
        filename: str,
        content: bytes,
        declared_mime_type: str | None = None,
    ) -> ChannelFileScanResult:
        """Validate content or raise ``ValueError`` before persistence."""


class BuiltinChannelFileScanner:
    """Validate signatures, archives and text without trusting provider MIME data."""

    def __init__(
        self,
        *,
        max_archive_entries: int = 2_000,
        max_archive_uncompressed_bytes: int = 256 * 1024 * 1024,
        max_archive_ratio: float = 200.0,
    ) -> None:
        self.max_archive_entries = max_archive_entries
        self.max_archive_uncompressed_bytes = max_archive_uncompressed_bytes
        self.max_archive_ratio = max_archive_ratio

    def scan(
        self,
        *,
        filename: str,
        content: bytes,
        declared_mime_type: str | None = None,
    ) -> ChannelFileScanResult:
        if not content:
            raise ValueError("文件内容为空。")

        extension = Path(filename).suffix.lower()
        self._reject_executable_signature(content)

        archive_metadata: dict[str, Any] = {}
        if extension == ".pdf":
            if not content.startswith(b"%PDF-"):
                raise ValueError("文件扩展名与实际内容不一致：不是有效的 PDF。")
            lowered_pdf = content.lower()
            if any(marker in lowered_pdf for marker in (b"/javascript", b"/js", b"/launch", b"/embeddedfile")):
                raise ValueError("PDF 包含脚本、启动动作或嵌入文件，已拒绝处理。")
            detected_mime_type = "application/pdf"
        elif extension in _LEGACY_OFFICE_EXTENSIONS:
            if not content.startswith(_OLE_SIGNATURE):
                raise ValueError("文件扩展名与实际内容不一致：不是有效的旧版 Office 文件。")
            raise ValueError("旧版 Office 二进制格式无法可靠检查宏，请转换为 docx、xlsx 或 pptx。")
        elif extension in _OFFICE_ARCHIVE_MARKERS:
            archive_metadata = self._validate_office_archive(extension, content)
            detected_mime_type = {
                ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            }[extension]
        elif extension == ".rtf":
            if not content.lstrip().startswith(b"{\\rtf"):
                raise ValueError("文件扩展名与实际内容不一致：不是有效的 RTF。")
            detected_mime_type = "application/rtf"
        elif extension in _TEXT_EXTENSIONS:
            decoded = self._decode_text(content)
            if extension == ".json":
                try:
                    json.loads(decoded)
                except json.JSONDecodeError as exc:
                    raise ValueError("JSON 文件格式无效。") from exc
            detected_mime_type = {
                ".csv": "text/csv",
                ".htm": "text/html",
                ".html": "text/html",
                ".json": "application/json",
                ".markdown": "text/markdown",
                ".md": "text/markdown",
                ".xml": "application/xml",
                ".yaml": "application/yaml",
                ".yml": "application/yaml",
            }.get(extension, "text/plain")
        else:
            raise ValueError(f"没有可用于 {extension or '无扩展名'} 文件的内容校验器。")

        return ChannelFileScanResult(
            detected_mime_type=detected_mime_type,
            metadata={
                "scanner_version": 1,
                "extension": extension,
                "declared_mime_type": declared_mime_type,
                "sha256": hashlib.sha256(content).hexdigest(),
                **archive_metadata,
            },
        )

    @staticmethod
    def _reject_executable_signature(content: bytes) -> None:
        prefix = content[:8]
        for signature, label in _EXECUTABLE_SIGNATURES:
            if prefix.startswith(signature):
                raise ValueError(f"检测到伪装的可执行文件（{label}），已拒绝处理。")

    def _validate_office_archive(self, extension: str, content: bytes) -> dict[str, Any]:
        try:
            archive = zipfile.ZipFile(BytesIO(content))
        except zipfile.BadZipFile as exc:
            raise ValueError("Office 文件压缩结构无效。") from exc

        with archive:
            infos = archive.infolist()
            if len(infos) > self.max_archive_entries:
                raise ValueError("压缩包文件数量异常，可能存在压缩炸弹。")

            names: set[str] = set()
            total_uncompressed = 0
            total_compressed = 0
            for info in infos:
                normalized_name = info.filename.replace("\\", "/")
                path = PurePosixPath(normalized_name)
                if (
                    not normalized_name
                    or normalized_name.startswith("/")
                    or path.is_absolute()
                    or ".." in path.parts
                    or (path.parts and ":" in path.parts[0])
                ):
                    raise ValueError("压缩包包含不安全的路径。")

                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise ValueError("压缩包包含符号链接，已拒绝处理。")

                lowered = normalized_name.lower()
                if any(marker in lowered for marker in _MACRO_MARKERS):
                    raise ValueError("Office 文件包含宏或可执行脚本，已拒绝处理。")

                names.add(lowered)
                total_uncompressed += info.file_size
                total_compressed += info.compress_size
                if total_uncompressed > self.max_archive_uncompressed_bytes:
                    raise ValueError("压缩包解压后体积超过安全限制。")
                if info.file_size and info.compress_size == 0:
                    raise ValueError("压缩包压缩比异常，可能存在压缩炸弹。")
                if info.compress_size and info.file_size / info.compress_size > self.max_archive_ratio:
                    raise ValueError("压缩包压缩比异常，可能存在压缩炸弹。")

            if total_compressed and total_uncompressed / total_compressed > self.max_archive_ratio:
                raise ValueError("压缩包整体压缩比异常，可能存在压缩炸弹。")

            required = _OFFICE_ARCHIVE_MARKERS[extension]
            if "[content_types].xml" not in names or required not in names:
                raise ValueError("Office 文件缺少必要结构，扩展名与实际内容不一致。")

            return {
                "archive_entries": len(infos),
                "archive_uncompressed_bytes": total_uncompressed,
                "archive_compressed_bytes": total_compressed,
            }

    @staticmethod
    def _decode_text(content: bytes) -> str:
        if content.startswith((b"\xff\xfe", b"\xfe\xff")):
            try:
                return content.decode("utf-16")
            except UnicodeDecodeError as exc:
                raise ValueError("文本文件编码无效。") from exc

        if b"\x00" in content:
            raise ValueError("文本文件包含二进制 NUL 字节，扩展名与实际内容不一致。")

        for encoding in ("utf-8-sig", "gb18030"):
            try:
                decoded = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError("文本文件编码无法识别。")

        control_count = sum(ord(char) < 32 and char not in "\t\n\r\f" for char in decoded)
        if decoded and control_count / len(decoded) > 0.02:
            raise ValueError("文本文件包含过多控制字符，可能是二进制文件。")
        return decoded
