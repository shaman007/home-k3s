# Feature Specification: Complete Remaining Cluster Hardening Backlog

**Feature Branch**: `001-cluster-hardening-backlog`

**Created**: 2026-07-31

**Status**: Draft

**Input**: User description: "Import the remaining work from
`~/Documents/improvements-2026-07-30.md` into Spec Kit."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - De-risk SeaweedFS storage (Priority: P1)

As the cluster owner, I want SeaweedFS hardened through a staged, data-safe migration so that a
container compromise has less impact without risking the existing filer and volume data.

**Why this priority**: SeaweedFS combines root execution, direct host storage, and single-node
placement, making it the highest-impact remaining risk.

**Independent Test**: This story is complete when recovery is demonstrated from a verified backup,
the copied dataset operates under the selected restricted identity, and the production workload
meets the approved runtime and storage requirements without data loss.

**Acceptance Scenarios**:

1. **Given** the current SeaweedFS data, **When** recovery is exercised in an isolated environment,
   **Then** the recovered filer and volume data is complete and usable.
2. **Given** a copy of the current dataset, **When** the workload runs with the proposed restricted
   identity, **Then** normal storage operations succeed without granting unnecessary privileges.
3. **Given** the storage design decision, **When** the migration is reviewed, **Then** the choice of
   managed persistent storage or documented local storage includes availability, recovery, and
   ownership tradeoffs.

---

### User Story 2 - Stabilize Headlamp and continue safe hardening (Priority: P2)

As the cluster operator, I want the cause of Headlamp's short-lived pod churn identified and
resolved so that the service remains stable before further security restrictions are introduced.

**Why this priority**: The service is available, but repeated replacement pods create operational
noise and may conceal a resource, node, or process-lifecycle fault.

**Independent Test**: This story is complete when evidence identifies the termination cause, the
corrective change is narrowly scoped, and Headlamp remains available without unexpected pod
replacement during a 24-hour observation period.

**Acceptance Scenarios**:

1. **Given** current Headlamp pods and events, **When** termination reasons, node conditions, and
   process exits are reviewed, **Then** the root cause is documented with supporting evidence.
2. **Given** a root-cause-based correction, **When** the rollout is observed for 24 hours, **Then**
   Headlamp remains available and produces no unexplained replacement pods.
3. **Given** stable operation, **When** further hardening is considered, **Then** each restriction
   is assessed and rolled out independently rather than applied as a bulk policy.

---

### User Story 3 - Strengthen validation supply-chain controls (Priority: P3)

As a repository maintainer, I want validation dependencies and custom-resource checks to be
tamper-resistant and explicit so that a successful validation run provides stronger assurance.

**Why this priority**: Movable workflow dependencies, an unverified downloaded validator, and
missing custom-resource schemas weaken the repository's main pre-deployment gate.

**Independent Test**: This story is complete when workflow dependencies use immutable references,
download integrity is checked, and the named custom-resource families receive structural or focused
validation.

**Acceptance Scenarios**:

1. **Given** every external workflow dependency, **When** its reference is reviewed, **Then** it
   resolves to one immutable, reviewed revision.
2. **Given** the downloaded validation tool, **When** its archive is acquired, **Then** execution is
   blocked unless its integrity matches the trusted release value.
3. **Given** Argo CD, Cilium, External Secrets, Traefik, cert-manager, and Longhorn resources,
   **When** repository validation runs, **Then** each family receives an explicit validation path.

---

### User Story 4 - Reduce operational exceptions and warning noise (Priority: P4)

As the cluster operator, I want insecure TLS exceptions and Argo CD orphan warnings resolved only
when ownership and trust evidence support the change so that real risks remain visible.

**Why this priority**: These are defense-in-depth and signal-quality improvements that must not
trade away cluster availability or hide genuinely unmanaged resources.

**Independent Test**: This story is complete when node certificate trust is documented, safe TLS
exceptions are removed, shared-namespace warnings are reduced through narrow ownership rules, and
remaining orphan candidates are classified without deleting retained data.

**Acceptance Scenarios**:

1. **Given** every Talos node's kubelet certificate, **When** its identity and trust chain are
   validated, **Then** Metrics Server no longer requires insecure TLS exceptions.
2. **Given** shared `kube-system` resources, **When** ownership and exclusions are reviewed,
   **Then** warning noise is reduced without globally ignoring broad resource kinds.
3. **Given** retained volumes and generated resources, **When** orphan candidates are classified,
   **Then** each is assigned an owner or documented retention rationale and no persistent volume is
   removed merely to silence a warning.

---

### User Story 5 - Document the current platform accurately (Priority: P5)

As a new operator, I want repository documentation to describe the current Talos/Kubernetes
architecture and clearly identify legacy k3s material so that I do not follow obsolete or insecure
bootstrap instructions.

**Why this priority**: The documentation is misleading but does not currently affect workload
health.

**Independent Test**: A new operator can identify the current platform, find the legacy bootstrap
material, and determine the safe kubeconfig permissions without relying on unwritten context.

**Acceptance Scenarios**:

1. **Given** the repository documentation, **When** a new operator reads the architecture and
   bootstrap sections, **Then** Talos/Kubernetes is identified as current and k3s is clearly marked
   as historical.
2. **Given** retained legacy configuration, **When** its access-mode examples are reviewed, **Then**
   administrative kubeconfig files are restricted to their owner.

### Edge Cases

- SeaweedFS recovery fails or the copied dataset cannot run under a non-root identity.
- A storage migration succeeds functionally but weakens recovery time, availability, or data
  ownership guarantees.
- Headlamp churn stops temporarily without a supported root-cause conclusion.
- A third-party workflow dependency cannot yet be referenced immutably.
- A custom resource has no trustworthy schema compatible with the deployed version.
- One or more Talos nodes present kubelet certificates with unsuitable identities or trust chains.
- Reducing shared-namespace warnings would require a broad exclusion that could conceal unmanaged
  resources.
- An orphan candidate is a retained persistent volume or a controller-generated credential.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The improvement program MUST preserve the current healthy state of workloads,
  persistent data, certificate reconciliation, and secret synchronization after every batch.
- **FR-002**: SeaweedFS changes MUST begin with a verified backup and documented recovery exercise
  using representative filer and volume data.
- **FR-003**: The SeaweedFS target state MUST define its runtime identity, privilege boundary,
  writable paths, storage ownership, node dependency, recovery behavior, and storage design.
- **FR-004**: Any exceptional privilege used solely to prepare SeaweedFS storage MUST be narrowly
  bounded and MUST NOT remain available to long-running containers.
- **FR-005**: Headlamp remediation MUST be based on observed termination reasons, events, node
  conditions, and process behavior; another temporary-storage increase without such evidence is
  out of scope.
- **FR-006**: Additional workload hardening MUST proceed in workload-specific batches with
  independent rollout validation and MUST exclude blanket changes to stateful, interactive,
  GPU-heavy, or persistent-volume-heavy workloads.
- **FR-007**: Shared-namespace orphan-warning changes MUST use explicit ownership or narrow
  exclusions and MUST NOT globally suppress broad resource kinds.
- **FR-008**: Every external workflow dependency MUST use an immutable reviewed reference, or the
  unresolved dependency MUST be documented as a blocking exception.
- **FR-009**: Downloaded validation tooling MUST have its integrity checked against a trusted
  release value before it is used.
- **FR-010**: Repository validation MUST explicitly cover Argo CD, Cilium, External Secrets,
  Traefik, cert-manager, and Longhorn resources through trustworthy schemas or focused checks.
- **FR-011**: Metrics Server TLS exceptions MUST NOT be removed until kubelet certificate identity
  and trust are verified on every Talos node.
- **FR-012**: Documentation MUST identify Talos/Kubernetes as the current platform, mark k3s
  bootstrap material as historical, and specify owner-only administrative kubeconfig access.
- **FR-013**: Each remaining orphan candidate MUST be classified by owner and retention intent;
  persistent volumes MUST NOT be deleted solely to remove warnings.
- **FR-014**: Every repository change MUST update the application-specific manifest and matching
  Argo CD application context when applicable, remain minimal and reversible, and pass available
  non-mutating validation.
- **FR-015**: Live cluster mutations MUST require explicit approval, and prohibited commands in the
  project constitution MUST never be used.
- **FR-016**: Logs, specifications, plans, tasks, validation output, and reviews MUST NOT disclose
  secret values.

### Key Entities

- **Hardening batch**: One independently reviewable and reversible group of changes, with scope,
  evidence, validation results, and rollback conditions.
- **Workload exception**: A documented deviation retained for compatibility or operational need,
  including its rationale, boundaries, risk, and review trigger.
- **Resource owner**: The Argo CD application, platform controller, or documented external process
  responsible for a cluster resource.
- **Trust record**: Evidence that an external dependency, downloaded artifact, certificate chain,
  or resource schema is tied to a reviewed and expected identity.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A representative SeaweedFS backup can be restored and validated with no missing
  sampled filer or volume data before production storage changes begin.
- **SC-002**: All long-running SeaweedFS containers operate with the approved minimal privileges,
  and the accepted storage design documents recovery and single-node failure behavior.
- **SC-003**: Headlamp remains available for a continuous 24-hour observation period with zero
  unexplained replacement pods after remediation.
- **SC-004**: 100% of external workflow dependencies use immutable reviewed references, and 100% of
  downloaded validation executables pass an integrity check before execution.
- **SC-005**: All six named custom-resource families have an explicit validation result in the
  repository's validation workflow.
- **SC-006**: Metrics Server uses authenticated TLS to every Talos kubelet with zero insecure TLS
  bypasses after all node trust checks pass.
- **SC-007**: Every targeted shared-namespace or Longhorn orphan candidate is either assigned an
  owner or given a documented retention rationale, with no broad kind-level global suppression.
- **SC-008**: A reader can identify the current platform, the historical bootstrap path, and the
  required administrative kubeconfig access mode from repository documentation alone.
- **SC-009**: After each completed batch, all affected Argo CD applications and workloads return to
  their expected healthy state and no persistent data or secret value is lost or exposed.

## Assumptions

- The dated review reflects repository revision `218c5a8` and live-cluster observations from
  2026-07-30; current state will be rechecked before planning or implementation.
- The later dated file supersedes the earlier `~/Documents/improvements.md` audit where their
  findings differ.
- Lenka remains an intentionally loose playground and is outside this hardening feature.
- Renovate remains manually reviewed with automatic merging disabled.
- General backup restoration policy is outside scope because restoration has already been
  exercised; only the SeaweedFS migration-specific recovery proof is required here.
- The image builder's constrained privileged mode remains an accepted exception.
- Database, Redis server, Grafana, Vault, mail, interactive shell, GPU, and heavy persistent-volume
  workloads will not receive blanket non-root or read-only-root changes.
- Repository and live-cluster inspection precede each proposal, and all live mutations require
  separate explicit approval under the project constitution.
