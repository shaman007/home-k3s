"""Download pinned chart inputs over HTTPS, including HTTPS-only redirects."""

import urllib.error
import urllib.parse
import urllib.request


def validate_https_url(url):
    """Reject insecure or ambiguous download targets without echoing signed URLs."""
    try:
        parsed = urllib.parse.urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.port not in (None, 443)
        ):
            raise ValueError
        if (
            parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or any(character.isspace() or ord(character) < 32 for character in url)
        ):
            raise ValueError
    except ValueError:
        raise ValueError("Chart downloads require unambiguous HTTPS endpoints") from None


class HTTPSOnly(urllib.request.HTTPErrorProcessor):
    """Check redirect destinations before normal urllib redirect dispatch."""

    def http_response(self, request, response):
        """Retain signed HTTPS release downloads while refusing insecure destinations."""
        if response.code in {301, 302, 303, 307, 308}:
            location = response.headers.get("Location") or response.headers.get("URI")
            if location:
                try:
                    validate_https_url(urllib.parse.urljoin(request.full_url, location))
                except ValueError:
                    response.close()
                    raise
        return super().http_response(request, response)

    https_response = http_response


def fetch(url, accept="application/json"):
    """Read a TLS-verified response and close failures without logging private URLs."""
    validate_https_url(url)
    request = urllib.request.Request(url, headers={"Accept": accept})
    try:
        with urllib.request.build_opener(HTTPSOnly()).open(request, timeout=60) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        error.close()
        raise RuntimeError(f"Chart download failed: HTTP {error.code}") from None
    except (urllib.error.URLError, OSError):
        raise RuntimeError("Chart download transport failed; private details suppressed") from None
