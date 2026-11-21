# Traefik Registry RBAC

The Registry controller watches only `harbor`. Its namespaced Role and
RoleBinding are owned by `harbor-custom`, whose Argo project already permits
resources in that namespace. Its existing ClusterRole and ClusterRoleBinding
remain owned by `traefik-registry`, with only read access to IngressClasses
and Nodes. Traefik 3.7.18 starts both informers; removing Node permissions alone
would prevent the informer cache from synchronizing.

Keep Helm `rbac.namespaced=false`: setting it to true also injects
`disableClusterScopeResources=true`, which prevents processing Ingresses with
`spec.ingressClassName`. The chart's built-in RBAC is disabled and replaced by
the explicit resources, preserving the current service account and binding names.

## Publication and rollout

Sync `harbor-custom` first and verify its RoleBinding exists before syncing
`traefik-registry`. Independent automated applications do not guarantee this
order when both changes are published together. No AppProject permissions need
to be expanded.

After rollout, verify that the Registry service account can list Services,
EndpointSlices, Secrets and Ingresses in `harbor`, read IngressClasses and Nodes,
and update Harbor Ingress status. It must not read Secrets in other namespaces
or list them across the cluster. Check the Registry controller for RBAC/cache
errors, then verify certificate validation and an authenticated registry pull.

For rollback, restore the previous Registry chart RBAC values first; leave the
Harbor RoleBinding until the old ClusterRole permissions are restored.
