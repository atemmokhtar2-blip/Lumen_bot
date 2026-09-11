"""Minimal aiohttp.web stub so Phase E pen tests run without installing aiohttp."""
from __future__ import annotations


class HTTPException(Exception):
    status_code = 500

    def __init__(self, *, text: str = "", content_type: str | None = None, headers: dict | None = None):
        self.text = text
        self.content_type = content_type
        self.headers = headers or {}
        super().__init__(text)


class HTTPUnauthorized(HTTPException):
    status_code = 401


class HTTPForbidden(HTTPException):
    status_code = 403


class HTTPServiceUnavailable(HTTPException):
    status_code = 503


class HTTPTooManyRequests(HTTPException):
    status_code = 429


class HTTPBadRequest(HTTPException):
    status_code = 400


class HTTPNotFound(HTTPException):
    status_code = 404


class HTTPPaymentRequired(HTTPException):
    status_code = 402


class _Web:
    HTTPException = HTTPException
    HTTPUnauthorized = HTTPUnauthorized
    HTTPForbidden = HTTPForbidden
    HTTPServiceUnavailable = HTTPServiceUnavailable
    HTTPTooManyRequests = HTTPTooManyRequests
    HTTPBadRequest = HTTPBadRequest
    HTTPNotFound = HTTPNotFound
    HTTPPaymentRequired = HTTPPaymentRequired

    @staticmethod
    def middleware(fn):
        return fn

    @staticmethod
    def json_response(data, status=200):
        return SimpleResponse(data, status)


class SimpleResponse:
    def __init__(self, data, status=200):
        self.data = data
        self.status = status


web = _Web()


def install_aiohttp_stub() -> None:
    """Register stub only if real aiohttp is missing."""
    import sys
    import types

    try:
        import aiohttp  # noqa: F401
        return
    except ImportError:
        pass
    pkg = types.ModuleType("aiohttp")
    pkg.web = web
    sys.modules["aiohttp"] = pkg
    sys.modules["aiohttp.web"] = web
