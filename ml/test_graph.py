"""Unit tests for ml/graph.py (Step 9B.2 Graph Builder).

Covers all required test categories per Contract v1.2:
1. Node and edge types and required attributes (§6.1, §7.1).
2. Transfer versus merchant-profile edge semantics (§6.2).
3. Transfer-only aggregation (non-transfer edges excluded from monetary math).
4. Null/missing device behavior (zero fabricated device nodes/edges).
5. Deterministic graph and subgraph construction across line permutations.
6. Evidence-path connectivity, valid references, and size limits (max 10 edges, 25 nodes, 60 edges).
7. Empty-path behavior when no valid path exists (disconnected edge cases).
8. Causation disclaimer present.
"""

import copy
import unittest
from typing import Any, Dict, List

from ml.graph import (
    CAUSATION_DISCLAIMER,
    EDGE_TYPES,
    MAX_PATH_EDGES,
    MAX_SUBGRAPH_EDGES,
    MAX_SUBGRAPH_NODES,
    NODE_TYPES,
    HeterogeneousGraph,
    aggregate_transfer_metrics,
    build_graph_from_transactions,
    extract_evidence_subgraph,
    find_evidence_path,
    validate_evidence_path,
)


class TestGraphBuilder(unittest.TestCase):
    """Test suite for HeterogeneousGraph and evidence subgraph extraction."""

    def test_node_and_edge_types_and_attributes(self):
        """Graph supports account, device, merchant, complaint nodes and transfer, uses_device, merchant_profile, has_complaint edges."""
        self.assertEqual(NODE_TYPES, {"account", "device", "merchant", "complaint"})
        self.assertEqual(EDGE_TYPES, {"transfer", "uses_device", "merchant_profile", "has_complaint"})

        txns = [
            {
                "txn_id": "T000001",
                "timestamp": "2026-10-01T10:00:00Z",
                "sender_account": "ACC_0001",
                "receiver_account": "ACC_0002",
                "sender_device_id": "DEV_0001",
                "merchant_id": "MER_0001",
                "merchant_category": "ELECTRONICS",
                "amount_inr": 2500.0,
                "status": "SUCCESS",
                "complaint": {
                    "complaint_id": "CMP_0001",
                    "filed_at": "2026-10-01T10:15:00Z",
                    "category": "PHISHING_SCAM",
                },
            }
        ]
        scores = {"ACC_0001": 0.12, "ACC_0002": 0.88}
        g = build_graph_from_transactions(txns, scores)

        # Check nodes
        nodes = g.nodes
        self.assertIn("ACC_0001", nodes)
        self.assertIn("ACC_0002", nodes)
        self.assertIn("DEV_0001", nodes)
        self.assertIn("MER_0001", nodes)
        self.assertIn("CMP_0001", nodes)

        # Account node attributes
        acc1 = nodes["ACC_0001"]
        self.assertEqual(acc1["type"], "account")
        self.assertEqual(acc1["label"], "ACC_0001")
        self.assertEqual(acc1["score"], 0.12)
        self.assertFalse(acc1["metadata"]["is_merchant"])

        acc2 = nodes["ACC_0002"]
        self.assertEqual(acc2["type"], "account")
        self.assertEqual(acc2["score"], 0.88)
        self.assertTrue(acc2["metadata"]["is_merchant"])
        self.assertEqual(acc2["metadata"]["merchant_id"], "MER_0001")

        # Device node attributes
        dev = nodes["DEV_0001"]
        self.assertEqual(dev["type"], "device")
        self.assertIsNone(dev["score"])

        # Merchant node attributes
        mer = nodes["MER_0001"]
        self.assertEqual(mer["type"], "merchant")
        self.assertIsNone(mer["score"])
        self.assertEqual(mer["metadata"]["category"], "ELECTRONICS")

        # Complaint node attributes
        cmp_node = nodes["CMP_0001"]
        self.assertEqual(cmp_node["type"], "complaint")
        self.assertIsNone(cmp_node["score"])
        self.assertEqual(cmp_node["metadata"]["category"], "PHISHING_SCAM")
        self.assertEqual(cmp_node["metadata"]["filed_at"], "2026-10-01T10:15:00Z")

        # Check edges
        edge_types = {e["type"] for e in g.edges}
        self.assertEqual(edge_types, {"transfer", "uses_device", "merchant_profile", "has_complaint"})

    def test_transfer_vs_merchant_profile_semantics(self):
        """Transfer edges retain financial data; merchant_profile edges connect receiver to merchant with null financial data."""
        txns = [
            {
                "txn_id": "T000001",
                "timestamp": "2026-10-01T10:00:00Z",
                "sender_account": "ACC_0001",
                "receiver_account": "ACC_0002",
                "merchant_id": "MER_0001",
                "merchant_category": "GENERAL_RETAIL",
                "amount_inr": 4999.0,
                "status": "SUCCESS",
            }
        ]
        g = build_graph_from_transactions(txns)

        transfer_edges = [e for e in g.edges if e["type"] == "transfer"]
        merchant_edges = [e for e in g.edges if e["type"] == "merchant_profile"]

        self.assertEqual(len(transfer_edges), 1)
        self.assertEqual(len(merchant_edges), 1)

        t_edge = transfer_edges[0]
        self.assertEqual(t_edge["source"], "ACC_0001")
        self.assertEqual(t_edge["target"], "ACC_0002")
        self.assertEqual(t_edge["txn_id"], "T000001")
        self.assertEqual(t_edge["amount_inr"], 4999.0)
        self.assertEqual(t_edge["timestamp"], "2026-10-01T10:00:00Z")

        m_edge = merchant_edges[0]
        self.assertEqual(m_edge["source"], "ACC_0002")
        self.assertEqual(m_edge["target"], "MER_0001")
        self.assertIsNone(m_edge["txn_id"])
        self.assertIsNone(m_edge["amount_inr"])
        self.assertIsNone(m_edge["timestamp"])

    def test_transfer_only_aggregation(self):
        """Only transfer edges participate in transaction/amount aggregation (§6.2)."""
        txns = [
            {
                "txn_id": "T000001",
                "timestamp": "2026-10-01T10:00:00Z",
                "sender_account": "ACC_0001",
                "receiver_account": "ACC_0002",
                "sender_device_id": "DEV_0001",
                "merchant_id": "MER_0001",
                "amount_inr": 1000.0,
                "status": "SUCCESS",
                "complaint_filed": True,
            },
            {
                "txn_id": "T000002",
                "timestamp": "2026-10-01T11:00:00Z",
                "sender_account": "ACC_0002",
                "receiver_account": "ACC_0003",
                "amount_inr": 400.0,
                "status": "SUCCESS",
            },
        ]
        g = build_graph_from_transactions(txns)

        # ACC_0002 received 1000.0, sent 400.0. Total transfers: 2.
        # Structural edges (merchant_profile, has_complaint) must not inflate counts or amounts.
        metrics = aggregate_transfer_metrics(g.edges, "ACC_0002")
        self.assertEqual(metrics["txn_count_sent"], 1)
        self.assertEqual(metrics["txn_count_received"], 1)
        self.assertEqual(metrics["txn_count_total"], 2)
        self.assertEqual(metrics["amount_sent_total"], 400.0)
        self.assertEqual(metrics["amount_received_total"], 1000.0)
        self.assertEqual(metrics["net_flow_amount"], 600.0)

    def test_null_and_missing_device_behavior(self):
        """Missing or null device IDs must not create fabricated device nodes or edges (§5.2)."""
        txns = [
            # Txn 1: sender_device_id is None
            {
                "txn_id": "T000001",
                "timestamp": "2026-10-01T10:00:00Z",
                "sender_account": "ACC_0001",
                "receiver_account": "ACC_0002",
                "sender_device_id": None,
                "amount_inr": 500.0,
                "status": "SUCCESS",
            },
            # Txn 2: sender_device_id omitted
            {
                "txn_id": "T000002",
                "timestamp": "2026-10-01T11:00:00Z",
                "sender_account": "ACC_0002",
                "receiver_account": "ACC_0003",
                "amount_inr": 750.0,
                "status": "SUCCESS",
            },
        ]
        g = build_graph_from_transactions(txns)

        device_nodes = [n for n in g.nodes.values() if n["type"] == "device"]
        device_edges = [e for e in g.edges if e["type"] == "uses_device"]

        self.assertEqual(len(device_nodes), 0)
        self.assertEqual(len(device_edges), 0)

    def test_deterministic_graph_construction(self):
        """Identical transactions produce identical graph serialization regardless of input order."""
        txns1 = [
            {
                "txn_id": "T000001",
                "timestamp": "2026-10-01T10:00:00Z",
                "sender_account": "ACC_0001",
                "receiver_account": "ACC_0002",
                "sender_device_id": "DEV_0001",
                "amount_inr": 100.0,
                "status": "SUCCESS",
            },
            {
                "txn_id": "T000002",
                "timestamp": "2026-10-01T11:00:00Z",
                "sender_account": "ACC_0002",
                "receiver_account": "ACC_0003",
                "amount_inr": 200.0,
                "status": "SUCCESS",
            },
        ]
        # Reversed input
        txns2 = [copy.deepcopy(txns1[1]), copy.deepcopy(txns1[0])]

        g1 = build_graph_from_transactions(txns1)
        g2 = build_graph_from_transactions(txns2)

        self.assertEqual(g1.to_dict(), g2.to_dict())

    def test_evidence_subgraph_connectivity_and_limits(self):
        """Evidence subgraph respects 25 nodes, 60 edges, and evidence path is contiguous walk <= 10 edges."""
        # Create a chain of transactions: ACC_0000 -> ACC_0001 -> ACC_0002 -> ... -> ACC_0030
        txns = []
        for i in range(30):
            txns.append({
                "txn_id": f"T{i+1:06d}",
                "timestamp": f"2026-10-01T10:{i:02d}:00Z",
                "sender_account": f"ACC_{i:04d}",
                "receiver_account": f"ACC_{i+1:04d}",
                "amount_inr": float(100 + i * 10),
                "status": "SUCCESS",
            })

        g = build_graph_from_transactions(txns)
        subgraph = extract_evidence_subgraph(g, "ACC_0010")

        # Hard limits check (§6.0, §7.2)
        self.assertLessEqual(len(subgraph["nodes"]), MAX_SUBGRAPH_NODES)
        self.assertLessEqual(len(subgraph["edges"]), MAX_SUBGRAPH_EDGES)
        self.assertLessEqual(len(subgraph["evidence_path"]), MAX_PATH_EDGES)

        # Center node must be first in nodes list
        self.assertEqual(subgraph["nodes"][0]["id"], "ACC_0010")

        # Path validation
        path = subgraph["evidence_path"]
        self.assertTrue(len(path) > 0)
        self.assertTrue(validate_evidence_path(path, subgraph["edges"], "ACC_0010"))

    def test_empty_evidence_path_when_disconnected(self):
        """Disconnected or isolated alert accounts cleanly return an empty evidence path []."""
        # Standalone account with no edges
        g = HeterogeneousGraph()
        g.add_node("ACC_9999", "account", "ACC_9999", score=0.95)

        subgraph = extract_evidence_subgraph(g, "ACC_9999")
        self.assertEqual(len(subgraph["nodes"]), 1)
        self.assertEqual(len(subgraph["edges"]), 0)
        self.assertEqual(subgraph["evidence_path"], [])

    def test_causation_disclaimer_constant(self):
        """CAUSATION_DISCLAIMER exists and specifies non-proof of causation (§7.2)."""
        self.assertIn("conspiratorial causation", CAUSATION_DISCLAIMER)
        self.assertIn("do not constitute legal proof", CAUSATION_DISCLAIMER)

    def test_merchant_account_role_ordering_preserves_metadata(self):
        """Merchant receiver account preserves is_merchant=True and merchant_id even if it also acts as sender."""
        txns = [
            # Txn 1: ACC_0002 is sender (standard account)
            {
                "txn_id": "T000001",
                "timestamp": "2026-10-01T10:00:00Z",
                "sender_account": "ACC_0002",
                "receiver_account": "ACC_0003",
                "amount_inr": 500.0,
                "status": "SUCCESS",
            },
            # Txn 2: ACC_0002 is receiver with merchant settlement
            {
                "txn_id": "T000002",
                "timestamp": "2026-10-01T11:00:00Z",
                "sender_account": "ACC_0001",
                "receiver_account": "ACC_0002",
                "merchant_id": "MER_0042",
                "merchant_category": "JEWELRY",
                "amount_inr": 15000.0,
                "status": "SUCCESS",
            },
        ]
        g1 = build_graph_from_transactions(txns)
        acc_node1 = g1.nodes["ACC_0002"]
        self.assertTrue(acc_node1["metadata"]["is_merchant"])
        self.assertEqual(acc_node1["metadata"]["merchant_id"], "MER_0042")

        # Reversed order: receiver txn first, then sender txn
        txns_rev = [copy.deepcopy(txns[1]), copy.deepcopy(txns[0])]
        g2 = build_graph_from_transactions(txns_rev)
        acc_node2 = g2.nodes["ACC_0002"]
        self.assertTrue(acc_node2["metadata"]["is_merchant"])
        self.assertEqual(acc_node2["metadata"]["merchant_id"], "MER_0042")

    def test_has_complaint_edge_schema_and_attributes(self):
        """Complaint node and has_complaint edge strictly follow Contract §6.1, §6.2, §7.1."""
        txns = [
            {
                "txn_id": "T000001",
                "timestamp": "2026-10-01T10:00:00Z",
                "sender_account": "ACC_0001",
                "receiver_account": "ACC_0002",
                "amount_inr": 2000.0,
                "status": "SUCCESS",
                "complaint": {
                    "complaint_id": "CMP_0099",
                    "filed_at": "2026-10-01T10:45:00Z",
                    "category": "UNAUTHORIZED_TRANSACTION",
                },
            }
        ]
        g = build_graph_from_transactions(txns)

        # Complaint node checks
        self.assertIn("CMP_0099", g.nodes)
        c_node = g.nodes["CMP_0099"]
        self.assertEqual(c_node["type"], "complaint")
        self.assertEqual(c_node["label"], "CMP_0099")
        self.assertIsNone(c_node["score"])
        self.assertEqual(c_node["metadata"]["category"], "UNAUTHORIZED_TRANSACTION")
        self.assertEqual(c_node["metadata"]["filed_at"], "2026-10-01T10:45:00Z")

        # has_complaint edge checks
        c_edges = [e for e in g.edges if e["type"] == "has_complaint"]
        self.assertEqual(len(c_edges), 1)
        ce = c_edges[0]
        self.assertEqual(ce["source"], "ACC_0002")  # Connected to receiver account
        self.assertEqual(ce["target"], "CMP_0099")
        self.assertEqual(ce["type"], "has_complaint")
        self.assertIsNone(ce["amount_inr"])  # Must be None (non-monetary)
        self.assertEqual(ce["timestamp"], "2026-10-01T10:45:00Z")  # t_filed


if __name__ == "__main__":
    unittest.main()
