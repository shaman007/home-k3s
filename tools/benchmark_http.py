"""Keep benchmark credentials on the explicitly selected HTTP service."""

from contextlib import contextmanager
import urllib.error
import urllib.parse
import urllib.request


def validate_base_url(url):
    """Accept explicit HTTP services without ambiguous authority or URL suffixes."""
    try:
        parsed = urllib.parse.urlsplit(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.port == 0
        ):
            raise ValueError
        if (
            parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or any(character.isspace() or ord(character) < 32 for character in url)
        ):
            raise ValueError
    except ValueError:
        raise ValueError(
            "Use an HTTP or HTTPS service URL without credentials or suffixes"
        ) from None
    return url.rstrip("/")


class NoRedirects(urllib.request.HTTPErrorProcessor):
    """Stop redirect responses before the default redirect handler can replay a request."""

    def http_response(self, request, response):
        """Refuse every redirect status while retaining ordinary HTTP error handling."""
        if 300 <= response.code < 400:
            raise urllib.error.HTTPError(
                request.full_url, response.code, "Redirect refused", response.headers, response
            )
        return super().http_response(request, response)

    https_response = http_response


@contextmanager
def open_response(request, timeout):
    """Close responses and sanitize transport failures without swallowing caller deadlines."""
    try:
        validate_base_url(request.full_url)
        with urllib.request.build_opener(NoRedirects()).open(request, timeout=timeout) as response:
            yield response
    except urllib.error.HTTPError as error:
        error.close()
        raise RuntimeError(f"Inference HTTP request failed: HTTP {error.code}") from None
    except (urllib.error.URLError, OSError, ValueError):
        raise RuntimeError("Inference transport failed; private details suppressed") from None
