#!/usr/bin/env python3
"""Validate rendered and raw manifests; missing custom-resource schemas fail CI.

Custom schemas come from the rendered, version-pinned controller CRDs, plus
explicit upstream sources for controllers that install CRDs at runtime. This is
structural validation, not execution of admission webhooks or CEL expressions.
"""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile

import jsonschema
import regex
import yaml
from ci_yaml import load, load_all

ROOT = Path(__file__).resolve().parents[2]
BUILTIN_GROUPS = {"", "apps", "batch", "autoscaling", "policy", "networking.k8s.io",
                  "rbac.authorization.k8s.io", "apiextensions.k8s.io", "apiregistration.k8s.io",
                  "scheduling.k8s.io", "node.k8s.io", "discovery.k8s.io", "storage.k8s.io",
                  "coordination.k8s.io", "admissionregistration.k8s.io", "certificates.k8s.io",
                  "resource.k8s.io", "flowcontrol.apiserver.k8s.io"}


def unicode_pattern(validator, pattern, instance, schema):
    # Kubernetes CRDs use RE2 Unicode categories (e.g. Cilium's \PC).
    # Python's built-in re cannot evaluate those patterns.
    if isinstance(instance, str) and regex.search(pattern, instance) is None:
        yield jsonschema.ValidationError("pattern constraint")


CRDValidator = jsonschema.validators.extend(jsonschema.Draft7Validator, {"pattern": unicode_pattern})


def documents(text):
    for doc in load_all(text):
        if not doc:
            continue
        if doc.get("kind") == "List":
            yield from doc.get("items", [])
        else:
            yield doc


def convert_schema(schema):
    """Translate Kubernetes OpenAPI extensions into JSON Schema constraints."""
    schema = copy.deepcopy(schema)
    if not isinstance(schema, dict):
        return schema
    if isinstance(schema.get("pattern"), str):
        regex.compile(schema["pattern"])
    if schema.get("x-kubernetes-int-or-string"):
        schema.pop("type", None)
        schema["anyOf"] = [{"type": "integer"}, {"type": "string"}]
    for key in ("properties", "patternProperties", "definitions"):
        if key in schema:
            schema[key] = {k: convert_schema(v) for k, v in schema[key].items()}
    for key in ("items", "additionalProperties", "not"):
        if isinstance(schema.get(key), dict):
            schema[key] = convert_schema(schema[key])
    for key in ("allOf", "anyOf", "oneOf"):
        if key in schema:
            schema[key] = [convert_schema(s) for s in schema[key]]
    if schema.get("type") == "object" and "properties" in schema and not schema.get("x-kubernetes-preserve-unknown-fields"):
        schema.setdefault("additionalProperties", False)
    if schema.pop("nullable", False):
        return {"anyOf": [schema, {"type": "null"}]}
    return schema


def collect_schemas(docs):
    schemas = {}
    for doc in docs:
        if doc.get("kind") != "CustomResourceDefinition":
            continue
        spec = doc["spec"]
        for version in spec["versions"]:
            if not version.get("served", False):
                continue
            schema = convert_schema(version["schema"]["openAPIV3Schema"])
            # Kubernetes supplies these implicit top-level fields to all CRs.
            props = schema.setdefault("properties", {})
            props.setdefault("apiVersion", {"type": "string"})
            props.setdefault("kind", {"type": "string"})
            props.setdefault("metadata", {"type": "object"})
            schemas[(spec["group"] + "/" + version["name"], spec["names"]["kind"])] = schema
    return schemas


def crd_errors(doc):
    """Focused CRD checks: kubeconform's registry does not ship a CRD schema."""
    errors = []
    spec = doc.get("spec", {})
    names = spec.get("names", {})
    versions = spec.get("versions", [])
    if doc.get("apiVersion") != "apiextensions.k8s.io/v1":
        errors.append("unsupported CRD apiVersion")
    if not spec.get("group") or not names.get("kind") or not names.get("plural"):
        errors.append("group, names.kind and names.plural are required")
    if doc.get("metadata", {}).get("name") != names.get("plural", "") + "." + spec.get("group", ""):
        errors.append("metadata.name must match plural.group")
    if spec.get("scope") not in {"Namespaced", "Cluster"}:
        errors.append("invalid scope")
    if not versions or sum(v.get("storage") is True for v in versions) != 1:
        errors.append("exactly one storage version is required")
    version_names = [v.get("name") for v in versions]
    if not all(version_names) or len(set(version_names)) != len(version_names):
        errors.append("version names must be present and unique")
    for version in versions:
        if not isinstance(version.get("served"), bool) or not isinstance(version.get("storage"), bool):
            errors.append("served/storage must be booleans")
        schema = version.get("schema", {}).get("openAPIV3Schema", {})
        if schema.get("type") != "object":
            errors.append("version schema must have an object root")
        try:
            jsonschema.Draft7Validator.check_schema(convert_schema(schema), format_checker=None)
        except (jsonschema.SchemaError, regex.error):
            errors.append("invalid version schema")
    return errors


def custom_errors(doc, schemas):
    key = (doc["apiVersion"], doc["kind"])
    if key not in schemas:
        return ["missing schema"]
    # Do not print values: rendered manifests may contain generated credentials.
    return [f"{'.'.join(map(str, e.absolute_path)) or '<root>'}: {e.validator} constraint"
            for e in CRDValidator(schemas[key]).iter_errors(doc)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rendered", type=Path, required=True)
    args = parser.parse_args()
    config = load((ROOT / "tools/ci/validation-config.yaml").read_text())
    inputs = []
    inventory = json.loads((args.rendered / "inventory.json").read_text())
    expected = []
    for file in (ROOT / "argocd").glob("*.yaml"):
        app = load(file.read_text())
        if isinstance(app, dict) and app.get("kind") == "Application":
            expected.append(app["metadata"]["name"])
    if set(inventory) != set(expected):
        raise ValueError("Full application render required for validation")
    for name in inventory:
        inputs.extend((f"rendered/{name}", doc) for doc in documents((args.rendered / (name + ".yaml")).read_text()))
    spec = importlib.util.spec_from_file_location("discovery", ROOT / "tools/ci/list-k8s-manifest-files.py")
    discovery = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(discovery)
    for path in discovery.tracked_yaml_files(ROOT):
        if discovery.looks_like_k8s_manifest(path):
            for doc in documents(path.read_text()):
                # Kustomize configuration is consumed by the render step, not Kubernetes.
                if doc.get("apiVersion") == "kustomize.config.k8s.io/v1beta1" and doc.get("kind") == "Kustomization":
                    continue
                inputs.append((str(path.relative_to(ROOT)), doc))
    crds = [doc for _, doc in inputs if doc.get("kind") == "CustomResourceDefinition"]
    for source in config.get("additionalCRDs", []):
        app = load((ROOT / "argocd" / ("application-" + source["application"] + ".yaml")).read_text())
        sources = app["spec"].get("sources", [app["spec"].get("source", {})])
        version = next(s["targetRevision"] for s in sources if "chart" in s).removeprefix("v")
        url = source["url"].format(version=version)
        result = subprocess.run(["curl", "-fsSL", "--connect-timeout", "15", "--max-time", "120", url], capture_output=True, text=True, timeout=130, check=True)
        crds.extend(documents(result.stdout))
    errors = []
    for crd in crds:
        errors.extend(f"CRD/{crd.get('metadata', {}).get('name', '<unnamed>')}: {error}" for error in crd_errors(crd))
    if errors:
        for error in errors:
            print(error)
        return 1
    schemas = collect_schemas(crds)
    standard, custom_count = [], 0
    for origin, doc in inputs:
        api_version = doc.get("apiVersion", "")
        group = api_version.split("/")[0] if "/" in api_version else ""
        if doc.get("kind") == "CustomResourceDefinition":
            continue  # Explicitly validated above, never silently skipped.
        if group in BUILTIN_GROUPS:
            standard.append(doc)
        else:
            custom_count += 1
            for error in custom_errors(doc, schemas):
                errors.append(f"{origin}: {doc['kind']}/{doc.get('metadata', {}).get('name', '<unnamed>')}: {error}")
    for error in errors:
        print(error)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "standard.yaml"
        path.write_text(yaml.safe_dump_all(standard, sort_keys=False))
        os.chmod(path, 0o600)
        result = subprocess.run(["kubeconform", "-strict", "-summary", "-output", "json", "-kubernetes-version", config["kubernetesVersion"], str(path)], capture_output=True, text=True, timeout=300)
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError:
            raise RuntimeError("kubeconform failed without a JSON report") from None
        print("Built-in resource validation:", report.get("summary", {}))
        for resource in report.get("resources", []):
            if resource.get("status") not in {"statusValid", "statusSkipped"}:
                print("Invalid built-in resource:", resource.get("kind"), resource.get("name"), resource.get("status"))
    print(f"Custom resources: {custom_count} checked against {len(schemas)} served CRD schemas; {len(errors)} errors")
    return int(bool(errors) or result.returncode != 0)


if __name__ == "__main__":
    raise SystemExit(main())
