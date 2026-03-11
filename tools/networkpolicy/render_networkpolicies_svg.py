#!/usr/bin/env python3

import argparse
import collections
import datetime as dt
import json
import math
import pathlib
import subprocess
import textwrap
import xml.sax.saxutils as saxutils


SVG_WIDTH = 1960
PAGE_MARGIN = 28
GAP = 20
SECTION_WIDTH = 608
POLICY_WIDTH = SECTION_WIDTH - 32
OVERVIEW_BOX_WIDTH = 216
OVERVIEW_BOX_HEIGHT = 62
OVERVIEW_COLUMNS = 8

TITLE_FONT = 30
SUBTITLE_FONT = 15
SECTION_TITLE_FONT = 21
SMALL_FONT = 12
MONO_FONT = 12
LINE_HEIGHT = 17

GRAPH_NODE_WIDTH = 196
GRAPH_NODE_HEIGHT = 20
GRAPH_ROW_GAP = 26
GRAPH_CURVE = 340

INTERNET_CIDRS = {"0.0.0.0/0", "::/0"}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Render all Kubernetes NetworkPolicies into an SVG inventory."
    )
    parser.add_argument(
        "--input",
        type=pathlib.Path,
        help="Optional input JSON file from `kubectl get networkpolicies --all-namespaces -o json`.",
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=pathlib.Path("tools/networkpolicy/networkpolicies-live.svg"),
        help="Output SVG path.",
    )
    parser.add_argument(
        "--context",
        help="Optional Kubernetes context label to show in the header.",
    )
    return parser.parse_args()


def run_command(args):
    return subprocess.check_output(args, text=True).strip()


def load_payload(input_path):
    if input_path:
        return json.loads(input_path.read_text(encoding="utf-8"))
    raw = run_command(["kubectl", "get", "networkpolicies", "--all-namespaces", "-o", "json"])
    return json.loads(raw)


def detect_context(cli_context):
    if cli_context:
        return cli_context
    try:
        return run_command(["kubectl", "config", "current-context"])
    except Exception:
        return "unknown"


def xml(text):
    return saxutils.escape(str(text), {'"': "&quot;"})


def stable_labels(labels):
    pairs = sorted(labels.items())
    return ", ".join(f"{key}={value}" for key, value in pairs)


def format_selector(selector):
    labels = (selector or {}).get("matchLabels", {})
    if not labels:
        return "all pods"
    return "{" + stable_labels(labels) + "}"


def exact_namespace_name(selector):
    if not selector:
        return None
    labels = selector.get("matchLabels", {})
    if set(labels) == {"kubernetes.io/metadata.name"}:
        return labels["kubernetes.io/metadata.name"]
    return None


def format_namespace_selector(selector):
    labels = selector.get("matchLabels", {})
    exact_name = exact_namespace_name(selector)
    if exact_name:
        return f"ns:{exact_name}"
    if labels:
        return "ns{" + stable_labels(labels) + "}"
    return "all namespaces"


def format_peer(peer):
    parts = []
    if "namespaceSelector" in peer:
        parts.append(format_namespace_selector(peer["namespaceSelector"]))
    if "podSelector" in peer:
        parts.append("pod" + format_selector(peer["podSelector"]))
    if "ipBlock" in peer:
        ip_block = peer["ipBlock"]
        text = f"ip:{ip_block['cidr']}"
        excepts = ip_block.get("except") or []
        if excepts:
            text += " except " + ", ".join(excepts)
        parts.append(text)
    if not parts:
        return "all peers"
    return " & ".join(parts)


def format_ports(ports):
    if not ports:
        return "all ports"
    chunks = []
    for port in ports:
        protocol = port.get("protocol", "TCP")
        port_value = port.get("port", "all")
        chunks.append(f"{protocol}/{port_value}")
    return ", ".join(chunks)


def summarize_rule(direction, rule):
    peers_key = "from" if direction == "IN" else "to"
    peers = rule.get(peers_key)
    ports = format_ports(rule.get("ports"))
    peer_text = ", ".join(format_peer(peer) for peer in peers) if peers else "all peers"
    action = "from" if direction == "IN" else "to"
    return f"{direction} {action} {peer_text} on {ports}"


def wrap_text(text, width):
    return textwrap.wrap(text, width=width, break_long_words=False, break_on_hyphens=False) or [""]


def policy_kind(policy):
    spec = policy["spec"]
    policy_types = spec.get("policyTypes") or []
    ingress = "Ingress" in policy_types
    egress = "Egress" in policy_types
    has_rules = bool(spec.get("ingress")) or bool(spec.get("egress"))
    if not has_rules and ingress and egress:
        return "deny-both"
    if not has_rules and ingress:
        return "deny-ingress"
    if not has_rules and egress:
        return "deny-egress"
    if ingress and egress:
        return "mixed"
    if ingress:
        return "ingress"
    return "egress"


def summarize_policy(policy):
    metadata = policy["metadata"]
    spec = policy["spec"]
    policy_types = spec.get("policyTypes") or []
    lines = [f"Applies to {format_selector(spec.get('podSelector', {}))}"]

    ingress_rules = spec.get("ingress") or []
    egress_rules = spec.get("egress") or []

    if "Ingress" in policy_types:
        if ingress_rules:
            for rule in ingress_rules:
                lines.append(summarize_rule("IN", rule))
        else:
            lines.append("IN deny all ingress")

    if "Egress" in policy_types:
        if egress_rules:
            for rule in egress_rules:
                lines.append(summarize_rule("OUT", rule))
        else:
            lines.append("OUT deny all egress")

    return {
        "name": metadata["name"],
        "namespace": metadata["namespace"],
        "kind": policy_kind(policy),
        "types": ", ".join(policy_types) if policy_types else "unspecified",
        "lines": lines,
    }


def count_namespace_stats(policies):
    counts = collections.Counter()
    deny_defaults = 0
    ingress = 0
    egress = 0
    for policy in policies:
        counts["total"] += 1
        types = policy["types"]
        if "Ingress" in types:
            ingress += 1
        if "Egress" in types:
            egress += 1
        if policy["kind"].startswith("deny"):
            deny_defaults += 1
    counts["ingress"] = ingress
    counts["egress"] = egress
    counts["deny"] = deny_defaults
    return counts


def estimate_policy_height(policy):
    line_count = 1
    for line in policy["lines"]:
        line_count += len(wrap_text(line, 66))
    return 50 + line_count * LINE_HEIGHT


def layout_namespaces(namespace_sections, start_y):
    column_x = [PAGE_MARGIN + i * (SECTION_WIDTH + GAP) for i in range(3)]
    column_y = [start_y, start_y, start_y]
    positioned = []

    for section in namespace_sections:
        index = min(range(3), key=lambda idx: column_y[idx])
        x = column_x[index]
        y = column_y[index]
        section["x"] = x
        section["y"] = y
        positioned.append(section)
        column_y[index] += section["height"] + GAP

    return positioned, max(column_y) + PAGE_MARGIN


def build_namespace_sections(payload):
    grouped = collections.defaultdict(list)
    for item in payload["items"]:
        grouped[item["metadata"]["namespace"]].append(summarize_policy(item))

    sections = []
    for namespace in sorted(grouped):
        policies = sorted(grouped[namespace], key=lambda item: item["name"])
        stats = count_namespace_stats(policies)
        body_height = 54
        for policy in policies:
            policy["height"] = estimate_policy_height(policy)
            body_height += policy["height"] + 10
        sections.append(
            {
                "namespace": namespace,
                "policies": policies,
                "stats": stats,
                "height": body_height + 18,
            }
        )
    sections.sort(key=lambda section: (-section["height"], section["namespace"]))
    return sections


def make_graph_node(key, label, is_special):
    return {"key": key, "label": label, "is_special": is_special}


def graph_node_from_peer(peer, current_namespace):
    if not peer:
        return make_graph_node("special:all-peers", "All peers", True)

    if "ipBlock" in peer:
        cidr = peer["ipBlock"]["cidr"]
        if cidr in INTERNET_CIDRS:
            return make_graph_node("special:internet", "Internet", True)
        return make_graph_node(f"special:cidr:{cidr}", f"CIDR {cidr}", True)

    namespace_selector = peer.get("namespaceSelector")
    pod_selector = peer.get("podSelector")
    exact_name = exact_namespace_name(namespace_selector)
    if exact_name:
        return make_graph_node(exact_name, exact_name, False)

    if namespace_selector and pod_selector:
        label = f"{format_namespace_selector(namespace_selector)} & pod{format_selector(pod_selector)}"
        return make_graph_node(f"special:selector:{label}", label, True)

    if namespace_selector:
        label = format_namespace_selector(namespace_selector)
        if label == "all namespaces":
            return make_graph_node("special:all-namespaces", "All namespaces", True)
        return make_graph_node(f"special:selector:{label}", label, True)

    if pod_selector:
        return make_graph_node(current_namespace, current_namespace, False)

    return make_graph_node("special:all-peers", "All peers", True)


def barycenter_for(node_key, neighbor_positions, neighbors):
    weighted = []
    for neighbor_key, weight in neighbors.get(node_key, []):
        if neighbor_key in neighbor_positions:
            weighted.extend([neighbor_positions[neighbor_key]] * max(1, weight))
    if not weighted:
        return float("inf")
    return sum(weighted) / len(weighted)


def optimize_bipartite_order(left_nodes, right_nodes, edges):
    left_order = [node["key"] for node in left_nodes]
    right_order = [node["key"] for node in right_nodes]
    left_lookup = {node["key"]: node for node in left_nodes}
    right_lookup = {node["key"]: node for node in right_nodes}

    left_neighbors = collections.defaultdict(list)
    right_neighbors = collections.defaultdict(list)
    for edge in edges:
        left_neighbors[edge["source"]].append((edge["target"], edge["count"]))
        right_neighbors[edge["target"]].append((edge["source"], edge["count"]))

    for _ in range(6):
        left_positions = {key: index for index, key in enumerate(left_order)}
        right_order.sort(
            key=lambda key: (
                right_lookup[key]["is_special"],
                barycenter_for(key, left_positions, right_neighbors),
                right_lookup[key]["label"],
            )
        )
        right_positions = {key: index for index, key in enumerate(right_order)}
        left_order.sort(
            key=lambda key: (
                left_lookup[key]["is_special"],
                barycenter_for(key, right_positions, left_neighbors),
                left_lookup[key]["label"],
            )
        )

    return left_order, right_order


def build_connection_graph(payload, namespace_sections):
    namespace_names = sorted(section["namespace"] for section in namespace_sections)
    edge_map = {}
    source_specials = {}
    target_specials = {}
    hidden_self_edges = 0

    def add_edge(source_node, target_node, via):
        nonlocal hidden_self_edges
        if source_node["key"] == target_node["key"]:
            hidden_self_edges += 1
            return

        if source_node["is_special"]:
            source_specials[source_node["key"]] = source_node
        if target_node["is_special"]:
            target_specials[target_node["key"]] = target_node

        edge = edge_map.setdefault(
            (source_node["key"], target_node["key"]),
            {
                "source": source_node["key"],
                "target": target_node["key"],
                "source_label": source_node["label"],
                "target_label": target_node["label"],
                "count": 0,
                "via": set(),
                "source_special": source_node["is_special"],
                "target_special": target_node["is_special"],
            },
        )
        edge["count"] += 1
        edge["via"].add(via)

    for item in payload["items"]:
        namespace = item["metadata"]["namespace"]
        spec = item["spec"]

        for rule in spec.get("egress") or []:
            for peer in rule.get("to") or [{}]:
                add_edge(
                    make_graph_node(namespace, namespace, False),
                    graph_node_from_peer(peer, namespace),
                    "egress",
                )

        for rule in spec.get("ingress") or []:
            for peer in rule.get("from") or [{}]:
                add_edge(
                    graph_node_from_peer(peer, namespace),
                    make_graph_node(namespace, namespace, False),
                    "ingress",
                )

    edges = sorted(
        edge_map.values(),
        key=lambda edge: (edge["count"], edge["source_label"], edge["target_label"]),
    )

    out_counts = collections.Counter()
    in_counts = collections.Counter()
    for edge in edges:
        out_counts[edge["source"]] += edge["count"]
        in_counts[edge["target"]] += edge["count"]

    referenced_namespaces = {
        edge["source"] for edge in edges if not edge["source_special"]
    } | {
        edge["target"] for edge in edges if not edge["target_special"]
    }
    extra_namespaces = sorted(referenced_namespaces - set(namespace_names))
    all_namespace_nodes = namespace_names + extra_namespaces

    left_nodes = [make_graph_node(name, name, False) for name in all_namespace_nodes]
    left_nodes.extend(sorted(source_specials.values(), key=lambda node: node["label"]))
    right_nodes = [make_graph_node(name, name, False) for name in all_namespace_nodes]
    right_nodes.extend(sorted(target_specials.values(), key=lambda node: node["label"]))

    left_order, right_order = optimize_bipartite_order(left_nodes, right_nodes, edges)

    left_lookup = {node["key"]: node for node in left_nodes}
    right_lookup = {node["key"]: node for node in right_nodes}

    return {
        "edges": edges,
        "hidden_self_edges": hidden_self_edges,
        "left_nodes": [left_lookup[key] for key in left_order],
        "right_nodes": [right_lookup[key] for key in right_order],
        "out_counts": out_counts,
        "in_counts": in_counts,
        "visible_edge_count": len(edges),
    }


def render_text(x, y, lines, class_name):
    fragments = []
    for index, line in enumerate(lines):
        fragments.append(
            f'<text x="{x}" y="{y + index * LINE_HEIGHT}" class="{class_name}">{xml(line)}</text>'
        )
    return "\n".join(fragments)


def render_overview(namespace_sections, context_label, updated_at):
    total_policies = sum(section["stats"]["total"] for section in namespace_sections)
    total_namespaces = len(namespace_sections)
    lines = []
    lines.append(
        f'<text x="{PAGE_MARGIN}" y="58" class="title">Kubernetes NetworkPolicy Inventory</text>'
    )
    lines.append(
        f'<text x="{PAGE_MARGIN}" y="85" class="subtitle">Context: {xml(context_label)} | Generated: {xml(updated_at)} | Namespaces: {total_namespaces} | Policies: {total_policies}</text>'
    )

    lines.append(
        f'<rect x="{PAGE_MARGIN}" y="106" width="{SVG_WIDTH - PAGE_MARGIN * 2}" height="82" rx="18" class="overview-panel" />'
    )
    legend_y = 134
    legend_items = [
        ("policy ingress", "Ingress policy"),
        ("policy egress", "Egress policy"),
        ("policy mixed", "Ingress + Egress"),
        ("policy deny-both", "Default deny / empty rule set"),
    ]
    legend_x = PAGE_MARGIN + 20
    for class_name, label in legend_items:
        lines.append(
            f'<rect x="{legend_x}" y="{legend_y - 16}" width="18" height="18" rx="4" class="{class_name}" />'
        )
        lines.append(
            f'<text x="{legend_x + 28}" y="{legend_y - 2}" class="legend">{xml(label)}</text>'
        )
        legend_x += 250

    grid_top = 218
    for index, section in enumerate(sorted(namespace_sections, key=lambda item: item["namespace"])):
        row = index // OVERVIEW_COLUMNS
        col = index % OVERVIEW_COLUMNS
        x = PAGE_MARGIN + col * (OVERVIEW_BOX_WIDTH + 12)
        y = grid_top + row * (OVERVIEW_BOX_HEIGHT + 12)
        stats = section["stats"]
        lines.append(
            f'<rect x="{x}" y="{y}" width="{OVERVIEW_BOX_WIDTH}" height="{OVERVIEW_BOX_HEIGHT}" rx="14" class="namespace-chip" />'
        )
        lines.append(
            f'<text x="{x + 14}" y="{y + 24}" class="chip-title">{xml(section["namespace"])}</text>'
        )
        lines.append(
            f'<text x="{x + 14}" y="{y + 46}" class="chip-subtitle">{stats["total"]} policies | IN {stats["ingress"]} | OUT {stats["egress"]} | deny {stats["deny"]}</text>'
        )

    rows = math.ceil(len(namespace_sections) / OVERVIEW_COLUMNS)
    return "\n".join(lines), grid_top + rows * (OVERVIEW_BOX_HEIGHT + 12) + 26


def edge_class(edge):
    if edge["via"] == {"ingress"}:
        return "ingress"
    if edge["via"] == {"egress"}:
        return "egress"
    return "both"


def render_connection_graph(graph_data, start_y):
    row_count = max(len(graph_data["left_nodes"]), len(graph_data["right_nodes"]))
    graph_height = 158 + row_count * GRAPH_ROW_GAP
    panel_x = PAGE_MARGIN
    panel_y = start_y
    panel_width = SVG_WIDTH - PAGE_MARGIN * 2
    panel_height = graph_height

    left_x = panel_x + 26
    right_x = panel_x + panel_width - 26 - GRAPH_NODE_WIDTH
    row_top = panel_y + 128

    left_positions = {
        node["key"]: row_top + index * GRAPH_ROW_GAP + GRAPH_NODE_HEIGHT / 2
        for index, node in enumerate(graph_data["left_nodes"])
    }
    right_positions = {
        node["key"]: row_top + index * GRAPH_ROW_GAP + GRAPH_NODE_HEIGHT / 2
        for index, node in enumerate(graph_data["right_nodes"])
    }

    parts = []
    parts.append(
        f'<rect x="{panel_x}" y="{panel_y}" width="{panel_width}" height="{panel_height}" rx="22" class="graph-panel" />'
    )
    parts.append(
        f'<text x="{panel_x + 20}" y="{panel_y + 34}" class="section-title">Connection Graph</text>'
    )
    parts.append(
        f'<text x="{panel_x + 20}" y="{panel_y + 56}" class="section-subtitle">Namespace-level directed flows aggregated from policy peers. Sources are on the left, targets are on the right.</text>'
    )
    parts.append(
        f'<text x="{panel_x + 20}" y="{panel_y + 76}" class="section-subtitle">Visible cross-namespace or special-target links: {graph_data["visible_edge_count"]} | Hidden same-namespace links: {graph_data["hidden_self_edges"]}</text>'
    )

    legend_y = panel_y + 98
    legend_items = [
        ("edge ingress", "Allowed because of ingress rule"),
        ("edge egress", "Allowed because of egress rule"),
        ("edge both", "Seen from both sides"),
    ]
    legend_x = panel_x + 20
    for class_name, label in legend_items:
        parts.append(
            f'<line x1="{legend_x}" y1="{legend_y}" x2="{legend_x + 26}" y2="{legend_y}" class="{class_name}" />'
        )
        parts.append(
            f'<text x="{legend_x + 36}" y="{legend_y + 4}" class="legend">{xml(label)}</text>'
        )
        legend_x += 310

    parts.append(
        f'<text x="{left_x}" y="{panel_y + 118}" class="graph-heading">Sources</text>'
    )
    parts.append(
        f'<text x="{right_x}" y="{panel_y + 118}" class="graph-heading">Targets</text>'
    )

    parts.append(
        f'<line x1="{left_x + GRAPH_NODE_WIDTH + 8}" y1="{row_top - 16}" x2="{left_x + GRAPH_NODE_WIDTH + 8}" y2="{panel_y + panel_height - 20}" class="graph-guide" />'
    )
    parts.append(
        f'<line x1="{right_x - 8}" y1="{row_top - 16}" x2="{right_x - 8}" y2="{panel_y + panel_height - 20}" class="graph-guide" />'
    )

    for edge in graph_data["edges"]:
        y1 = left_positions[edge["source"]]
        y2 = right_positions[edge["target"]]
        x1 = left_x + GRAPH_NODE_WIDTH
        x2 = right_x
        stroke_width = 0.9 + min(4.8, edge["count"] * 0.75)
        opacity = min(0.72, 0.24 + edge["count"] * 0.09)
        klass = edge_class(edge)
        parts.append(
            f'<path d="M {x1} {y1} C {x1 + GRAPH_CURVE} {y1}, {x2 - GRAPH_CURVE} {y2}, {x2} {y2}" class="edge {klass}" style="stroke-width:{stroke_width};opacity:{opacity}" />'
        )
        if edge["count"] >= 3:
            label_x = (x1 + x2) / 2
            label_y = (y1 + y2) / 2 - 4
            parts.append(
                f'<text x="{label_x}" y="{label_y}" class="edge-count">{edge["count"]}</text>'
            )

    for index, node in enumerate(graph_data["left_nodes"]):
        y = row_top + index * GRAPH_ROW_GAP
        node_class = "graph-node special" if node["is_special"] else "graph-node"
        out_value = graph_data["out_counts"].get(node["key"], 0)
        parts.append(
            f'<rect x="{left_x}" y="{y}" width="{GRAPH_NODE_WIDTH}" height="{GRAPH_NODE_HEIGHT}" rx="10" class="{node_class}" />'
        )
        parts.append(
            f'<text x="{left_x + 12}" y="{y + 14}" class="graph-node-label">{xml(node["label"])}</text>'
        )
        parts.append(
            f'<text x="{left_x + GRAPH_NODE_WIDTH - 10}" y="{y + 14}" text-anchor="end" class="graph-node-metric">{out_value}</text>'
        )

    for index, node in enumerate(graph_data["right_nodes"]):
        y = row_top + index * GRAPH_ROW_GAP
        node_class = "graph-node special" if node["is_special"] else "graph-node"
        in_value = graph_data["in_counts"].get(node["key"], 0)
        parts.append(
            f'<rect x="{right_x}" y="{y}" width="{GRAPH_NODE_WIDTH}" height="{GRAPH_NODE_HEIGHT}" rx="10" class="{node_class}" />'
        )
        parts.append(
            f'<text x="{right_x + 12}" y="{y + 14}" class="graph-node-label">{xml(node["label"])}</text>'
        )
        parts.append(
            f'<text x="{right_x + GRAPH_NODE_WIDTH - 10}" y="{y + 14}" text-anchor="end" class="graph-node-metric">{in_value}</text>'
        )

    return "\n".join(parts), panel_y + panel_height + 26


def render_namespace_section(section):
    x = section["x"]
    y = section["y"]
    stats = section["stats"]
    parts = []

    parts.append(
        f'<rect x="{x}" y="{y}" width="{SECTION_WIDTH}" height="{section["height"]}" rx="22" class="namespace-panel" />'
    )
    parts.append(
        f'<text x="{x + 16}" y="{y + 30}" class="section-title">{xml(section["namespace"])}</text>'
    )
    stats_line = f'{stats["total"]} policies | IN {stats["ingress"]} | OUT {stats["egress"]} | deny {stats["deny"]}'
    parts.append(
        f'<text x="{x + 16}" y="{y + 52}" class="section-subtitle">{xml(stats_line)}</text>'
    )

    cursor_y = y + 70
    for policy in section["policies"]:
        parts.append(
            f'<rect x="{x + 12}" y="{cursor_y}" width="{POLICY_WIDTH}" height="{policy["height"]}" rx="16" class="policy {policy["kind"]}" />'
        )
        parts.append(
            f'<text x="{x + 24}" y="{cursor_y + 24}" class="policy-title">{xml(policy["name"])}</text>'
        )
        parts.append(
            f'<text x="{x + 24}" y="{cursor_y + 42}" class="policy-subtitle">{xml(policy["types"])}</text>'
        )
        text_y = cursor_y + 62
        for line in policy["lines"]:
            wrapped = wrap_text(line, 66)
            parts.append(render_text(x + 24, text_y, wrapped, "policy-body"))
            text_y += len(wrapped) * LINE_HEIGHT
        cursor_y += policy["height"] + 10

    return "\n".join(parts)


def render_svg(namespace_sections, graph_data, context_label):
    updated_at = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    overview_svg, start_y = render_overview(namespace_sections, context_label, updated_at)
    graph_svg, graph_end_y = render_connection_graph(graph_data, start_y)
    positioned, total_height = layout_namespaces(namespace_sections, graph_end_y)
    sections_svg = "\n".join(render_namespace_section(section) for section in positioned)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_WIDTH}" height="{total_height}" viewBox="0 0 {SVG_WIDTH} {total_height}" role="img" aria-labelledby="title desc">
  <title id="title">Kubernetes NetworkPolicy Inventory</title>
  <desc id="desc">Overview, connection graph, and per-namespace inventory of live Kubernetes NetworkPolicy objects.</desc>
  <defs>
    <style>
      .bg {{ fill: #f4f1e8; }}
      .title {{ font: 700 {TITLE_FONT}px 'Segoe UI', Arial, sans-serif; fill: #1d2a33; }}
      .subtitle {{ font: 500 {SUBTITLE_FONT}px 'Segoe UI', Arial, sans-serif; fill: #50606c; }}
      .legend {{ font: 600 {SMALL_FONT}px 'Segoe UI', Arial, sans-serif; fill: #33424d; }}
      .overview-panel {{ fill: #fffaf0; stroke: #d9c9a3; stroke-width: 1.4; }}
      .namespace-chip {{ fill: #fdfdfc; stroke: #d7dee2; stroke-width: 1.2; }}
      .chip-title {{ font: 700 14px 'Segoe UI', Arial, sans-serif; fill: #23333d; }}
      .chip-subtitle {{ font: 500 12px 'Segoe UI', Arial, sans-serif; fill: #5d6f7a; }}
      .graph-panel {{ fill: #fcfcfb; stroke: #d8e0e4; stroke-width: 1.5; }}
      .graph-heading {{ font: 700 13px 'Segoe UI', Arial, sans-serif; fill: #2b3d46; }}
      .graph-guide {{ stroke: #d8dee2; stroke-width: 1; }}
      .graph-node {{ fill: #f0f7fb; stroke: #aac1cf; stroke-width: 1; }}
      .graph-node.special {{ fill: #fdf2df; stroke: #d6ba84; }}
      .graph-node-label {{ font: 600 11px 'Segoe UI', Arial, sans-serif; fill: #20323c; }}
      .graph-node-metric {{ font: 700 11px Consolas, 'Courier New', monospace; fill: #455a66; }}
      .edge {{ fill: none; }}
      .edge.ingress {{ stroke: #4d88c7; marker-end: url(#arrow-ingress); }}
      .edge.egress {{ stroke: #d48a2b; marker-end: url(#arrow-egress); }}
      .edge.both {{ stroke: #4a9b69; marker-end: url(#arrow-both); }}
      .edge-count {{ font: 700 10px Consolas, 'Courier New', monospace; fill: #52656f; text-anchor: middle; }}
      .namespace-panel {{ fill: #fbfcfb; stroke: #d9e0e3; stroke-width: 1.6; }}
      .section-title {{ font: 700 {SECTION_TITLE_FONT}px 'Segoe UI', Arial, sans-serif; fill: #18303d; }}
      .section-subtitle {{ font: 600 12px 'Segoe UI', Arial, sans-serif; fill: #5d6a73; }}
      .policy-title {{ font: 700 13px 'Segoe UI', Arial, sans-serif; fill: #12222c; }}
      .policy-subtitle {{ font: 600 11px 'Segoe UI', Arial, sans-serif; fill: #4b5f69; }}
      .policy-body {{ font: 500 {MONO_FONT}px Consolas, 'Courier New', monospace; fill: #24333b; }}
      .policy {{ stroke-width: 1.1; }}
      .policy.ingress {{ fill: #edf6ff; stroke: #98bde6; }}
      .policy.egress {{ fill: #fff3df; stroke: #d8b574; }}
      .policy.mixed {{ fill: #ebf7ef; stroke: #8dbca0; }}
      .policy.deny-both {{ fill: #fdebea; stroke: #db8e88; }}
      .policy.deny-ingress {{ fill: #f6edff; stroke: #b39bcf; }}
      .policy.deny-egress {{ fill: #fff0ea; stroke: #d9a08e; }}
    </style>
    <marker id="arrow-ingress" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto">
      <path d="M 0 0 L 10 4 L 0 8 z" fill="#4d88c7" />
    </marker>
    <marker id="arrow-egress" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto">
      <path d="M 0 0 L 10 4 L 0 8 z" fill="#d48a2b" />
    </marker>
    <marker id="arrow-both" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto">
      <path d="M 0 0 L 10 4 L 0 8 z" fill="#4a9b69" />
    </marker>
  </defs>
  <rect class="bg" x="0" y="0" width="{SVG_WIDTH}" height="{total_height}" />
  {overview_svg}
  {graph_svg}
  {sections_svg}
</svg>
"""


def main():
    args = parse_args()
    payload = load_payload(args.input)
    context_label = detect_context(args.context)
    sections = build_namespace_sections(payload)
    graph_data = build_connection_graph(payload, sections)
    svg = render_svg(sections, graph_data, context_label)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg, encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
