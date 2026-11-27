#!/usr/bin/env python3
"""Render observation-only admission annotations for reviewed controller Pods."""

import json
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "tools/monitoring/audit_privileged_workloads.json"
OUTPUT = ROOT / "kubernetes-audit/admission-reviewed-privileged.yaml"
SC_FIELDS = [
    "privileged",
    "allowPrivilegeEscalation",
    "readOnlyRootFilesystem",
    "runAsNonRoot",
    "runAsUser",
    "runAsGroup",
    "procMount",
    "capabilities.add",
    "capabilities.drop",
    "seccompProfile.type",
    "seccompProfile.localhostProfile",
    "seLinuxOptions.user",
    "seLinuxOptions.role",
    "seLinuxOptions.type",
    "seLinuxOptions.level",
    "appArmorProfile.type",
    "appArmorProfile.localhostProfile",
    "windowsOptions.hostProcess",
]
POD_SC_FIELDS = [
    "runAsNonRoot",
    "runAsUser",
    "runAsGroup",
    "fsGroup",
    "fsGroupChangePolicy",
    "supplementalGroups",
    "supplementalGroupsPolicy",
    "seccompProfile.type",
    "seccompProfile.localhostProfile",
    "seLinuxOptions.user",
    "seLinuxOptions.role",
    "seLinuxOptions.type",
    "seLinuxOptions.level",
    "sysctls",
]


def literal(value):
    return json.dumps(value, ensure_ascii=True)


def optional(path):
    return ".?".join(path.split("."))


def guards(path, expected, fields):
    terms = []
    for field in fields:
        value = expected
        for part in field.split("."):
            value = value.get(part) if isinstance(value, dict) else None
        default = (
            []
            if field
            in [
                "capabilities.add",
                "capabilities.drop",
                "sysctls",
                "supplementalGroups",
            ]
            else False
            if field
            in ["privileged", "readOnlyRootFilesystem", "windowsOptions.hostProcess"]
            else "Default"
            if field == "procMount"
            else None
        )
        value = default if value is None else value
        terms.append(
            f"{path}.?{optional(field)}.orValue({literal(default)}) == {literal(value)}"
        )
    return terms


def profile_expression(entry):
    """Identity plus exact container/image/security/mount/host-path boundaries."""
    spec = entry["spec"]
    owner = entry["owner"]
    terms = [
        f"object.metadata.namespace == {literal(entry['namespace'])}",
        f'"app" in object.metadata.?labels.orValue({{}}) && object.metadata.labels["app"] == {literal(entry["app"])}',
        f'object.metadata.?name.orValue("").startsWith({literal(entry["podPrefix"])}) || (object.metadata.?name.orValue("") == "" && object.metadata.?generateName.orValue("") == {literal(entry["podPrefix"])})',
        "object.metadata.?ownerReferences.orValue([]).exists(o, "
        + " && ".join(
            [f"o.{k} == {literal(v)}" for k, v in owner.items()]
            + ["o.?controller.orValue(false)"]
        )
        + ")",
        f'object.spec.?serviceAccountName.orValue("default") == {literal(spec["serviceAccountName"])}',
        "object.spec.?ephemeralContainers.orValue([]).size() == 0",
    ]
    if entry.get("revisionHash"):
        terms.append(
            f'"controller-revision-hash" in object.metadata.?labels.orValue({{}}) && object.metadata.labels["controller-revision-hash"] == {literal(entry["revisionHash"])}'
        )
    terms.append(
        f"object.spec.?automountServiceAccountToken.orValue(true) == {literal(spec.get('automountServiceAccountToken', True))}"
    )
    for field in ["hostNetwork", "hostPID", "hostIPC", "shareProcessNamespace"]:
        terms.append(
            f"object.spec.?{field}.orValue(false) == {literal(spec.get(field, False))}"
        )
    terms += guards(
        "object.spec.?securityContext", spec.get("securityContext", {}), POD_SC_FIELDS
    )
    for section in ["containers", "initContainers"]:
        containers = spec.get(section, [])
        terms.append(f"object.spec.?{section}.orValue([]).size() == {len(containers)}")
        for c in containers:
            checks = [
                f"c.name == {literal(c['name'])}",
                f"c.image == {literal(c['image'])}",
            ]
            checks += guards(
                "c.?securityContext", c.get("securityContext", {}), SC_FIELDS
            )
            mounts = c.get("volumeMounts", [])
            actual = 'c.?volumeMounts.orValue([]).filter(m, !(m.name.startsWith("kube-api-access-") && m.mountPath == "/var/run/secrets/kubernetes.io/serviceaccount" && m.?readOnly.orValue(false)))'
            checks.append(f"{actual}.size() == {len(mounts)}")
            for m in mounts:
                mt = [f"m.{k} == {literal(m[k])}" for k in ["name", "mountPath"]]
                for k, default in [
                    ("readOnly", False),
                    ("subPath", ""),
                    ("subPathExpr", ""),
                    ("mountPropagation", "None"),
                ]:
                    mt.append(
                        f"m.?{k}.orValue({literal(default)}) == {literal(m.get(k, default))}"
                    )
                checks.append(
                    "c.?volumeMounts.orValue([]).exists(m, " + " && ".join(mt) + ")"
                )
            terms.append(
                f"object.spec.?{section}.orValue([]).exists(c, "
                + " && ".join(checks)
                + ")"
            )
    hostpaths = spec.get("volumes", [])
    terms.append(
        f"object.spec.?volumes.orValue([]).filter(v, has(v.hostPath)).size() == {len(hostpaths)}"
    )
    for v in hostpaths:
        terms.append(
            "object.spec.?volumes.orValue([]).exists(v, "
            + f'v.name == {literal(v["name"])} && has(v.hostPath) && v.hostPath.path == {literal(v["hostPath"]["path"])} && v.hostPath.?type.orValue("") == {literal(v["hostPath"].get("type", ""))})'
        )
    return " &&\n".join("(" + t + ")" for t in terms)


def documents(entries):
    variables = []
    choices = []
    for i, e in enumerate(entries):
        name = "profile" + str(i)
        variables.append({"name": name, "expression": profile_expression(e)})
        create = f'(request.operation == "CREATE" && request.userInfo.username == {literal(e["createActor"])})'
        operation = create
        if e.get("metadataUpdateActor"):
            operation += (
                " || "
                + f'(request.operation == "UPDATE" && request.userInfo.username == {literal(e["metadataUpdateActor"])} && oldObject != null && object.spec == oldObject.spec)'
            )
        choices.append(f"(variables.{name} && ({operation})) ? {literal(e['id'])} : ")
    variables.append({"name": "reviewed", "expression": "".join(choices) + '""'})
    policy = {
        "apiVersion": "admissionregistration.k8s.io/v1",
        "kind": "ValidatingAdmissionPolicy",
        "metadata": {"name": "homelab-audit-reviewed-privileged"},
        "spec": {
            "failurePolicy": "Ignore",
            "matchConstraints": {
                "resourceRules": [
                    {
                        "apiGroups": [""],
                        "apiVersions": ["v1"],
                        "operations": ["CREATE", "UPDATE"],
                        "resources": ["pods"],
                    }
                ]
            },
            "matchConditions": [
                {
                    "name": "main-resource-only",
                    "expression": 'request.?subResource.orValue("") == ""',
                }
            ],
            "variables": variables,
            "validations": [{"expression": "true"}],
            "auditAnnotations": [
                {"key": "expected", "valueExpression": "variables.reviewed"}
            ],
        },
    }
    binding = {
        "apiVersion": policy["apiVersion"],
        "kind": "ValidatingAdmissionPolicyBinding",
        "metadata": {"name": policy["metadata"]["name"]},
        "spec": {
            "policyName": policy["metadata"]["name"],
            "validationActions": ["Audit"],
        },
    }
    return [policy, binding]


START = "      // BEGIN generated reviewed privileged Pods\n"
END = "      // END generated reviewed privileged Pods\n"


def render_alloy(entries):
    """Recheck admission markers against the actor, verb, namespace and outcome."""

    def eq(field, value):
        return f"(eq .{field} {literal(value)})"

    def combine(operation, *terms):
        return "(" + operation + " " + " ".join(terms) + ")"

    profiles = []
    for entry in entries:
        operations = [
            combine("and", eq("actor", entry["createActor"]), eq("verb", "create"))
        ]
        if entry.get("metadataUpdateActor"):
            operations.append(
                combine(
                    "and",
                    eq("actor", entry["metadataUpdateActor"]),
                    combine("or", eq("verb", "update"), eq("verb", "patch")),
                )
            )
        profiles.append(
            combine(
                "and",
                eq("target_namespace", entry["namespace"]),
                eq("reviewed_privileged", entry["id"]),
                combine("or", *operations),
            )
        )
    outcome = (
        "(or (and (ge (int .code) 200) (lt (int .code) 300)) (eq (int .code) 409))"
    )
    expression = combine(
        "and",
        "(not .impersonated)",
        "(not .subresource)",
        eq("resource", "pods"),
        outcome,
        combine("or", *profiles),
    )
    return (
        START
        + "      // Source: tools/monitoring/audit_privileged_workloads.json.\n"
        + '      stage.template {\n        source = "expected_privileged_pod"\n'
        + "        template = `{{ if "
        + expression
        + " }}yes{{ end }}`\n      }\n"
        + END
    )


def main():
    entries = json.loads(CATALOG.read_text())["entries"]
    OUTPUT.write_text(
        "# Generated by tools/monitoring/generate_privileged_audit_exceptions.py\n"
        + yaml.safe_dump_all(documents(entries), sort_keys=False, width=110)
    )
    path = ROOT / "kubernetes-audit/config-map-audit-alloy.yaml"
    text = path.read_text()
    begin = text.index(START)
    end = text.index(END, begin) + len(END)
    path.write_text(text[:begin] + render_alloy(entries) + text[end:])


if __name__ == "__main__":
    main()
