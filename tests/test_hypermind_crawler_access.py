from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


class HypermindCrawlerAccessTest(unittest.TestCase):
    def test_honeypot_records_forwarded_ips_on_pvc_and_keeps_sse_streaming(self):
        def load(name):
            return yaml.safe_load((ROOT / "hypermind" / name).read_text())

        pod = load("deployment-hypermind.yaml")["spec"]["template"]["spec"]
        proxy = next(c for c in pod["containers"] if c["name"] == "access-proxy")
        service = load("service-hypermind.yaml")
        self.assertEqual("proxy-http", service["spec"]["ports"][0]["targetPort"])
        self.assertEqual(8080, proxy["ports"][0]["containerPort"])
        self.assertIn(
            {"name": "storage", "mountPath": "/app/storage"}, proxy["volumeMounts"]
        )
        config = load("config-map-access-proxy.yaml")["data"]["nginx.conf"]
        self.assertIn("access_log /app/storage/http-logs/access.log honeypot_json;", config)
        for field in ("$http_x_forwarded_for", "$remote_addr", "$http_user_agent"):
            self.assertIn(field, config)
        self.assertIn("proxy_set_header X-Forwarded-For $http_x_forwarded_for;", config)
        self.assertIn("proxy_buffering off;", config)
        self.assertIn("proxy_read_timeout 1h;", config)
        # Record visits without retaining credentials, query strings or post bodies.
        for field in ("$request_body", "$http_authorization", "$http_cookie", "$request_uri"):
            self.assertNotIn(field, config)

    def test_public_honeypot_intentionally_allows_crawling(self):
        # Hypermind is intentionally discoverable to observe automated use.
        # Keep its existing ingress protections without the robots disallow rule.
        ingress = yaml.safe_load(
            (ROOT / "hypermind/ingress-hypermind.yaml").read_text(encoding="utf-8")
        )
        self.assertIn(
            "hypermind.andreybondarenko.com",
            [rule["host"] for rule in ingress["spec"]["rules"]],
        )
        middlewares = {
            ref.strip()
            for ref in ingress["metadata"]["annotations"][
                "traefik.ingress.kubernetes.io/router.middlewares"
            ].split(",")
        }
        self.assertNotIn("traefik-robots-disallow-all@kubernetescrd", middlewares)
        self.assertTrue(
            {
                "traefik-geoip-country@kubernetescrd",
                "hypermind-hsts@kubernetescrd",
            }.issubset(middlewares)
        )


if __name__ == "__main__":
    unittest.main()
