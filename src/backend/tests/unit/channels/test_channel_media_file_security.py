from __future__ import annotations

import pytest
from langflow.channels.services.file_security import BuiltinChannelFileScanner


def _jpeg(*, width: int = 1, height: int = 1) -> bytes:
    frame = (
        b"\xff\xc0"
        + (17).to_bytes(2, "big")
        + b"\x08"
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + b"\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00"
    )
    return b"\xff\xd8" + frame + b"\xff\xd9"


def _mp4() -> bytes:
    return b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2"


@pytest.mark.parametrize("extension", [".jpg", ".jpeg"])
def test_scanner_accepts_jpeg_and_records_dimensions(extension: str) -> None:
    result = BuiltinChannelFileScanner().scan(
        filename=f"photo{extension}",
        content=_jpeg(width=1920, height=1080),
        declared_mime_type="application/octet-stream",
    )

    assert result.detected_mime_type == "image/jpeg"
    assert result.metadata["media_kind"] == "image"
    assert result.metadata["width"] == 1920
    assert result.metadata["height"] == 1080
    assert result.metadata["scanner_version"] == 2


@pytest.mark.parametrize(
    ("extension", "expected_mime_type"),
    [(".mp4", "video/mp4"), (".m4v", "video/mp4"), (".mov", "video/quicktime")],
)
def test_scanner_accepts_iso_bmff_video(extension: str, expected_mime_type: str) -> None:
    result = BuiltinChannelFileScanner().scan(filename=f"clip{extension}", content=_mp4())

    assert result.detected_mime_type == expected_mime_type
    assert result.metadata["media_kind"] == "video"
    assert result.metadata["container"] == "iso-bmff"
    assert result.metadata["major_brand"] == "isom"


def test_scanner_rejects_content_that_does_not_match_media_extension() -> None:
    scanner = BuiltinChannelFileScanner()

    with pytest.raises(ValueError, match="不是有效的 JPEG"):
        scanner.scan(filename="photo.jpg", content=_mp4())

    with pytest.raises(ValueError, match="不是有效的 MP4/MOV"):
        scanner.scan(filename="clip.mp4", content=_jpeg())


def test_scanner_rejects_image_pixel_bomb() -> None:
    scanner = BuiltinChannelFileScanner(max_image_pixels=1_000_000)

    with pytest.raises(ValueError, match="像素数量超过安全限制"):
        scanner.scan(filename="huge.jpg", content=_jpeg(width=2000, height=2000))


def test_scanner_remains_fail_closed_for_unregistered_binary_types() -> None:
    with pytest.raises(ValueError, match="没有可用于 .bin 文件的内容校验器"):
        BuiltinChannelFileScanner().scan(filename="payload.bin", content=b"binary payload")
