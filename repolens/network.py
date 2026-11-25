"""Read an existing Windows manual proxy without changing OS/Git settings."""

from urllib.parse import urlsplit

from repolens.mining import RepositoryError


def validate_proxy(value: str) -> str:
    try:
        parsed = urlsplit(value)
        port = parsed.port
        if (parsed.scheme not in ("http", "https", "socks5", "socks5h") or not parsed.hostname
                or not port or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in ("", "/")):
            raise ValueError("invalid proxy")
    except ValueError as exc:
        raise RepositoryError("系统代理地址格式不受支持；需要不含账号密码的 HTTP/HTTPS/SOCKS 地址和端口。") from exc
    return value.rstrip("/")


def parse_windows_proxy(enabled, server):
    if not enabled or not isinstance(server, str) or not server.strip():
        return None
    parts = dict(part.strip().split("=", 1) for part in server.split(";") if "=" in part)
    if parts:
        value = parts.get("https") or parts.get("http")
        scheme = "http"
        if not value:
            value, scheme = parts.get("socks"), "socks5h"
    else:
        value, scheme = server.strip(), "http"
    if not value:
        return None
    value = value.strip()
    try:
        return validate_proxy(value if "://" in value else scheme + "://" + value)
    except RepositoryError:
        return None


def windows_proxy():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Internet Settings") as key:
            enabled = winreg.QueryValueEx(key, "ProxyEnable")[0]
            server = winreg.QueryValueEx(key, "ProxyServer")[0]
        return parse_windows_proxy(enabled, server)
    except (ImportError, OSError):
        return None
