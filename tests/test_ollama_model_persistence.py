from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


class OllamaModelPersistenceTest(unittest.TestCase):
    def test_both_deployments_use_the_discovered_nvidia_gpu(self):
        for path in (
            "ollama/deployment-ollama.yaml",
            "ollama-small/deployment-ollama-small.yaml",
        ):
            deployment = load_yaml(path)
            pod_spec = deployment["spec"]["template"]["spec"]
            ollama = next(
                container
                for container in pod_spec["containers"]
                if container["name"] == "ollama"
            )

            self.assertEqual("nvidia", pod_spec["runtimeClassName"], path)
            self.assertEqual(
                {"nvidia.com/gpu.present": "true"}, pod_spec["nodeSelector"], path
            )
            self.assertEqual(1, ollama["resources"]["limits"]["nvidia.com/gpu"], path)

    def test_model_pullers_reuse_models_from_persistent_storage(self):
        deployments = (
            ("ollama/deployment-ollama.yaml", "ollama-data-lh", "gpt-oss:20b"),
            (
                "ollama-small/deployment-ollama-small.yaml",
                "ollama-small-data",
                "qwen2.5:1.5b",
            ),
        )

        for path, claim_name, model in deployments:
            deployment = load_yaml(path)
            pod_spec = deployment["spec"]["template"]["spec"]
            containers = {
                container["name"]: container for container in pod_spec["containers"]
            }
            puller = containers["model-puller"]
            command = puller["command"][2]

            self.assertIn(f"ollama show {model}", command, path)
            self.assertIn(f"ollama pull {model}", command, path)
            self.assertLess(command.index("ollama show"), command.index("ollama pull"))
            self.assertIn(
                {"name": puller["volumeMounts"][0]["name"], "persistentVolumeClaim": {"claimName": claim_name}},
                pod_spec["volumes"],
            )
            self.assertEqual("/root/.ollama", puller["volumeMounts"][0]["mountPath"])
            self.assertEqual(
                "/root/.ollama",
                containers["ollama"]["volumeMounts"][0]["mountPath"],
            )


if __name__ == "__main__":
    unittest.main()
