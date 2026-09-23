"""The client's IP as Caddy resolved it. Caddy sets X-Real-IP on every request (from
CF-Connecting-IP only when the peer is a Cloudflare range), and in production the app is reachable
only through Caddy, so the header can't be spoofed."""


def client_ip(request) -> str:
    forwarded = request.headers.get("x-real-ip")
    if forwarded:
        return forwarded.strip()
    return request.client.host if request.client else "unknown"   # local dev, no proxy
