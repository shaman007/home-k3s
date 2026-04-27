# NetworkPolicy Generation

Some application namespaces share the same NetworkPolicy shapes: default deny,
DNS egress, intra-namespace traffic, and Traefik ingress. Keep those patterns in
`tools/networkpolicy/common-policies/` and generate the Argo-applied bundle into
the application directory.

Generate a bundle:

```powershell
python tools/networkpolicy/generate_common_networkpolicies.py tools/networkpolicy/common-policies/convertx.yaml
```

Generate all bundles:

```powershell
python tools/networkpolicy/generate_common_networkpolicies.py tools/networkpolicy/common-policies
```

Check that a committed bundle is still in sync with its catalog:

```powershell
python tools/networkpolicy/generate_common_networkpolicies.py --check tools/networkpolicy/common-policies
```

Use the generated bundle for boring repeated policies. Keep hand-written
NetworkPolicy manifests when a namespace has unusual peers, selectors, ports, or
comments that document an exception.

Current generated bundles:

- `canitiser/network-policies-generated.yaml`
- `connectivity-exporter/network-policies-generated.yaml`
- `convertx/network-policies-generated.yaml`
- `mempalace/network-policies-generated.yaml`
- `ollama/network-policies-generated.yaml`
- `stirling-pdf/network-policies-generated.yaml`
- `year/network-policies-generated.yaml`
