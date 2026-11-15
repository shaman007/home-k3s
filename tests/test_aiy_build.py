"""Check the build request cannot silently widen approved publication scope."""
import base64
import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile
import unittest

SPEC = importlib.util.spec_from_file_location(
    "aiy_build", Path(__file__).resolve().parents[1] / "aiy-voice/prepare_build.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class BuildRequestTests(unittest.TestCase):
    def test_retry_retains_approved_destination_and_records_actual_source(self):
        request = builder.render("src-89e4e483f7496011")
        config, job = request["items"]
        source = base64.b64decode(config["binaryData"]["context.tgz"])
        self.assertEqual(job["metadata"]["annotations"]["aiy-source-sha256"],
                         hashlib.sha256(source).hexdigest())
        container = job["spec"]["template"]["spec"]["containers"][0]
        env = {entry["name"]: entry.get("value") for entry in container["env"]}
        self.assertEqual(env["AIY_IMAGE"],
                         "harbor.andreybondarenko.com/library/aiy-voice:src-89e4e483f7496011")
        self.assertEqual(request, builder.render("src-89e4e483f7496011"))
        with tarfile.open(fileobj=io.BytesIO(source), mode="r:gz") as archive:
            self.assertEqual(set(archive.getnames()), set(builder.FILES))
            self.assertNotIn("auth.json", archive.getnames())
        self.assertNotIn(":latest", container["args"][0])
        self.assertEqual(job["spec"]["backoffLimit"], 0)

    def test_invalid_destination_tag_is_rejected(self):
        for tag in ("../other", "bad tag", "tag;command", ""):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                builder.render(tag)


if __name__ == "__main__":
    unittest.main()
