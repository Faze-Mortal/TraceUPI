"""TraceUPI Heterogeneous Temporal Graph Builder.

Constructs deterministic heterogeneous graphs and alert-centric evidence subgraphs
strictly adhering to TraceUPI Interface Contract v1.2:
  - Node types: account, device, merchant, complaint (§6.1).
  - Edge types: transfer, uses_device, merchant_profile, has_complaint (§6.0, §6.2).
  - Transfer edges retain txn_id, amount_inr, and timestamp.
  - Merchant-profile edges link receiver account to its merchant (carry no amount, timestamp, or txn_id).
  - Only transfer edges participate in transaction/amount aggregation (§6.2).
  - Unobserved devices (null or omitted) create no device nodes or edges (§5.2).
  - Evidence subgraphs capped at 25 nodes and 60 edges (§6.0, §7.2).
  - Evidence paths are continuous walks (max 10 edges) touching the alert account,
    or empty [] if no valid path exists (§7.2).
  - Explicit causation disclaimer included (§7.2).
  - Standard library only; 100% deterministic outputs across runs.
"""

from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Set, Tuple

from ml.features import is_complaint_active

# Contract v1.2 hard limits and schema constants (§6.0, §7.2)
MAX_SUBGRAPH_NODES = 25
MAX_SUBGRAPH_EDGES = 60
MAX_PATH_EDGES = 10

NODE_TYPES = {"account", "device", "merchant", "complaint"}
EDGE_TYPES = {"transfer", "uses_device", "merchant_profile", "has_complaint"}

CAUSATION_DISCLAIMER = (
    "Evidence paths illustrate graph connectivity, transfer flow, and shared infrastructure. "
    "They do not constitute legal proof of conspiratorial causation."
)


class HeterogeneousGraph:
    """Heterogeneous directed graph representation for TraceUPI investigations."""

    def __init__(self) -> None:
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: List[Dict[str, Any]] = []
        # Adjacency maps for fast neighborhood exploration (node_id -> list of edge dicts)
        self._adj: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._out_edges: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._in_edges: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    def add_node(
        self,
        node_id: str,
        node_type: str,
        label: Optional[str] = None,
        score: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add or update a node in the graph."""
        if node_type not in NODE_TYPES:
            raise ValueError(f"Invalid node_type '{node_type}'. Allowed: {sorted(NODE_TYPES)}")

        if label is None:
            label = node_id

        if metadata is None:
            metadata = {}

        # If node already exists, update attributes without overwriting valid data
        if node_id in self.nodes:
            existing = self.nodes[node_id]
            if score is not None:
                existing["score"] = score
            if metadata:
                for k, v in metadata.items():
                    if k == "is_merchant":
                        existing["metadata"]["is_merchant"] = bool(existing["metadata"].get("is_merchant") or v)
                    elif k == "merchant_id":
                        if v is not None:
                            existing["metadata"]["merchant_id"] = v
                    else:
                        if v is not None or k not in existing["metadata"]:
                            existing["metadata"][k] = v
        else:
            self.nodes[node_id] = {
                "id": node_id,
                "type": node_type,
                "label": label,
                "score": score,
                "metadata": dict(metadata),
            }

    def add_edge(
        self,
        edge_id: str,
        source: str,
        target: str,
        edge_type: str,
        txn_id: Optional[str] = None,
        amount_inr: Optional[float] = None,
        timestamp: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add an edge to the graph."""
        if edge_type not in EDGE_TYPES:
            raise ValueError(f"Invalid edge_type '{edge_type}'. Allowed: {sorted(EDGE_TYPES)}")

        if source not in self.nodes:
            raise KeyError(f"Source node '{source}' does not exist in graph")
        if target not in self.nodes:
            raise KeyError(f"Target node '{target}' does not exist in graph")

        # Contract §6.2: Structural edges carry null amount, timestamp, and txn_id where specified
        if edge_type == "merchant_profile":
            amount_inr = None
            timestamp = None
            txn_id = None
        elif edge_type == "uses_device":
            amount_inr = None
            timestamp = None
            txn_id = None
        elif edge_type == "has_complaint":
            amount_inr = None

        edge = {
            "id": edge_id,
            "source": source,
            "target": target,
            "type": edge_type,
            "txn_id": txn_id,
            "amount_inr": amount_inr,
            "timestamp": timestamp,
        }
        self.edges.append(edge)
        self._adj[source].append(edge)
        self._adj[target].append(edge)
        self._out_edges[source].append(edge)
        self._in_edges[target].append(edge)
        return edge

    def to_dict(self) -> Dict[str, Any]:
        """Serialize complete graph matching Contract v1.2 schema."""
        return {
            "nodes": [self.nodes[nid] for nid in sorted(self.nodes.keys())],
            "edges": list(self.edges),
        }


def build_graph_from_transactions(
    transactions: List[Dict[str, Any]],
    account_scores: Optional[Dict[str, float]] = None,
) -> HeterogeneousGraph:
    """Construct a full HeterogeneousGraph from raw transaction records.

    Args:
        transactions: List of transaction dictionaries matching Contract v1.2.
        account_scores: Optional mapping of account_id -> ML score.

    Returns:
        Deterministic HeterogeneousGraph populated with accounts, devices, merchants,
        complaints, transfers, and structural edges.
    """
    if account_scores is None:
        account_scores = {}

    g = HeterogeneousGraph()
    if not transactions:
        return g

    # 1. Collect and register accounts, merchants, devices, and complaints
    # Track unique structural relationships to prevent duplicate structural edges
    observed_device_links: Set[Tuple[str, str]] = set()  # (sender, device)
    observed_merchant_links: Set[Tuple[str, str]] = set()  # (receiver, merchant)
    observed_complaint_links: Set[Tuple[str, str]] = set()  # (receiver, complaint_id)

    # First pass: create all nodes
    for txn in transactions:
        sender = txn["sender_account"]
        receiver = txn["receiver_account"]

        s_score = account_scores.get(sender)
        r_score = account_scores.get(receiver)

        # Sender account node
        g.add_node(
            node_id=sender,
            node_type="account",
            label=sender,
            score=round(s_score, 4) if s_score is not None else None,
            metadata={"is_merchant": False, "merchant_id": None},
        )

        # Receiver account node
        mer_id = txn.get("merchant_id")
        g.add_node(
            node_id=receiver,
            node_type="account",
            label=receiver,
            score=round(r_score, 4) if r_score is not None else None,
            metadata={
                "is_merchant": bool(mer_id),
                "merchant_id": mer_id,
            },
        )

        # Device node (sender-side only; unobserved/null devices create NO node per §5.2)
        dev_id = txn.get("sender_device_id")
        if dev_id is not None:
            g.add_node(
                node_id=dev_id,
                node_type="device",
                label=dev_id,
                score=None,
                metadata={},
            )
            observed_device_links.add((sender, dev_id))

        # Merchant entity node (§6.1, §6.2)
        if mer_id is not None:
            g.add_node(
                node_id=mer_id,
                node_type="merchant",
                label=mer_id,
                score=None,
                metadata={"category": txn.get("merchant_category")},
            )
            observed_merchant_links.add((receiver, mer_id))

        # Complaint node (§2.4, §6.1)
        if is_complaint_active(txn):
            c_obj = txn.get("complaint")
            if c_obj is not None:
                cid = c_obj["complaint_id"]
                filed_at = c_obj["filed_at"]
                cat = c_obj.get("category", "UNSPECIFIED")
            else:
                cid = "CMP_" + txn["txn_id"][1:]
                filed_at = txn["timestamp"]
                cat = "UNSPECIFIED"

            g.add_node(
                node_id=cid,
                node_type="complaint",
                label=cid,
                score=None,
                metadata={"category": cat, "filed_at": filed_at},
            )
            observed_complaint_links.add((receiver, cid))

    # Second pass: assemble edges deterministically with sequential E-ids
    # Sort candidate edges by canonical keys before assigning IDs:
    # 1. Transfer edges: sorted by timestamp asc, txn_id asc
    transfer_candidates: List[Dict[str, Any]] = []
    for txn in transactions:
        transfer_candidates.append({
            "source": txn["sender_account"],
            "target": txn["receiver_account"],
            "type": "transfer",
            "txn_id": txn["txn_id"],
            "amount_inr": float(txn["amount_inr"]),
            "timestamp": txn["timestamp"],
        })
    transfer_candidates.sort(key=lambda x: (x["timestamp"], x["txn_id"]))

    # 2. Structural uses_device edges: sorted by sender asc, dev_id asc
    device_candidates = [
        {
            "source": s,
            "target": d,
            "type": "uses_device",
            "txn_id": None,
            "amount_inr": None,
            "timestamp": None,
        }
        for s, d in sorted(observed_device_links)
    ]

    # 3. Structural merchant_profile edges: sorted by receiver asc, mer_id asc
    merchant_candidates = [
        {
            "source": r,
            "target": m,
            "type": "merchant_profile",
            "txn_id": None,
            "amount_inr": None,
            "timestamp": None,
        }
        for r, m in sorted(observed_merchant_links)
    ]

    # 4. Structural has_complaint edges: sorted by receiver asc, cid asc
    complaint_candidates: List[Dict[str, Any]] = []
    for r, cid in sorted(observed_complaint_links):
        # Look up filing time from complaint node metadata
        c_node = g.nodes.get(cid)
        c_filed = c_node["metadata"].get("filed_at") if c_node else None
        complaint_candidates.append({
            "source": r,
            "target": cid,
            "type": "has_complaint",
            "txn_id": None,
            "amount_inr": None,
            "timestamp": c_filed,
        })

    # Combine in deterministic order and assign edge IDs E1, E2, ...
    all_candidates = (
        transfer_candidates
        + device_candidates
        + merchant_candidates
        + complaint_candidates
    )

    for idx, c in enumerate(all_candidates, 1):
        g.add_edge(
            edge_id=f"E{idx}",
            source=c["source"],
            target=c["target"],
            edge_type=c["type"],
            txn_id=c["txn_id"],
            amount_inr=c["amount_inr"],
            timestamp=c["timestamp"],
        )

    return g


def aggregate_transfer_metrics(
    edges: List[Dict[str, Any]],
    account_id: str,
) -> Dict[str, Any]:
    """Calculate financial aggregates strictly over transfer edges per Contract §6.2.

    Structural edges (uses_device, merchant_profile, has_complaint) carry no transfer
    amounts and must NEVER contribute to financial sums or transaction counts.

    Args:
        edges: List of edge dictionaries.
        account_id: Target account to aggregate.

    Returns:
        Dictionary with sent/received transfer counts and amounts.
    """
    count_sent = 0
    count_received = 0
    amount_sent = 0.0
    amount_received = 0.0

    for e in edges:
        # Strictly ignore non-transfer edges
        if e.get("type") != "transfer":
            continue

        amt = float(e.get("amount_inr") or 0.0)
        if e.get("source") == account_id:
            count_sent += 1
            amount_sent += amt
        if e.get("target") == account_id:
            count_received += 1
            amount_received += amt

    return {
        "txn_count_sent": count_sent,
        "txn_count_received": count_received,
        "txn_count_total": count_sent + count_received,
        "amount_sent_total": round(amount_sent, 4),
        "amount_received_total": round(amount_received, 4),
        "net_flow_amount": round(amount_received - amount_sent, 4),
    }


def validate_evidence_path(
    path_edge_ids: List[str],
    edges: List[Dict[str, Any]],
    alert_account_id: str,
) -> bool:
    """Validate that an evidence path conforms strictly to Contract §7.2.

    Rules:
    1. 0 <= len(path_edge_ids) <= 10.
    2. An empty path [] is explicitly valid (disconnected edge cases).
    3. Every edge ID in the path must exist in the provided edges.
    4. At least one edge in the path must touch alert_account_id.
    5. Consecutive edges in the path must share at least one node (connected walk).
    """
    if not path_edge_ids:
        return True

    if len(path_edge_ids) > MAX_PATH_EDGES:
        return False

    edge_map = {e["id"]: e for e in edges}
    for eid in path_edge_ids:
        if eid not in edge_map:
            return False

    # Rule 4: At least one edge touches alert_account_id
    touches_alert = any(
        edge_map[eid]["source"] == alert_account_id
        or edge_map[eid]["target"] == alert_account_id
        for eid in path_edge_ids
    )
    if not touches_alert:
        return False

    # Rule 5: Consecutive edges share at least one node
    for i in range(len(path_edge_ids) - 1):
        e1 = edge_map[path_edge_ids[i]]
        e2 = edge_map[path_edge_ids[i + 1]]
        nodes1 = {e1["source"], e1["target"]}
        nodes2 = {e2["source"], e2["target"]}
        if not (nodes1 & nodes2):
            return False

    return True


def find_evidence_path(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    alert_account_id: str,
    max_path_edges: int = MAX_PATH_EDGES,
) -> List[str]:
    """Find a contiguous, explainable evidence walk for an alert account per Contract §7.2.

    Prioritizes:
    1. Multi-hop transfer pass-through walks (e.g. Inflow -> Alert -> Outflow).
    2. Cash-out walks to commercial merchants (e.g. Inflow -> Alert -> Merchant).
    3. Inflow walks associated with victim complaints (e.g. Inflow -> Alert -> Complaint).
    4. Significant transfer edges directly touching the alert account.
    Returns empty list [] if no valid connected path exists.
    """
    if not nodes or not edges or not alert_account_id:
        return []

    # Map node existence and edges
    edge_map = {e["id"]: e for e in edges}
    adj: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for e in edges:
        adj[e["source"]].append(e)
        adj[e["target"]].append(e)

    alert_edges = adj.get(alert_account_id, [])
    if not alert_edges:
        return []

    incoming_transfers = [
        e for e in alert_edges
        if e["type"] == "transfer" and e["target"] == alert_account_id
    ]
    outgoing_transfers = [
        e for e in alert_edges
        if e["type"] == "transfer" and e["source"] == alert_account_id
    ]
    merchant_edges = [
        e for e in alert_edges
        if e["type"] == "merchant_profile"
    ]
    complaint_edges = [
        e for e in alert_edges
        if e["type"] == "has_complaint"
    ]

    # Sort transfer candidates by amount_inr descending for highest investigative relevance
    incoming_transfers.sort(key=lambda e: float(e.get("amount_inr") or 0.0), reverse=True)
    outgoing_transfers.sort(key=lambda e: float(e.get("amount_inr") or 0.0), reverse=True)

    # Strategy 1: Pass-through walk (Incoming transfer -> Alert Account -> Outgoing transfer)
    if incoming_transfers and outgoing_transfers:
        in_e = incoming_transfers[0]
        out_e = outgoing_transfers[0]
        candidate_path = [in_e["id"], out_e["id"]]

        # Check if the recipient of out_e has an onward transfer or merchant link
        next_node = out_e["target"]
        next_edges = [
            e for e in adj.get(next_node, [])
            if e["id"] not in candidate_path
        ]
        next_merchants = [e for e in next_edges if e["type"] == "merchant_profile"]
        next_transfers = [
            e for e in next_edges
            if e["type"] == "transfer" and e["source"] == next_node
        ]
        next_transfers.sort(key=lambda e: float(e.get("amount_inr") or 0.0), reverse=True)

        if next_merchants:
            candidate_path.append(next_merchants[0]["id"])
        elif next_transfers:
            candidate_path.append(next_transfers[0]["id"])

        if validate_evidence_path(candidate_path, edges, alert_account_id):
            return candidate_path[:max_path_edges]

    # Strategy 2: Liquidation walk to Merchant (Incoming transfer -> Alert Account -> Merchant)
    if incoming_transfers and merchant_edges:
        candidate_path = [incoming_transfers[0]["id"], merchant_edges[0]["id"]]
        if validate_evidence_path(candidate_path, edges, alert_account_id):
            return candidate_path[:max_path_edges]

    # Strategy 3: Disputed Inflow with Complaint (Incoming transfer -> Alert Account -> Complaint)
    if incoming_transfers and complaint_edges:
        candidate_path = [incoming_transfers[0]["id"], complaint_edges[0]["id"]]
        if validate_evidence_path(candidate_path, edges, alert_account_id):
            return candidate_path[:max_path_edges]

    # Strategy 4: Outgoing transfer + Device link or onward transfer
    if outgoing_transfers:
        out_e = outgoing_transfers[0]
        candidate_path = [out_e["id"]]
        next_node = out_e["target"]
        next_transfers = [
            e for e in adj.get(next_node, [])
            if e["type"] == "transfer" and e["source"] == next_node and e["id"] != out_e["id"]
        ]
        if next_transfers:
            next_transfers.sort(key=lambda e: float(e.get("amount_inr") or 0.0), reverse=True)
            candidate_path.append(next_transfers[0]["id"])

        if validate_evidence_path(candidate_path, edges, alert_account_id):
            return candidate_path[:max_path_edges]

    # Strategy 5: Single primary transfer touching the alert account
    if incoming_transfers:
        candidate_path = [incoming_transfers[0]["id"]]
        if validate_evidence_path(candidate_path, edges, alert_account_id):
            return candidate_path[:max_path_edges]

    # Fallback: Disconnected edge case (§7.2 Rule 2) -> empty path
    return []


def extract_evidence_subgraph(
    graph: HeterogeneousGraph,
    alert_account_id: str,
    max_nodes: int = MAX_SUBGRAPH_NODES,
    max_edges: int = MAX_SUBGRAPH_EDGES,
) -> Dict[str, Any]:
    """Extract a localized 2-hop evidence subgraph centered on an alert account.

    Strictly complies with Contract v1.2 §6.0, §6.1, §7.1, and §7.2:
      - Centers on alert_account_id.
      - Expands up to 2 hops across any edge type.
      - Caps deterministically at max_nodes (25) and max_edges (60).
      - Computes contiguous evidence_path (max 10 edges) touching alert_account_id.
      - Guarantees 100% deterministic output.

    Args:
        graph: Full HeterogeneousGraph.
        alert_account_id: ID of the alert's primary account.
        max_nodes: Maximum nodes in subgraph (default 25).
        max_edges: Maximum edges in subgraph (default 60).

    Returns:
        Dict matching Contract Section 7.1 "evidence":
        {"nodes": [...], "edges": [...], "evidence_path": [...]}
    """
    if alert_account_id not in graph.nodes:
        return {"nodes": [], "edges": [], "evidence_path": []}

    # 1. 2-Hop BFS to discover candidate nodes
    selected_nodes: Set[str] = {alert_account_id}
    hop_map: Dict[str, int] = {alert_account_id: 0}

    queue: deque = deque([(alert_account_id, 0)])
    while queue:
        curr, depth = queue.popleft()
        if depth >= 2:
            continue

        for edge in graph._adj.get(curr, []):
            nbr = edge["target"] if edge["source"] == curr else edge["source"]
            if nbr not in hop_map:
                hop_map[nbr] = depth + 1
                queue.append((nbr, depth + 1))

    # 2. Deterministic node ranking & selection (cap at max_nodes)
    def node_priority(nid: str) -> Tuple[int, int, float, str]:
        # Priority order:
        # 1. Hop distance (0 first, then 1, then 2)
        # 2. Node type priority: account > complaint > merchant > device
        # 3. ML score (descending; None treated as -1.0)
        # 4. Node ID (ascending tie-breaker)
        depth = hop_map.get(nid, 99)
        ntype = graph.nodes[nid]["type"]
        type_rank = {"account": 0, "complaint": 1, "merchant": 2, "device": 3}.get(ntype, 4)
        score = graph.nodes[nid].get("score")
        score_val = -float(score) if score is not None else 1.0
        return (depth, type_rank, score_val, nid)

    all_candidates = sorted(hop_map.keys(), key=node_priority)
    chosen_node_ids = set(all_candidates[:max_nodes])

    # 3. Collect edges between chosen nodes
    candidate_edges: List[Dict[str, Any]] = []
    seen_edge_ids: Set[str] = set()

    for nid in chosen_node_ids:
        for edge in graph._adj.get(nid, []):
            eid = edge["id"]
            if eid not in seen_edge_ids:
                if edge["source"] in chosen_node_ids and edge["target"] in chosen_node_ids:
                    seen_edge_ids.add(eid)
                    candidate_edges.append(edge)

    # 4. Deterministic edge ranking & capping (cap at max_edges)
    def edge_priority(e: Dict[str, Any]) -> Tuple[int, float, str]:
        # Priority:
        # 1. Edges directly touching alert_account_id (0 = direct, 1 = distant)
        # 2. Transfer amount descending (None treated as 0.0)
        # 3. Edge ID ascending tie-breaker
        is_direct = 0 if (e["source"] == alert_account_id or e["target"] == alert_account_id) else 1
        amt = -float(e.get("amount_inr") or 0.0)
        return (is_direct, amt, e["id"])

    candidate_edges.sort(key=edge_priority)
    chosen_edges = candidate_edges[:max_edges]

    # Re-sort edges by edge ID for canonical contract serialization
    chosen_edges.sort(key=lambda e: int(e["id"][1:]) if e["id"].startswith("E") and e["id"][1:].isdigit() else e["id"])

    # 5. Format nodes: alert_account_id first, then sorted by (type, id)
    formatted_nodes: List[Dict[str, Any]] = []
    other_node_ids = [nid for nid in chosen_node_ids if nid != alert_account_id]
    other_node_ids.sort(key=lambda nid: (graph.nodes[nid]["type"], nid))

    final_node_ids = [alert_account_id] + other_node_ids
    for nid in final_node_ids:
        n = graph.nodes[nid]
        formatted_nodes.append({
            "id": n["id"],
            "type": n["type"],
            "label": n["label"],
            "score": n["score"],
            "metadata": dict(n["metadata"]),
        })

    # 6. Compute evidence path touching alert_account_id
    path_ids = find_evidence_path(formatted_nodes, chosen_edges, alert_account_id)

    return {
        "nodes": formatted_nodes,
        "edges": chosen_edges,
        "evidence_path": path_ids,
    }
