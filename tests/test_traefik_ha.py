from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]

class TraefikHATest(unittest.TestCase):
    def test_both_value_sources_preserve_storage_and_enforce_ha(self):
        app = yaml.safe_load((ROOT / "argocd/application-traefik.yaml").read_text())
        for values in [yaml.safe_load(app["spec"]["source"]["helm"]["values"]),
                       yaml.safe_load((ROOT / "traefik/values.yaml").read_text())]:
            self.assertEqual(2, values["deployment"]["replicas"])
            self.assertEqual("RollingUpdate", values["updateStrategy"]["type"])
            self.assertEqual(0, values["updateStrategy"]["rollingUpdate"]["maxUnavailable"])
            self.assertEqual(1, values["podDisruptionBudget"]["minAvailable"])
            anti = values["affinity"]["podAntiAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"][0]
            self.assertEqual("kubernetes.io/hostname", anti["topologyKey"])
            self.assertEqual("traefik-traefik", anti["labelSelector"]["matchLabels"]["app.kubernetes.io/instance"])
            claims = {o["metadata"]["name"]: o for o in values["extraObjects"] if o.get("kind") == "PersistentVolumeClaim"}
            self.assertEqual("traefik-geoip-rwx", values["persistence"]["existingClaim"])
            self.assertEqual(["ReadWriteMany"], claims["traefik-geoip-rwx"]["spec"]["accessModes"])
            self.assertEqual("Prune=false", claims["traefik"]["metadata"]["annotations"]["argocd.argoproj.io/sync-options"])
            self.assertEqual("pvc-0b8e1746-93a0-401c-a4ac-e2aac9c7ff2e", claims["traefik"]["spec"]["volumeName"])
            init = values["deployment"]["initContainers"]
            self.assertEqual(["download-geoip-country-db"], [c["name"] for c in init])
            script = init[0]["command"][-1]
            self.assertIn('gunzip -c "$db_archive" > "$db_staged"', script)
            self.assertIn('mv -f "$db_staged" "$db_file"', script)
            self.assertNotIn('gunzip -c "$db_archive" > "$db_file"', script)
