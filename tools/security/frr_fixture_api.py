"""Loopback-only mock Kubernetes API for disposable FRR exporter probes."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import json
import ssl
import time

GROUP = "frrk8s.metallb.io"
VERSION = GROUP + "/v1beta1"
KINDS = {
    "bgpsessionstates": "BGPSessionState",
    "frrnodestates": "FRRNodeState",
    "frrconfigurations": "FRRConfiguration",
    "frrk8sconfigurations": "FRRK8sConfiguration",
}
STATE = {}
POD = {
    "apiVersion": "v1",
    "kind": "Pod",
    "metadata": {
        "name": "guard-pod",
        "namespace": "fixture",
        "uid": "00000000-0000-0000-0000-000000000001",
        "resourceVersion": "1",
    },
    "spec": {"nodeName": "guard-node", "containers": [{"name": "frr-status", "image": "fixture"}]},
    "status": {"phase": "Running"},
}


class Handler(BaseHTTPRequestHandler):
    def respond(self, data, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_GET(self):
        path = urlparse(self.path).path
        query = parse_qs(urlparse(self.path).query)
        if path == "/version":
            return self.respond({"major": "1", "minor": "37", "gitVersion": "v1.37.1"})
        if path == "/api":
            return self.respond(
                {
                    "apiVersion": "v1",
                    "kind": "APIVersions",
                    "versions": ["v1"],
                    "serverAddressByClientCIDRs": [],
                }
            )
        if path == "/apis":
            return self.respond(
                {
                    "apiVersion": "v1",
                    "kind": "APIGroupList",
                    "groups": [
                        {
                            "name": GROUP,
                            "versions": [{"groupVersion": VERSION, "version": "v1beta1"}],
                            "preferredVersion": {"groupVersion": VERSION, "version": "v1beta1"},
                        }
                    ],
                }
            )
        if path == "/api/v1":
            return self.respond(
                {
                    "apiVersion": "v1",
                    "kind": "APIResourceList",
                    "groupVersion": "v1",
                    "resources": [
                        {
                            "name": "pods",
                            "kind": "Pod",
                            "namespaced": True,
                            "verbs": ["get", "list", "watch"],
                        }
                    ],
                }
            )
        if path == "/apis/" + VERSION:
            resources = []
            for resource, kind in KINDS.items():
                resources.append(
                    {
                        "name": resource,
                        "kind": kind,
                        "namespaced": resource != "frrnodestates",
                        "verbs": ["get", "list", "watch", "create", "update", "patch"],
                    }
                )
                resources.append(
                    {
                        "name": resource + "/status",
                        "kind": kind,
                        "namespaced": resource != "frrnodestates",
                        "verbs": ["get", "update", "patch"],
                    }
                )
            return self.respond(
                {
                    "apiVersion": "v1",
                    "kind": "APIResourceList",
                    "groupVersion": VERSION,
                    "resources": resources,
                }
            )
        if path.endswith("/pods/guard-pod"):
            print("pod-read", flush=True)
            return self.respond(POD)
        parts = path.split("/")
        resource = next((r for r in KINDS if r in parts), None)
        if resource:
            print("resource-read", resource, flush=True)
            kind = KINDS[resource]
            index = parts.index(resource)
            if query.get("watch") == ["true"]:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                bookmark = {
                    "type": "BOOKMARK",
                    "object": {
                        "apiVersion": VERSION,
                        "kind": kind,
                        "metadata": {
                            "resourceVersion": "1",
                            "annotations": {"k8s.io/initial-events-end": "true"},
                        },
                    },
                }
                try:
                    self.wfile.write((json.dumps(bookmark) + chr(10)).encode())
                    self.wfile.flush()
                    time.sleep(5)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return
            if len(parts) == index + 1:
                return self.respond(
                    {
                        "apiVersion": VERSION,
                        "kind": kind + "List",
                        "metadata": {"resourceVersion": "1"},
                        "items": [v for (r, n), v in STATE.items() if r == resource],
                    }
                )
            name = parts[index + 1]
            if (resource, name) in STATE:
                return self.respond(STATE[(resource, name)])
        return self.respond(
            {
                "apiVersion": "v1",
                "kind": "Status",
                "status": "Failure",
                "reason": "NotFound",
                "code": 404,
            },
            404,
        )

    def do_POST(self):
        self.write_request()

    def do_PUT(self):
        self.write_request()

    def do_PATCH(self):
        self.write_request()

    def write_request(self):
        path = urlparse(self.path).path
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or "{}")
        if path.endswith("/tokenreviews"):
            print("token-review", flush=True)
            return self.respond(
                {
                    "apiVersion": "authentication.k8s.io/v1",
                    "kind": "TokenReview",
                    "status": {
                        "authenticated": True,
                        "audiences": data.get("spec", {}).get("audiences", []),
                        "user": {
                            "username": "fixture",
                            "uid": "fixture",
                            "groups": ["system:authenticated"],
                        },
                    },
                }
            )
        if path.endswith("/subjectaccessreviews"):
            print("access-review", flush=True)
            return self.respond(
                {
                    "apiVersion": "authorization.k8s.io/v1",
                    "kind": "SubjectAccessReview",
                    "status": {"allowed": True},
                }
            )
        resource = next((r for r in KINDS if r in path.split("/")), None)
        if resource and data.get("metadata", {}).get("name"):
            data["metadata"]["resourceVersion"] = "1"
            STATE[(resource, data["metadata"]["name"])] = data
            print("resource-write", resource, flush=True)
        return self.respond(data, 201 if self.command == "POST" else 200)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 6443), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain("/fixture/server.crt", "/fixture/server.key")
    server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()
