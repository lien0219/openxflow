"""Tests for URLComponent input type configuration."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def url_component(monkeypatch):
    """Import URLComponent with heavy third-party modules stubbed for this test."""
    for mod in (
        "langchain_community",
        "langchain_community.document_loaders",
        "markitdown",
        "bs4",
        "lxml",
    ):
        monkeypatch.setitem(sys.modules, mod, MagicMock())

    from lfx.components.data_source.url import URLComponent

    return URLComponent


class TestURLComponentInputTypes:
    """Verify the urls input accepts Message as an input type."""

    def test_urls_input_accepts_message_type(self, url_component):
        urls_input = next(inp for inp in url_component.inputs if inp.name == "urls")
        assert "Message" in urls_input.input_types

    def test_urls_input_is_list(self, url_component):
        urls_input = next(inp for inp in url_component.inputs if inp.name == "urls")
        assert urls_input.is_list is True

    def test_follow_redirects_input_defaults_to_true(self, url_component):
        """Redirects must be followed by default so canonical http->https / www hops resolve."""
        follow_redirects_input = next(inp for inp in url_component.inputs if inp.name == "follow_redirects")
        assert follow_redirects_input.value is True

    def test_import_does_not_load_dotenv_into_process_environment(self):
        """Importing a component must not apply the repository .env to the test process."""
        project_root = Path(__file__).parents[6]
        script = (
            "import os; "
            "assert os.getenv('LANGFLOW_SSRF_PROTECTION_ENABLED') is None; "
            "assert os.getenv('LANGFLOW_SSRF_ALLOWED_HOSTS') is None; "
            "import lfx.components.data_source.url; "
            "assert os.getenv('LANGFLOW_SSRF_PROTECTION_ENABLED') is None; "
            "assert os.getenv('LANGFLOW_SSRF_ALLOWED_HOSTS') is None"
        )
        env = os.environ.copy()
        env.pop("LANGFLOW_SSRF_PROTECTION_ENABLED", None)
        env.pop("LANGFLOW_SSRF_ALLOWED_HOSTS", None)
        result = subprocess.run(  # noqa: S603 - fixed test script using this interpreter, no shell
            [sys.executable, "-c", script],
            cwd=project_root,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr or result.stdout


class TestHeadersForRedirect:
    """Verify sensitive headers are only kept across same-origin (or https-upgrade) redirects."""

    HEADERS = {"Authorization": "Bearer token", "Cookie": "session=1", "User-Agent": "Test"}

    def test_same_origin_keeps_headers(self, url_component):
        result = url_component._headers_for_redirect(self.HEADERS, "https://a.test/x", "https://a.test/y")
        assert result == self.HEADERS

    def test_https_upgrade_keeps_headers(self, url_component):
        """Direct http->https upgrade on default ports keeps headers, matching httpx."""
        result = url_component._headers_for_redirect(self.HEADERS, "http://a.test/x", "https://a.test/x")
        assert result == self.HEADERS

    def test_https_downgrade_drops_sensitive_headers(self, url_component):
        """https->http is a different origin; credentials must not leak to plaintext."""
        result = url_component._headers_for_redirect(self.HEADERS, "https://a.test/x", "http://a.test/x")
        assert result == {"User-Agent": "Test"}

    def test_port_change_drops_sensitive_headers(self, url_component):
        """Same host on another port is a different origin (possibly a different service)."""
        result = url_component._headers_for_redirect(self.HEADERS, "https://a.test/x", "https://a.test:8443/x")
        assert result == {"User-Agent": "Test"}

    def test_cross_host_drops_sensitive_headers(self, url_component):
        result = url_component._headers_for_redirect(self.HEADERS, "https://a.test/x", "https://b.test/x")
        assert result == {"User-Agent": "Test"}

    def test_explicit_default_port_is_same_origin(self, url_component):
        result = url_component._headers_for_redirect(self.HEADERS, "https://a.test/x", "https://a.test:443/y")
        assert result == self.HEADERS
