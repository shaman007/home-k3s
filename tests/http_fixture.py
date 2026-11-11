"""Simulate HTTP redirect dispatch without opening sockets or using credentials."""

from email.message import Message
import io
import urllib.request
import urllib.response


def fixture_opener(
    url, status, visits, buffers, target="https://elsewhere.invalid/collect"
):
    """Build a transport fixture whose redirect scenario is bound outside test loops."""
    original_build = urllib.request.build_opener

    class FixtureHttp(urllib.request.HTTPSHandler, urllib.request.HTTPHandler):
        """Return controlled HTTP responses without opening a socket."""

        def http_open(self, req):
            """Record the request and synthesize the redirect or destination response."""
            visits.append(req.full_url)
            response_headers = Message()
            code = status if req.full_url == url else 200
            if code != 200:
                response_headers["Location"] = target
            body = io.BytesIO(b"{}")
            buffers.append(body)
            response = urllib.response.addinfourl(
                body, response_headers, req.full_url, code
            )
            response.msg = "Fixture response"
            return response

        https_open = http_open

    def build(*handlers):
        return original_build(urllib.request.ProxyHandler({}), FixtureHttp(), *handlers)

    return build
