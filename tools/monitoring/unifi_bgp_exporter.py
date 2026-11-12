#!/usr/bin/env python3
"""Read-only UniFi BGP telemetry. Credentials/cookies stay in process memory."""

import http.cookiejar
import http.server
import ipaddress
import json
import logging
import os
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager

PEERS = ("192.168.30.100", "192.168.30.209", "192.168.30.242")
PREFIXES = ("192.168.30.210/32", "192.168.30.211/32", "192.168.30.213/32", "192.168.30.212/32")
LOGGER = logging.getLogger("unifi_bgp")
READ_STAGES = {
    "/proxy/network/v2/api/site/default/bgp/neighbors": "neighbors",
    "/proxy/network/v2/api/site/default/routes": "routes",
}


def error_kind(error):
    """Classify failures without serializing exception text or transport details."""
    if isinstance(error, urllib.error.URLError) and not isinstance(
        error, urllib.error.HTTPError
    ):
        error = error.reason
    if isinstance(error, TimeoutError):
        return "timeout"
    if isinstance(error, ssl.SSLError):
        return "tls"
    if isinstance(error, urllib.error.HTTPError):
        return "http"
    if isinstance(error, OSError):
        return "network"
    if isinstance(error, (ValueError, KeyError, TypeError)):
        return "invalid_data"
    return "internal"


@contextmanager
def stage_event(stage, attempt=1):
    """Log only fixed stage names, numeric timings/status and bounded error categories."""
    event = {
        "event": "unifi_bgp_stage",
        "stage": stage,
        "attempt": attempt,
        "phase": "operation",
        "outcome": "success",
    }
    started = time.monotonic()
    try:
        yield event
    except Exception as error:
        event.update(outcome="failure", error_kind=error_kind(error))
        raise
    finally:
        event["duration_seconds"] = round(time.monotonic() - started, 6)
        LOGGER.info("%s", json.dumps(event, sort_keys=True))


def decode(neighbors, routes):
    """Produce explicit zeroes for missing expected peers/routes, not stale data."""
    if (
        not isinstance(neighbors, list)
        or not isinstance(routes, dict)
        or not isinstance(routes.get("items"), list)
    ):
        raise ValueError("Invalid controller response")
    peers = {}
    for router in neighbors:
        if router.get("vrf") == "default":
            for peer in router["neighbors"]:
                if peer["peer"] in peers:
                    raise ValueError("Duplicate neighbor")
                peers[peer["peer"]] = peer
    bgp = [r for r in routes["items"] if r.get("origin") == "BGP"]
    violations = {
        "unexpected_peer": len(set(peers) - set(PEERS)),
        "unexpected_prefix": sum(r["destination"] not in PREFIXES for r in bgp),
        "unexpected_next_hop": sum(
            n.get("gateway") not in PEERS
            for r in bgp
            if r["destination"] in PREFIXES
            for n in r["nexthops"]
            if n.get("in_use")
        ),
        "unexpected_remote_as": sum(p["remote_as"] != 65040 for p in peers.values()),
    }
    metrics = []
    for ip in PEERS:
        peer = peers.get(ip)
        metrics.append(
            (
                "unifi_bgp_peer_established",
                {"peer": ip},
                int(bool(peer and peer["state"] == "Established" and peer["remote_as"] == 65040)),
            )
        )
        if peer:
            metrics.append(
                ("unifi_bgp_exported_routes", {"peer": ip}, int(peer["advertised_routes_count"]))
            )
    for prefix in PREFIXES:
        active = {
            n["gateway"]
            for r in bgp
            if r["destination"] == prefix
            for n in r["nexthops"]
            if n.get("in_use") and n.get("gateway") in PEERS
        }
        metrics.append(("unifi_bgp_route_active_next_hops", {"prefix": prefix}, len(active)))
    metrics.extend(
        ("unifi_bgp_policy_violations", {"reason": reason}, value)
        for reason, value in violations.items()
    )
    return metrics


def render(metrics, success, last_success):
    """Format collection status and supplied BGP measurements as Prometheus text."""
    help_text = {
        "unifi_bgp_scrape_success": "Whether both authenticated router API reads succeeded.",
        "unifi_bgp_last_success_timestamp_seconds": (
            "Unix timestamp of the last complete successful collection."
        ),
        "unifi_bgp_peer_established": (
            "Whether the expected router neighbor is established with the reviewed ASN."
        ),
        "unifi_bgp_exported_routes": "Routes advertised by the UDM to this Kubernetes neighbor.",
        "unifi_bgp_route_active_next_hops": (
            "Active reviewed Kubernetes next hops installed for the expected prefix."
        ),
        "unifi_bgp_policy_violations": (
            "Current deviations from the reviewed BGP peers and forwarding policy."
        ),
    }
    lines = []
    for name, text in help_text.items():
        lines.extend([f"# HELP {name} {text}", f"# TYPE {name} gauge"])
    lines += [
        f"unifi_bgp_scrape_success {int(success)}",
        f"unifi_bgp_last_success_timestamp_seconds {last_success}",
    ]
    for name, labels, value in metrics:
        tags = ",".join(k + "=" + json.dumps(v) for k, v in sorted(labels.items()))
        lines.append(f"{name}{{{tags}}} {value}")
    return "\n".join(lines) + "\n"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Reject HTTP redirects when making authenticated router API requests."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def controller_url(url):
    """Require an unambiguous HTTPS origin before any credential-bearing request."""
    try:
        origin = urllib.parse.urlsplit(url)
        if origin.scheme != "https" or not origin.hostname or origin.port == 0:
            raise ValueError
        if origin.username is not None or origin.password is not None:
            raise ValueError
        if (
            origin.path not in ("", "/")
            or origin.query
            or origin.fragment
            or any(character.isspace() or ord(character) < 32 for character in url)
        ):
            raise ValueError
    except ValueError:
        raise ValueError(
            "UNIFI_URL must be an HTTPS origin without credentials or suffixes"
        ) from None
    return url.rstrip("/")


class Controller:
    """Collect router BGP neighbors and routes with explicit collection-success state."""

    def __init__(self):
        self.base = controller_url(os.environ["UNIFI_URL"])
        context = ssl.create_default_context()
        self.context = context
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            NoRedirect(),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
            urllib.request.HTTPSHandler(context=context),
        )
        self.logged_in = False
        self.csrf = ""

    def request(self, path, data=None, attempt=1):
        """Send a JSON router request and retain an updated CSRF token in memory."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "home-k3s-unifi-bgp-exporter/1.0",
        }
        if self.csrf:
            headers["X-CSRF-Token"] = self.csrf
        req = urllib.request.Request(
            self.base + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers=headers,
        )
        stage = "login" if path == "/api/auth/login" else READ_STAGES.get(path, "other")
        with stage_event(stage, attempt) as event:
            event["phase"] = "response"
            try:
                with self.opener.open(req, timeout=15) as response:
                    event["http_status"] = response.status
                    event["phase"] = "body_json"
                    self.csrf = response.headers.get("X-CSRF-Token", self.csrf)
                    return json.load(response)
            except urllib.error.HTTPError as error:
                event["http_status"] = error.code
                error.close()
                raise

    def login(self):
        """Authenticate using environment-provided credentials and the in-memory cookie jar."""
        self.request(
            "/api/auth/login",
            {"username": os.environ["UNIFI_USERNAME"], "password": os.environ["UNIFI_PASSWORD"]},
        )
        self.logged_in = True

    def get(self, path):
        """Renew auth once; retry only reviewed GETs once after a timeout, never login."""
        if not self.logged_in:
            self.login()
        renewed = retried = False
        for attempt in range(1, 4):
            try:
                return self.request(path, attempt=attempt)
            except urllib.error.HTTPError as error:
                if error.code not in (401, 403) or renewed:
                    raise
                self.logged_in = False
                self.login()
                renewed = True
            except (TimeoutError, urllib.error.URLError) as error:
                if error_kind(error) != "timeout" or retried or path not in READ_STAGES:
                    raise
                retried = True
                time.sleep(1)
        raise RuntimeError("Read attempt budget exhausted")

    def certificate_expiry(self):
        """Inspect the certificate actually served by the verified controller endpoint."""
        origin = urllib.parse.urlsplit(self.base)
        with socket.create_connection((origin.hostname, origin.port or 443), timeout=15) as raw:
            with self.context.wrap_socket(raw, server_hostname=origin.hostname) as connection:
                return ssl.cert_time_to_seconds(connection.getpeercert()["notAfter"])

    def collect(self):
        """Read neighbor and route endpoints and decode their current BGP measurements."""
        base = "/proxy/network/v2/api/site/default/"
        neighbors = self.get(base + "bgp/neighbors")
        routes = self.get(base + "routes")
        with stage_event("decode"):
            metrics = decode(neighbors, routes)
        with stage_event("certificate"):
            expiry = self.certificate_expiry()
        metrics.append(
            ("unifi_bgp_tls_certificate_expiry_timestamp_seconds", {}, expiry)
        )
        return metrics


def metrics_address():
    """Bind the IPv4 metrics server to loopback or an explicitly selected interface."""
    try:
        address = ipaddress.ip_address(os.environ.get("UNIFI_METRICS_ADDRESS", "127.0.0.1"))
    except ValueError:
        raise ValueError("UNIFI_METRICS_ADDRESS must be a specific IPv4 address") from None
    if address.version != 4 or address.is_unspecified:
        raise ValueError("UNIFI_METRICS_ADDRESS must be a specific IPv4 address")
    return str(address)


def main():
    """Poll the router in a background thread and serve metrics and liveness responses."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    listen_address = metrics_address()
    controller = Controller()
    lock = threading.Lock()
    state = {"body": render([], False, 0)}

    def poll():
        last_success = 0
        while True:
            try:
                with stage_event("collection"):
                    metrics = controller.collect()
                    collected_at = time.time()
                    body = render(metrics, True, collected_at)
                    last_success = collected_at
            except Exception:
                # Never log requests, response bodies, passwords or session cookies.
                body = render([], False, last_success)
            with lock:
                state["body"] = body
            time.sleep(45)

    class Handler(http.server.BaseHTTPRequestHandler):
        """Expose current BGP collection metrics over HTTP."""

        def do_get(self):
            """Serve the current metrics snapshot or liveness response, rejecting other paths."""
            if self.path not in ("/metrics", "/healthz"):
                self.send_error(404)
                return
            with lock:
                body = (state["body"] if self.path == "/metrics" else "ok\n").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = do_get

        def log_message(self, *_):
            pass

    threading.Thread(target=poll, daemon=True).start()
    http.server.ThreadingHTTPServer((listen_address, 9131), Handler).serve_forever()


if __name__ == "__main__":
    main()
