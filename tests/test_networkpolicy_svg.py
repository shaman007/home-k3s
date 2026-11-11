"""Keep the NetworkPolicy inventory's peer graph and XML escaping stable."""

import importlib.util
from pathlib import Path
import unittest

from defusedxml import ElementTree

SPEC = importlib.util.spec_from_file_location(
    "network_svg",
    Path(__file__).resolve().parents[1] / "tools/networkpolicy/render_networkpolicies_svg.py",
)
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)


def policy(namespace, ingress=None, egress=None):
    """Build a small synthetic policy containing both traffic directions."""
    return {
        "metadata": {"name": "fixture<&", "namespace": namespace},
        "spec": {
            "policyTypes": ["Ingress", "Egress"],
            "ingress": ingress or [],
            "egress": egress or [],
        },
    }


class NetworkPolicySvgTests(unittest.TestCase):
    """Verify graph aggregation and valid escaped SVG without accessing Kubernetes."""

    def test_shared_edges_and_hidden_self_links(self):
        """Ingress and egress observations aggregate while same-namespace peers stay hidden."""
        to_other = {"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "other"}}}
        from_source = {
            "namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "source"}}
        }
        payload = {
            "items": [
                policy(
                    "source",
                    egress=[
                        {
                            "to": [
                                to_other,
                                to_other,
                                {"podSelector": {"matchLabels": {"app": "local"}}},
                            ]
                        }
                    ],
                ),
                policy("other", ingress=[{"from": [from_source]}]),
            ]
        }
        sections = renderer.build_namespace_sections(payload)
        graph = renderer.build_connection_graph(payload, sections)
        self.assertEqual(graph["hidden_self_edges"], 1)
        self.assertEqual(graph["visible_edge_count"], 1)
        edge = graph["edges"][0]
        self.assertEqual((edge["source"], edge["target"], edge["count"]), ("source", "other", 3))
        self.assertEqual(edge["via"], {"ingress", "egress"})
        svg = renderer.render_svg(sections, graph, "fixture<&")
        ElementTree.fromstring(svg)
        self.assertIn('class="edge both"', svg)
        self.assertIn('class="edge-count">3</text>', svg)
        self.assertIn("fixture&lt;&amp;", svg)

    def test_special_peers_and_referenced_namespaces(self):
        """Internet and unrestricted peers keep distinct special nodes."""
        payload = {
            "items": [
                policy(
                    "source",
                    egress=[
                        {
                            "to": [
                                {},
                                {"ipBlock": {"cidr": "::/0"}},
                                {
                                    "namespaceSelector": {
                                        "matchLabels": {"kubernetes.io/metadata.name": "external"}
                                    }
                                },
                            ]
                        }
                    ],
                )
            ]
        }
        graph = renderer.build_connection_graph(payload, renderer.build_namespace_sections(payload))
        keys = {node["key"] for node in graph["right_nodes"]}
        self.assertTrue({"special:internet", "special:all-peers", "external"}.issubset(keys))
        self.assertEqual(graph["out_counts"]["source"], 3)

    def test_empty_inventory_is_valid_svg(self):
        """An empty policy snapshot remains a complete renderable document."""
        graph = renderer.build_connection_graph({"items": []}, [])
        svg = renderer.render_svg([], graph, "fixture")
        root = ElementTree.fromstring(svg)
        self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
        self.assertGreater(int(root.attrib["height"]), 0)
        self.assertEqual(graph["visible_edge_count"], 0)
