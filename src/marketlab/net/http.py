from __future__ import annotations

from typing import Any, Iterable, Mapping, MutableMapping
from urllib.parse import urljoin, urlparse

import requests

DEFAULT_TIMEOUT = 5.0
DEFAULT_SCHEMES = frozenset({"http", "https"})


class SchemeNotAllowedError(ValueError):
    """Raised when a URL uses a rejected scheme."""


class HostNotAllowedError(ValueError):
    """Raised when a URL points to a host outside the allow-list."""


class RedirectNotAllowedError(RuntimeError):
    """Raised when an HTTP redirect would violate the allow-list rules."""


def _normalize_host(host: str) -> str:
    return host.lower()


def _validate_url(url: str, allow_hosts: set[str], allowed_schemes: set[str]) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in allowed_schemes:
        raise SchemeNotAllowedError(f"Scheme '{parsed.scheme}' is not permitted.")
    host = parsed.hostname or ""
    if _normalize_host(host) not in allow_hosts:
        raise HostNotAllowedError(f"Host '{host}' is not in the allow-list.")


def _request(
    method: str,
    url: str,
    *,
    allow_hosts: set[str],
    allowed_schemes: set[str],
    timeout: float,
    params: Mapping[str, Any] | None = None,
    json: Mapping[str, Any] | None = None,
    headers: MutableMapping[str, str] | None = None,
    allow_redirects: bool = False,
    max_redirects: int = 3,
) -> requests.Response:
    next_url = url
    for _ in range(max_redirects + 1):
        _validate_url(next_url, allow_hosts, allowed_schemes)
        response = requests.request(
            method,
            next_url,
            params=params,
            json=json,
            headers=headers,
            timeout=timeout,
            allow_redirects=False,
        )
        if response.is_redirect:
            location = response.headers.get("location")
            if not location:
                raise RedirectNotAllowedError("Redirect without Location header.")
            candidate = urljoin(next_url, location)
            _validate_url(candidate, allow_hosts, allowed_schemes)
            if not allow_redirects:
                raise RedirectNotAllowedError(f"Redirect to '{candidate}' is not allowed.")
            next_url = candidate
            continue
        response.raise_for_status()
        return response
    raise RedirectNotAllowedError("Maximum redirect limit exceeded.")


class SafeHttpClient:
    """HTTP client that enforces host and scheme allow-lists."""

    def __init__(
        self,
        allow_hosts: Iterable[str],
        *,
        timeout: float = DEFAULT_TIMEOUT,
        allowed_schemes: Iterable[str] | None = None,
    ) -> None:
        hosts = {_normalize_host(host) for host in allow_hosts if host}
        if not hosts:
            raise ValueError("allow_hosts must contain at least one host.")
        self._allow_hosts = hosts
        self._allowed_schemes = (
            set(allowed_schemes) if allowed_schemes is not None else set(DEFAULT_SCHEMES)
        )
        if not self._allowed_schemes:
            raise ValueError("allowed_schemes must contain at least one scheme.")
        self._timeout = float(timeout)

    def request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
        headers: MutableMapping[str, str] | None = None,
        timeout: float | None = None,
        allow_redirects: bool = False,
        max_redirects: int = 3,
    ) -> requests.Response:
        return _request(
            method,
            url,
            allow_hosts=self._allow_hosts,
            allowed_schemes=self._allowed_schemes,
            timeout=timeout if timeout is not None else self._timeout,
            params=params,
            json=json,
            headers=headers,
            allow_redirects=allow_redirects,
            max_redirects=max_redirects,
        )

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: MutableMapping[str, str] | None = None,
        timeout: float | None = None,
        allow_redirects: bool = False,
        max_redirects: int = 3,
    ) -> requests.Response:
        return self.request(
            "GET",
            url,
            params=params,
            headers=headers,
            timeout=timeout,
            allow_redirects=allow_redirects,
            max_redirects=max_redirects,
        )

    def post(
        self,
        url: str,
        *,
        json: Mapping[str, Any] | None = None,
        headers: MutableMapping[str, str] | None = None,
        timeout: float | None = None,
        allow_redirects: bool = False,
        max_redirects: int = 3,
    ) -> requests.Response:
        return self.request(
            "POST",
            url,
            json=json,
            headers=headers,
            timeout=timeout,
            allow_redirects=allow_redirects,
            max_redirects=max_redirects,
        )

    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: MutableMapping[str, str] | None = None,
        timeout: float | None = None,
        allow_redirects: bool = False,
        max_redirects: int = 3,
    ) -> Any:
        response = self.get(
            url,
            params=params,
            headers=headers,
            timeout=timeout,
            allow_redirects=allow_redirects,
            max_redirects=max_redirects,
        )
        return response.json()

    def post_json(
        self,
        url: str,
        *,
        json: Mapping[str, Any] | None = None,
        headers: MutableMapping[str, str] | None = None,
        timeout: float | None = None,
        allow_redirects: bool = False,
        max_redirects: int = 3,
    ) -> Any:
        response = self.post(
            url,
            json=json,
            headers=headers,
            timeout=timeout,
            allow_redirects=allow_redirects,
            max_redirects=max_redirects,
        )
        return response.json()


def get_json(
    url: str,
    allow_hosts: Iterable[str],
    *,
    timeout: float = DEFAULT_TIMEOUT,
    params: Mapping[str, Any] | None = None,
    headers: MutableMapping[str, str] | None = None,
    allow_redirects: bool = False,
    max_redirects: int = 3,
) -> Any:
    client = SafeHttpClient(allow_hosts, timeout=timeout)
    return client.get_json(
        url,
        params=params,
        headers=headers,
        timeout=timeout,
        allow_redirects=allow_redirects,
        max_redirects=max_redirects,
    )
