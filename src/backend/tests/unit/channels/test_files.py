import pytest
from langflow.channels.services.files import sanitize_channel_filename


@pytest.mark.parametrize(
    "filename",
    [
        "../secret.txt",
        "folder/report.pdf",
        "folder\\report.pdf",
        "bad\x00name.txt",
        "line\nfeed.txt",
        "",
    ],
)
def test_sanitize_channel_filename_rejects_unsafe_names(filename: str) -> None:
    with pytest.raises(ValueError):
        sanitize_channel_filename(filename)


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("report.pdf", "report.pdf"),
        ("销售报表 2026.xlsx", "销售报表 2026.xlsx"),
        ("notes.md", "notes.md"),
    ],
)
def test_sanitize_channel_filename_accepts_safe_names(filename: str, expected: str) -> None:
    assert sanitize_channel_filename(filename) == expected
