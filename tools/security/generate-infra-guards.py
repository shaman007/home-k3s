#!/usr/bin/env python3
"""Generate narrowly reviewed native mutations and their guarded GitOps hook."""

import argparse
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
J = json.dumps


def C(value):
    # CEL map literals otherwise infer a single value type and reject mixed
    # Kubernetes fields such as a volume's name plus configMap object.
    """Render catalog values as CEL literals with explicit dynamic map values."""
    if isinstance(value, dict):
        return "{" + ", ".join(J(k) + ": dyn(" + C(v) + ")" for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(C(v) for v in value) + "]"
    return J(value)


def generate(catalog):
    """Generate reviewed admission guards and the matching scoped backfill manifests."""
    entries = catalog["entries"]
    branches = []
    patches = []
    for e in entries:
        pod = e["fixture"]["spec"]["template"]["spec"]
        identity = (
            f"object.metadata.namespace == "
            f"{J(e['namespace'])}"
            f" && object.kind == "
            f"{J(e['kind'])}"
            f" && object.metadata.name == "
            f"{J(e['name'])}"
        )
        terms = [identity, f'p.?serviceAccountName.orValue("default") == {J(e["serviceAccount"])}']
        for label, value in e["labels"].items():
            terms.append(
                f"object.spec.template.metadata.?labels.orValue({{}})[{J(label)}] == {J(value)}"
            )
        for section in ["containers", "initContainers"]:
            terms.append(f"p.?{section}.orValue([]).size() == {len(pod[section])}")
            for i, c in enumerate(pod[section]):
                ref = f"p.{section}[{i}]"
                terms.extend([f"{ref}.{k} == {J(c[k])}" for k in ["name", "image"]])
                terms.extend(
                    f"{ref}.?{k}.orValue([]) == {C(c.get(k, []))}"
                    for k in ["command", "args", "volumeMounts"]
                )
        terms.append(f"p.?volumes.orValue([]) == {C(pod.get('volumes', []))}")
        if e["kind"] == "DaemonSet":
            terms.append(
                f"object.spec.updateStrategy == {C(e['fixture']['spec']['updateStrategy'])}"
            )
        mutation_parts = []
        for target in e["targets"]:
            section, index = target["section"], target["index"]
            if not pod[section][index]["name"] == target["name"]:
                raise AssertionError
            ref = f"object.spec.template.spec.{section}[{index}]"
            terms.append(
                f"p.{section}[{index}].?securityContext.?privileged.orValue(false) == false"
            )
            for key, value in target.get("requiredEnv", {}).items():
                terms.append(
                    (
                        f"p."
                        f"{section}"
                        f"["
                        f"{index}"
                        f"].?env.orValue([]).exists(v, v.name == "
                        f"{J(key)}"
                        f' && v.?value.orValue("") == '
                        f"{J(value)}"
                        f")"
                    )
                )
            for key, path_value in target.get("requiredFieldRefs", {}).items():
                terms.append(
                    (
                        f"p."
                        f"{section}"
                        f"["
                        f"{index}"
                        f"].?env.orValue([]).exists(v, v.name == "
                        f"{J(key)}"
                        f" && v.?valueFrom.?fieldRef.?fieldPath.or"
                        f'Value("") == '
                        f"{J(path_value)}"
                        f")"
                    )
                )

            path = f"/spec/template/spec/{section}/{index}/securityContext"
            mutation_parts.append(
                (
                    f"(!has("
                    f"{ref}"
                    f".securityContext) ? "
                    f'[JSONPatch{{op:"add",path:'
                    f"{J(path)}"
                    f",value:{{}}}}] : [])"
                )
            )
            mutation_parts.append(
                "["
                + ", ".join(
                    'JSONPatch{op:"add",path:' + J(path + "/" + key) + ",value:" + J(value) + "}"
                    for key, value in target["guards"].items()
                )
                + "]"
            )
        if e.get("podGuards"):
            path = "/spec/template/spec/securityContext"
            mutation_parts.append(
                '(!has(object.spec.template.spec.securityContext) ? [JSONPatch{op:"add",path:'
                + J(path)
                + ",value:{}}] : [])"
            )
            mutation_parts.append(
                "["
                + ", ".join(
                    'JSONPatch{op:"add",path:' + J(path + "/" + key) + ",value:" + J(value) + "}"
                    for key, value in e["podGuards"].items()
                )
                + "]"
            )
        branches.append("(" + " &&\n".join(terms) + ")")
        patches.append((identity, " + ".join(mutation_parts)))
    expression = "[]"
    for identity, patch in reversed(patches):
        expression = "(" + identity + ") ? (" + patch + ") : (" + expression + ")"
    name = "reviewed-infrastructure-guards"
    policy = {
        "apiVersion": "admissionregistration.k8s.io/v1",
        "kind": "MutatingAdmissionPolicy",
        "metadata": {"name": name, "annotations": {"argocd.argoproj.io/sync-wave": "-2"}},
        "spec": {
            "failurePolicy": "Ignore",
            "reinvocationPolicy": "IfNeeded",
            "matchConstraints": {
                "resourceRules": [
                    {
                        "apiGroups": ["apps"],
                        "apiVersions": ["v1"],
                        "operations": ["CREATE", "UPDATE"],
                        "resources": ["deployments", "daemonsets"],
                    }
                ]
            },
            "matchConditions": [
                {
                    "name": "reviewed-exact-contract",
                    "expression": "[object.spec.template.spec].exists(p,\n"
                    + " ||\n".join(branches)
                    + ")",
                }
            ],
            "mutations": [{"patchType": "JSONPatch", "jsonPatch": {"expression": expression}}],
        },
    }
    namespaces = sorted({e["namespace"] for e in entries})
    binding = {
        "apiVersion": "admissionregistration.k8s.io/v1",
        "kind": "MutatingAdmissionPolicyBinding",
        "metadata": {"name": name, "annotations": {"argocd.argoproj.io/sync-wave": "-1"}},
        "spec": {
            "policyName": name,
            "matchResources": {
                "namespaceSelector": {
                    "matchExpressions": [
                        {
                            "key": "kubernetes.io/metadata.name",
                            "operator": "In",
                            "values": namespaces,
                        }
                    ]
                }
            },
        },
    }
    def meta(namespace):
        """Build metadata for a named guard resource in the supplied namespace."""
        return {"name": name, "namespace": namespace}

    docs = [
        policy,
        binding,
        {"apiVersion": "v1", "kind": "ServiceAccount", "metadata": meta("kyverno")},
    ]
    if catalog.get("gpuResourceReview"):
        docs += [
            {
                "apiVersion": "rbac.authorization.k8s.io/v1",
                "kind": "ClusterRole",
                "metadata": {"name": name + "-gpu-health"},
                "rules": [
                    {
                        "apiGroups": [""],
                        "resources": ["nodes"],
                        "resourceNames": [catalog["gpuResourceReview"]["node"]],
                        "verbs": ["get"],
                    }
                ],
            },
            {
                "apiVersion": "rbac.authorization.k8s.io/v1",
                "kind": "ClusterRoleBinding",
                "metadata": {"name": name + "-gpu-health"},
                "roleRef": {
                    "apiGroup": "rbac.authorization.k8s.io",
                    "kind": "ClusterRole",
                    "name": name + "-gpu-health",
                },
                "subjects": [{"kind": "ServiceAccount", "name": name, "namespace": "kyverno"}],
            },
        ]

    for ns in namespaces:
        rules = []
        for kind, resource in [("Deployment", "deployments"), ("DaemonSet", "daemonsets")]:
            names = [e["name"] for e in entries if e["namespace"] == ns and e["kind"] == kind]
            if names:
                rules.append(
                    {
                        "apiGroups": ["apps"],
                        "resources": [resource],
                        "resourceNames": names,
                        "verbs": ["get", "patch"],
                    }
                )
        if ns == "longhorn-system":
            rules.append(
                {"apiGroups": ["longhorn.io"], "resources": ["volumes", "nodes"], "verbs": ["list"]}
            )
        docs += [
            {
                "apiVersion": "rbac.authorization.k8s.io/v1",
                "kind": "Role",
                "metadata": meta(ns),
                "rules": rules,
            },
            {
                "apiVersion": "rbac.authorization.k8s.io/v1",
                "kind": "RoleBinding",
                "metadata": meta(ns),
                "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "Role", "name": name},
                "subjects": [{"kind": "ServiceAccount", "name": name, "namespace": "kyverno"}],
            },
        ]
    docs.append(
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": meta("kyverno"),
            "data": {
                "catalog.json": J(catalog),
                "backfill.py": (ROOT / "tools/security/infra_guard_backfill.py").read_text(),
                "storage_guard.py": (
                    ROOT / "tools/longhorn/backfill-component-security.py"
                ).read_text(),
            },
        }
    )
    docs.append(
        {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "generateName": name + "-",
                "namespace": "kyverno",
                "annotations": {
                    "argocd.argoproj.io/hook": "PostSync",
                    "argocd.argoproj.io/hook-delete-policy": "HookSucceeded",
                },
            },
            "spec": {
                "backoffLimit": 0,
                "activeDeadlineSeconds": len(entries) * 300 + 300,
                "template": {
                    "metadata": {"labels": {"app": name}},
                    "spec": {
                        "serviceAccountName": name,
                        "automountServiceAccountToken": True,
                        "restartPolicy": "Never",
                        "securityContext": {
                            "runAsNonRoot": True,
                            "runAsUser": 1000,
                            "runAsGroup": 1000,
                            "seccompProfile": {"type": "RuntimeDefault"},
                        },
                        "containers": [
                            {
                                "name": "backfill",
                                "image": (
                                    "harbor.andreybondarenko.com/dockerhub/li"
                                    "brary/python:3.15-alpine"
                                ),
                                "command": ["python3", "/config/backfill.py"],
                                "env": [{"name": "PYTHONDONTWRITEBYTECODE", "value": "1"}],
                                "securityContext": {
                                    "allowPrivilegeEscalation": False,
                                    "readOnlyRootFilesystem": True,
                                    "capabilities": {"drop": ["ALL"]},
                                },
                                "resources": {
                                    "requests": {"cpu": "10m", "memory": "32Mi"},
                                    "limits": {"memory": "128Mi"},
                                },
                                "volumeMounts": [
                                    {"name": "config", "mountPath": "/config", "readOnly": True}
                                ],
                            }
                        ],
                        "volumes": [{"name": "config", "configMap": {"name": name}}],
                    },
                },
            },
        }
    )
    return docs


def main():
    """Generate narrowly reviewed native mutations and their guarded GitOps hook."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = "# Generated by tools/security/generate-infra-guards.py.\n" + yaml.safe_dump_all(
        generate(json.loads((ROOT / "infra-guards/catalog.json").read_text())),
        sort_keys=False,
        width=120,
    )
    path = ROOT / "infra-guards/resources.yaml"
    if args.check:
        if not path.read_text() == text:
            raise AssertionError("Generated infrastructure guards are stale")
    else:
        path.write_text(text)


if __name__ == "__main__":
    main()
