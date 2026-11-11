"""Keep Sync and bootstrap credentials on one explicitly reviewed origin."""

import urllib.error
import urllib.parse
import urllib.request


def endpoint(url):
    """Parse an unambiguous URL without exposing its contents in validation errors."""
    try:
        if any(character.isspace() or ord(character) < 32 for character in url):
            raise ValueError
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
        if (
            parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or not parsed.hostname
            or port == 0
        ):
            raise ValueError
    except ValueError:
        raise ValueError("Invalid HTTP endpoint") from None
    return parsed, (
        parsed.scheme,
        parsed.hostname,
        port or (443 if parsed.scheme == "https" else 80),
    )


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Reject redirects before credentials or writes can reach another request."""

    def http_error_302(self, req, fp, code, msg, headers):
        """Preserve the original status and response for sanitized caller handling."""
        raise urllib.error.HTTPError(
            req.full_url, code, "Redirect refused", headers, fp
        )

    http_error_301 = http_error_302
    http_error_303 = http_error_302
    http_error_307 = http_error_302
    http_error_308 = http_error_302


class Transport:
    """Validate an origin once and enforce it on every authenticated request."""

    def __init__(self, url, https_hosts, allow_loopback=False):
        self._origin, self._endpoint = endpoint(url)
        public = self._origin.scheme == "https" and self._origin.hostname in https_hosts
        local = (
            allow_loopback
            and self._origin.scheme == "http"
            and self._origin.hostname in {"127.0.0.1", "localhost"}
        )
        if (
            not (local or (public and self._endpoint[2] == 443))
            or self._origin.path
            or self._origin.query
        ):
            raise ValueError("Use a reviewed HTTPS origin or an approved local tunnel")
        self._opener = urllib.request.build_opener(NoRedirect())

    @property
    def origin(self):
        """Expose the validated origin without allowing replacement after configuration."""
        return self._origin

    def open(self, request):
        """Open only the configured origin without following any redirect."""
        _, target = endpoint(request.full_url)
        if target != self._endpoint:
            raise ValueError("Request origin does not match the configured endpoint")
        return self._opener.open(request, timeout=15)
