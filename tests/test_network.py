import pytest

from repolens import remote
from repolens.mining import RepositoryError
from repolens.network import parse_windows_proxy, validate_proxy


def test_windows_shared_and_per_protocol_proxies():
    assert parse_windows_proxy(1, "127.0.0.1:7897") == "http://127.0.0.1:7897"
    assert parse_windows_proxy(1, "http=127.0.0.1:8080;https=127.0.0.1:7897") == "http://127.0.0.1:7897"
    assert parse_windows_proxy(1, "socks=127.0.0.1:1080") == "socks5h://127.0.0.1:1080"
    assert parse_windows_proxy(0, "127.0.0.1:7897") is None
    assert parse_windows_proxy(1, "") is None
    assert parse_windows_proxy(1, "bad-proxy") is None


@pytest.mark.parametrize("proxy", ["file:///tmp/a", "http://localhost", "http://localhost:invalid", "http://user:password@localhost:8080", "http://localhost:8080/path"])
def test_rejects_invalid_or_credential_bearing_proxy(proxy):
    with pytest.raises(RepositoryError):
        validate_proxy(proxy)


def test_proxy_is_process_local_and_not_written_to_git(monkeypatch):
    captured = {}

    class Process:
        returncode = 0

        def __init__(self, command, **kwargs):
            captured["command"] = command

        def communicate(self, timeout):
            return "success", ""

    monkeypatch.setattr(remote.subprocess, "Popen", Process)
    assert remote._run_git(["ls-remote", "https://github.com/example/repo.git"], proxy="http://127.0.0.1:7897") == "success"
    assert "http.proxy=http://127.0.0.1:7897" in captured["command"]
    assert "config" not in captured["command"]
