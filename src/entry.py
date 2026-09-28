"""
Cloudflare Python Workers Entry Point for InSave Hub (Django WSGI Integration).

Bridges the Cloudflare Workers Fetch API (`Request` / `Response`) and Worker
environment bindings (`D1`, `R2`, `ASSETS`, Secrets) to Django's WSGI callable.
"""
import io
import os
import sys
from urllib.parse import urlsplit

from config.d1_bridge import set_worker_d1_binding

try:
    from workers import Response, WorkerEntrypoint
except ImportError:
    class WorkerEntrypoint:  # type: ignore[no-redef]
        env = None
        ctx = None

    class Response:  # type: ignore[no-redef]
        def __init__(self, body=b"", status=200, headers=None):
            self.body = body
            self.status = status
            self.headers = headers or {}


_WSGI_APP = None

ENV_KEYS_TO_SYNC = (
    "DJANGO_SETTINGS_MODULE",
    "DJANGO_ENV",
    "DJANGO_DEBUG",
    "DJANGO_SECRET_KEY",
    "DJANGO_ALLOWED_HOSTS",
    "CSRF_TRUSTED_ORIGINS",
    "CANONICAL_BASE_URL",
    "DATABASE_URL",
    "USE_CLOUDFLARE_D1",
    "USE_CLOUDFLARE_R2",
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "GOOGLE_OAUTH_REDIRECT_URI",
    "PAYMENT_PROVIDER",
    "DONATION_CURRENCY",
    "RAZORPAY_KEY_ID",
    "RAZORPAY_KEY_SECRET",
    "RAZORPAY_WEBHOOK_SECRET",
    "AD_COUNTDOWN_SECONDS",
    "FREE_ACCESS_HOURS",
    "FREE_DOWNLOADS_BEFORE_AD",
)


def sync_worker_env(env) -> None:
    """Propagate Cloudflare Worker environment variables and bindings into Python runtime."""
    if env is None:
        return
    for key in ENV_KEYS_TO_SYNC:
        val = getattr(env, key, None)
        if val is not None and isinstance(val, (str, int, float, bool)):
            os.environ[key] = str(val)

    d1_binding = getattr(env, "DB", None)
    if d1_binding is not None:
        set_worker_d1_binding(d1_binding)


def get_django_wsgi_app(env):
    """Lazily initialize and return the Django WSGI application."""
    global _WSGI_APP
    sync_worker_env(env)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    if _WSGI_APP is None:
        from config.wsgi import application

        _WSGI_APP = application
    return _WSGI_APP


async def invoke_wsgi(wsgi_app, request, env) -> Response:
    """Translate a Cloudflare Fetch Request into a PEP 3333 WSGI environ call."""
    parsed = urlsplit(str(request.url))
    method = str(getattr(request, "method", "GET")).upper()
    host_header = parsed.netloc or "localhost"
    if ":" in host_header:
        server_name, server_port = host_header.split(":", 1)
    else:
        server_name = host_header
        server_port = "443" if parsed.scheme == "https" else "80"

    body_bytes = b""
    if method not in ("GET", "HEAD", "OPTIONS"):
        if hasattr(request, "bytes"):
            body_bytes = bytes(await request.bytes())
        elif hasattr(request, "text"):
            body_bytes = (await request.text()).encode("utf-8")

    environ = {
        "REQUEST_METHOD": method,
        "SCRIPT_NAME": "",
        "PATH_INFO": parsed.path or "/",
        "QUERY_STRING": parsed.query or "",
        "SERVER_NAME": server_name,
        "SERVER_PORT": server_port,
        "SERVER_PROTOCOL": "HTTP/1.1",
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": parsed.scheme or "https",
        "wsgi.input": io.BytesIO(body_bytes),
        "wsgi.errors": sys.stderr,
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
        "CONTENT_LENGTH": str(len(body_bytes)),
        "cloudflare.env": env,
    }

    headers = getattr(request, "headers", None)
    if headers:
        items = headers.items() if hasattr(headers, "items") else headers
        for k, v in items:
            key_upper = str(k).upper().replace("-", "_")
            if key_upper == "CONTENT_TYPE":
                environ["CONTENT_TYPE"] = str(v)
            elif key_upper == "CONTENT_LENGTH":
                environ["CONTENT_LENGTH"] = str(v)
            else:
                environ[f"HTTP_{key_upper}"] = str(v)

    status_Holder = {"code": 200, "headers": []}

    def start_response(status_str, response_headers, exc_info=None):
        code_str = status_str.split(" ", 1)[0]
        status_Holder["code"] = int(code_str)
        status_Holder["headers"] = list(response_headers)
        return lambda _data: None

    result_iter = wsgi_app(environ, start_response)
    output_chunks = []
    try:
        for chunk in result_iter:
            if isinstance(chunk, str):
                output_chunks.append(chunk.encode("utf-8"))
            else:
                output_chunks.append(bytes(chunk))
    finally:
        if hasattr(result_iter, "close"):
            result_iter.close()

    response_body = b"".join(output_chunks)
    return Response(
        response_body,
        status=status_Holder["code"],
        headers=status_Holder["headers"],
    )


class Default(WorkerEntrypoint):
    """Primary Cloudflare Python Worker Entrypoint."""

    async def fetch(self, request):
        # Serve static files directly from Cloudflare Assets binding when available
        parsed = urlsplit(str(request.url))
        assets_binding = getattr(self.env, "ASSETS", None)
        if assets_binding is not None and parsed.path.startswith("/static/"):
            try:
                return await assets_binding.fetch(request)
            except Exception:
                pass

        wsgi_app = get_django_wsgi_app(self.env)
        return await invoke_wsgi(wsgi_app, request, self.env)
