import socket

from ndp.scan.dns import resolve_hostname


def test_resolve_hostname_localhost(monkeypatch) -> None:
    def fake_getaddrinfo(hostname, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    result = resolve_hostname("localhost")
    assert result.addresses == ["127.0.0.1"]
    assert result.error is None


def test_resolve_hostname_failure(monkeypatch) -> None:
    def fake_getaddrinfo(hostname, port, *args, **kwargs):
        raise socket.gaierror("Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    result = resolve_hostname("missing.invalid")
    assert result.addresses == []
    assert result.error is not None
