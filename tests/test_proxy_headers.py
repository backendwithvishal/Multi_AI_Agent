from starlette.requests import Request

from tripmate.config.settings import settings
from tripmate.middleware import SlidingWindowRateLimiter


def create_mock_request(client_ip: str, headers_dict: dict = None) -> Request:
    """Helper creating a Starlette Request with specified client address and headers."""
    headers = []
    if headers_dict:
        for k, v in headers_dict.items():
            headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/health",
        "headers": headers,
        "client": (client_ip, 50000),
    }
    return Request(scope)


def test_client_ip_from_trusted_proxy(monkeypatch):
    """When peer is a trusted proxy, client IP is taken from X-Forwarded-For."""
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", ["10.0.0.1", "127.0.0.1"])
    limiter = SlidingWindowRateLimiter(app=None)

    req = create_mock_request(client_ip="10.0.0.1", headers_dict={"X-Forwarded-For": "203.0.113.195"})
    extracted_ip = limiter._get_client_ip(req)
    assert extracted_ip == "203.0.113.195"


def test_client_ip_ignored_from_untrusted_proxy(monkeypatch):
    """When peer is NOT in TRUSTED_PROXIES, X-Forwarded-For is ignored and peer IP is kept."""
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", ["10.0.0.1"])
    limiter = SlidingWindowRateLimiter(app=None)

    # Peer 198.51.100.22 is NOT trusted
    req = create_mock_request(client_ip="198.51.100.22", headers_dict={"X-Forwarded-For": "203.0.113.195"})
    extracted_ip = limiter._get_client_ip(req)
    assert extracted_ip == "198.51.100.22", "Untrusted proxy must not be allowed to spoof client IP"


def test_multi_hop_x_forwarded_for_from_trusted_proxy(monkeypatch):
    """When multiple hops are present in X-Forwarded-For, extracts original client IP from trusted proxy."""
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", ["10.0.0.1"])
    limiter = SlidingWindowRateLimiter(app=None)

    req = create_mock_request(client_ip="10.0.0.1", headers_dict={"X-Forwarded-For": "203.0.113.195, 10.0.0.2"})
    extracted_ip = limiter._get_client_ip(req)
    assert extracted_ip == "203.0.113.195"
