"""Only explicitly configured Caddy peers can supply client identity/protocol."""

from collections.abc import Callable
from ipaddress import IPv6Address, ip_address

from django.conf import settings
from django.http import HttpRequest, HttpResponse


def canonical_ip(value: str) -> str | None:
    if "%" in value:
        return None
    try:
        address = ip_address(value)
    except ValueError:
        return None
    if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
        return str(address.ipv4_mapped)
    return str(address)


def trusted_peer(request: HttpRequest) -> bool:
    return (
        settings.APP_ENV == "production"
        and canonical_ip(request.META.get("REMOTE_ADDR", "")) in settings.TRUSTED_PROXY_IPS
    )


def client_ip(request: HttpRequest) -> str:
    peer = canonical_ip(request.META.get("REMOTE_ADDR", ""))
    if trusted_peer(request):
        client = canonical_ip(request.META.get("HTTP_X_REAL_IP", ""))
        if client is not None:
            return client
    # Invalid/missing forwarding data cannot create arbitrary fresh rate buckets.
    return peer or "unknown"


class TrustedProxyMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if settings.APP_ENV == "production" and not trusted_peer(request):
            peer = canonical_ip(request.META.get("REMOTE_ADDR", ""))
            local_health = peer in {"127.0.0.1", "::1"} and request.path in {
                "/health/live/",
                "/health/ready/",
            }
            for header in (
                "HTTP_X_REAL_IP",
                "HTTP_X_FORWARDED_FOR",
                "HTTP_X_FORWARDED_HOST",
                "HTTP_X_FORWARDED_PROTO",
            ):
                if header == "HTTP_X_FORWARDED_PROTO" and local_health:
                    continue  # Container loopback readiness probe; never a public path.
                request.META.pop(header, None)
        return self.get_response(request)
