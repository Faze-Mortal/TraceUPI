"""TraceUPI Synthetic Transaction Data Generator.

Generates reproducible, contract-compliant synthetic UPI transaction datasets
demonstrating mule networks, shared-device families, and normal transactions.
Strictly complies with TraceUPI Interface Contract v1.1.
"""

import argparse
import datetime
import json
import os
import random
import re
from pathlib import Path


def generate_synthetic_transactions(seed: int = 42, size: str = "expanded") -> list[dict]:
    """Generate synthetic transactions strictly conforming to TraceUPI Interface Contract v1.1.

    Args:
        seed: Random seed for deterministic generation (default: 42).
        size: "expanded" (~3,300 transactions across ~477 accounts) or
              "small" (280 transactions across 62 accounts).

    Returns:
        List of transaction dictionaries sorted by timestamp asc, then txn_id asc.
    """
    if size == "small":
        return _generate_small_dataset(seed=seed)
    elif size == "expanded":
        return _generate_expanded_dataset(seed=seed)
    else:
        raise ValueError(f"Unknown dataset size '{size}', expected 'small' or 'expanded'")


def _generate_small_dataset(seed: int = 42) -> list[dict]:
    """Original small dataset generator: 280 transactions across 62 accounts."""
    rng = random.Random(seed)

    transactions = []
    txn_counter = 1

    base_time = datetime.datetime(2026, 10, 1, 8, 0, 0, tzinfo=datetime.timezone.utc)
    current_time_offset_sec = 0

    def next_timestamp(min_gap_sec: int = 60, max_gap_sec: int = 900) -> str:
        nonlocal current_time_offset_sec
        current_time_offset_sec += rng.randint(min_gap_sec, max_gap_sec)
        dt = base_time + datetime.timedelta(seconds=current_time_offset_sec)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def format_txn_id(idx: int) -> str:
        return f"T{idx:06d}"

    def format_acc_id(num: int) -> str:
        return f"ACC_{num:04d}"

    def format_dev_id(num: int) -> str:
        return f"DEV_{num:04d}"

    # 1. Normal Scenario Accounts & Transactions (25 accounts)
    normal_accounts = [format_acc_id(i) for i in range(301, 326)]
    normal_devices = {acc: format_dev_id(300 + idx) for idx, acc in enumerate(normal_accounts, start=1)}

    for _ in range(120):
        sender = rng.choice(normal_accounts)
        receiver = rng.choice([acc for acc in normal_accounts if acc != sender])
        device = normal_devices[sender]
        amount = round(rng.uniform(50.0, 7500.0), 2)
        status = "SUCCESS" if rng.random() > 0.04 else "FAILED"
        complaint = False

        transactions.append({
            "txn_id": format_txn_id(txn_counter),
            "timestamp": next_timestamp(min_gap_sec=60, max_gap_sec=600),
            "sender_account": sender,
            "receiver_account": receiver,
            "sender_device_id": device,
            "amount_inr": amount,
            "status": status,
            "complaint_filed": complaint,
            "ground_truth": {
                "scenario": "normal",
                "ring_member_accounts": []
            }
        })
        txn_counter += 1

    # 2. Shared Device Family Scenario (12 accounts, 3 families)
    family_clusters = [
        ([format_acc_id(i) for i in range(201, 205)], format_dev_id(20)),
        ([format_acc_id(i) for i in range(205, 209)], format_dev_id(21)),
        ([format_acc_id(i) for i in range(209, 213)], format_dev_id(22)),
    ]

    all_family_members = []
    for members, _ in family_clusters:
        all_family_members.extend(members)

    for members, shared_dev in family_clusters:
        for _ in range(18):
            sender = rng.choice(members)
            receiver = rng.choice([m for m in members if m != sender])
            amount = round(rng.uniform(100.0, 3500.0), 2)
            status = "SUCCESS" if rng.random() > 0.02 else "FAILED"

            transactions.append({
                "txn_id": format_txn_id(txn_counter),
                "timestamp": next_timestamp(min_gap_sec=120, max_gap_sec=1800),
                "sender_account": sender,
                "receiver_account": receiver,
                "sender_device_id": shared_dev,
                "amount_inr": amount,
                "status": status,
                "complaint_filed": False,
                "ground_truth": {
                    "scenario": "shared_device_family",
                    "ring_member_accounts": []
                }
            })
            txn_counter += 1

        for _ in range(8):
            sender = rng.choice(members)
            other_cohort = [m for m in all_family_members if m not in members]
            receiver = rng.choice(other_cohort)
            amount = round(rng.uniform(200.0, 4500.0), 2)
            status = "SUCCESS"

            transactions.append({
                "txn_id": format_txn_id(txn_counter),
                "timestamp": next_timestamp(min_gap_sec=120, max_gap_sec=1400),
                "sender_account": sender,
                "receiver_account": receiver,
                "sender_device_id": shared_dev,
                "amount_inr": amount,
                "status": status,
                "complaint_filed": False,
                "ground_truth": {
                    "scenario": "shared_device_family",
                    "ring_member_accounts": []
                }
            })
            txn_counter += 1

    # 3. Mule Ring Scenario (15 accounts, 3 sub-rings)
    mule_devices = {format_acc_id(i): format_dev_id(100 + i) for i in range(101, 116)}
    victim_accounts = [format_acc_id(i) for i in range(901, 911)]
    victim_devices = {v: format_dev_id(900 + idx) for idx, v in enumerate(victim_accounts, start=1)}

    for _ in range(25):
        victim = rng.choice(victim_accounts)
        aggregator = rng.choice([format_acc_id(101), format_acc_id(102)])
        amount = round(rng.uniform(4900.0, 9999.0), 2)
        complaint = rng.random() < 0.40

        transactions.append({
            "txn_id": format_txn_id(txn_counter),
            "timestamp": next_timestamp(min_gap_sec=30, max_gap_sec=450),
            "sender_account": victim,
            "receiver_account": aggregator,
            "sender_device_id": victim_devices[victim],
            "amount_inr": amount,
            "status": "SUCCESS",
            "complaint_filed": complaint,
            "ground_truth": {
                "scenario": "mule_ring",
                "ring_member_accounts": [aggregator]
            }
        })
        txn_counter += 1

    layering_paths = [
        (format_acc_id(101), format_acc_id(103)),
        (format_acc_id(101), format_acc_id(104)),
        (format_acc_id(102), format_acc_id(104)),
        (format_acc_id(102), format_acc_id(105)),
        (format_acc_id(103), format_acc_id(106)),
        (format_acc_id(104), format_acc_id(106)),
        (format_acc_id(105), format_acc_id(106)),
    ]
    for _ in range(20):
        sender, receiver = rng.choice(layering_paths)
        amount = round(rng.uniform(15000.0, 45000.0), 2)
        transactions.append({
            "txn_id": format_txn_id(txn_counter),
            "timestamp": next_timestamp(min_gap_sec=15, max_gap_sec=200),
            "sender_account": sender,
            "receiver_account": receiver,
            "sender_device_id": mule_devices[sender],
            "amount_inr": amount,
            "status": "SUCCESS",
            "complaint_filed": False,
            "ground_truth": {
                "scenario": "mule_ring",
                "ring_member_accounts": [sender, receiver]
            }
        })
        txn_counter += 1

    cycle_pairs = [
        (format_acc_id(107), format_acc_id(108)),
        (format_acc_id(108), format_acc_id(109)),
        (format_acc_id(109), format_acc_id(110)),
        (format_acc_id(110), format_acc_id(107)),
    ]
    for _ in range(16):
        sender, receiver = rng.choice(cycle_pairs)
        amount = round(rng.uniform(12000.0, 28000.0), 2)
        transactions.append({
            "txn_id": format_txn_id(txn_counter),
            "timestamp": next_timestamp(min_gap_sec=20, max_gap_sec=300),
            "sender_account": sender,
            "receiver_account": receiver,
            "sender_device_id": mule_devices[sender],
            "amount_inr": amount,
            "status": "SUCCESS",
            "complaint_filed": False,
            "ground_truth": {
                "scenario": "mule_ring",
                "ring_member_accounts": [sender, receiver]
            }
        })
        txn_counter += 1

    distributor = format_acc_id(111)
    smurfs = [format_acc_id(i) for i in range(112, 116)]
    for _ in range(5):
        victim = rng.choice(victim_accounts)
        amount = round(rng.uniform(30000.0, 50000.0), 2)
        transactions.append({
            "txn_id": format_txn_id(txn_counter),
            "timestamp": next_timestamp(min_gap_sec=30, max_gap_sec=300),
            "sender_account": victim,
            "receiver_account": distributor,
            "sender_device_id": victim_devices[victim],
            "amount_inr": amount,
            "status": "SUCCESS",
            "complaint_filed": True,
            "ground_truth": {
                "scenario": "mule_ring",
                "ring_member_accounts": [distributor]
            }
        })
        txn_counter += 1

    for _ in range(16):
        smurf = rng.choice(smurfs)
        amount = round(rng.uniform(4900.0, 9999.0), 2)
        transactions.append({
            "txn_id": format_txn_id(txn_counter),
            "timestamp": next_timestamp(min_gap_sec=10, max_gap_sec=150),
            "sender_account": distributor,
            "receiver_account": smurf,
            "sender_device_id": mule_devices[distributor],
            "amount_inr": amount,
            "status": "SUCCESS",
            "complaint_filed": False,
            "ground_truth": {
                "scenario": "mule_ring",
                "ring_member_accounts": [distributor, smurf]
            }
        })
        txn_counter += 1

    transactions.sort(key=lambda t: (t["timestamp"], t["txn_id"]))
    return transactions


def _generate_expanded_dataset(seed: int = 42) -> list[dict]:
    """Expanded dataset generator: ~3,300 transactions across ~477 accounts.

    Includes diverse mule topologies, benign shared-device families, varied personal
    accounts, and challenging hard negatives (fest coordinators, merchants, multi-hop splits).
    """
    rng = random.Random(seed)

    transactions = []
    txn_counter = 1

    base_time = datetime.datetime(2026, 10, 1, 8, 0, 0, tzinfo=datetime.timezone.utc)
    current_time_offset_sec = 0

    def next_timestamp(min_gap_sec: int = 30, max_gap_sec: int = 300) -> str:
        nonlocal current_time_offset_sec
        current_time_offset_sec += rng.randint(min_gap_sec, max_gap_sec)
        dt = base_time + datetime.timedelta(seconds=current_time_offset_sec)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def format_txn_id(idx: int) -> str:
        return f"T{idx:06d}"

    def format_acc_id(num: int) -> str:
        return f"ACC_{num:04d}"

    def format_dev_id(num: int) -> str:
        return f"DEV_{num:04d}"

    # 1. NORMAL PERSONAL ACCOUNTS (ACC_0301 to ACC_0550 -> 250 accounts)
    normal_accounts = [format_acc_id(i) for i in range(301, 551)]
    normal_devices = {acc: format_dev_id(300 + idx) for idx, acc in enumerate(normal_accounts, start=1)}

    high_act = normal_accounts[:30]
    med_act = normal_accounts[30:150]
    low_act = normal_accounts[150:]

    for _ in range(1550):
        r_tier = rng.random()
        if r_tier < 0.50:
            sender = rng.choice(high_act)
        elif r_tier < 0.85:
            sender = rng.choice(med_act)
        else:
            sender = rng.choice(low_act)

        receiver = rng.choice([acc for acc in normal_accounts if acc != sender])
        device = normal_devices[sender]

        r_amt = rng.random()
        if r_amt < 0.65:
            amount = round(rng.uniform(25.0, 1500.0), 2)
        elif r_amt < 0.92:
            amount = round(rng.uniform(1500.0, 6500.0), 2)
        else:
            amount = round(rng.uniform(6500.0, 20000.0), 2)

        status = "SUCCESS" if rng.random() > 0.035 else "FAILED"
        complaint = (rng.random() < 0.003) if status == "SUCCESS" else False

        transactions.append({
            "txn_id": format_txn_id(txn_counter),
            "timestamp": next_timestamp(min_gap_sec=30, max_gap_sec=240),
            "sender_account": sender,
            "receiver_account": receiver,
            "sender_device_id": device,
            "amount_inr": amount,
            "status": status,
            "complaint_filed": complaint,
            "ground_truth": {
                "scenario": "normal",
                "ring_member_accounts": []
            }
        })
        txn_counter += 1

    # 2. HARD NEGATIVE LEGITIMATE ACCOUNTS (ACC_0601 to ACC_0635 -> 35 accounts)
    hard_neg_devices = {format_acc_id(i): format_dev_id(600 + idx) for idx, i in enumerate(range(601, 636), start=1)}

    # Sub-case 2A: College Fest / Event Coordinators (ACC_0601, ACC_0602)
    fest_coordinators = [format_acc_id(601), format_acc_id(602)]
    vendor_accounts = [format_acc_id(603), format_acc_id(604)]
    for _ in range(120):
        sender = rng.choice(normal_accounts)
        coordinator = rng.choice(fest_coordinators)
        amount = round(rng.uniform(250.0, 1500.0), 2)
        transactions.append({
            "txn_id": format_txn_id(txn_counter),
            "timestamp": next_timestamp(min_gap_sec=40, max_gap_sec=300),
            "sender_account": sender,
            "receiver_account": coordinator,
            "sender_device_id": normal_devices[sender],
            "amount_inr": amount,
            "status": "SUCCESS" if rng.random() > 0.02 else "FAILED",
            "complaint_filed": False,
            "ground_truth": {"scenario": "normal", "ring_member_accounts": []}
        })
        txn_counter += 1

    for _ in range(12):
        coord = rng.choice(fest_coordinators)
        vendor = rng.choice(vendor_accounts)
        amount = round(rng.uniform(15000.0, 35000.0), 2)
        transactions.append({
            "txn_id": format_txn_id(txn_counter),
            "timestamp": next_timestamp(min_gap_sec=300, max_gap_sec=1800),
            "sender_account": coord,
            "receiver_account": vendor,
            "sender_device_id": hard_neg_devices[coord],
            "amount_inr": amount,
            "status": "SUCCESS",
            "complaint_filed": False,
            "ground_truth": {"scenario": "normal", "ring_member_accounts": []}
        })
        txn_counter += 1

    # Sub-case 2B: Campus Canteen / Small Merchants (ACC_0605, ACC_0606, ACC_0607)
    merchants = [format_acc_id(605), format_acc_id(606), format_acc_id(607)]
    for _ in range(150):
        sender = rng.choice(normal_accounts)
        merchant = rng.choice(merchants)
        amount = round(rng.uniform(20.0, 350.0), 2)
        transactions.append({
            "txn_id": format_txn_id(txn_counter),
            "timestamp": next_timestamp(min_gap_sec=20, max_gap_sec=180),
            "sender_account": sender,
            "receiver_account": merchant,
            "sender_device_id": normal_devices[sender],
            "amount_inr": amount,
            "status": "SUCCESS" if rng.random() > 0.01 else "FAILED",
            "complaint_filed": False,
            "ground_truth": {"scenario": "normal", "ring_member_accounts": []}
        })
        txn_counter += 1

    # Sub-case 2C: Society Rent / Maintenance Aggregator (ACC_0608, ACC_0609)
    aggregators = [format_acc_id(608), format_acc_id(609)]
    for _ in range(50):
        sender = rng.choice(normal_accounts[:60])
        agg = rng.choice(aggregators)
        amount = round(rng.uniform(3500.0, 7500.0), 2)
        transactions.append({
            "txn_id": format_txn_id(txn_counter),
            "timestamp": next_timestamp(min_gap_sec=100, max_gap_sec=900),
            "sender_account": sender,
            "receiver_account": agg,
            "sender_device_id": normal_devices[sender],
            "amount_inr": amount,
            "status": "SUCCESS",
            "complaint_filed": False,
            "ground_truth": {"scenario": "normal", "ring_member_accounts": []}
        })
        txn_counter += 1

    # Sub-case 2D: Multi-hop Trip / Dinner bill splitting (ACC_0610 to ACC_0620 -> 11 friends)
    friend_group = [format_acc_id(i) for i in range(610, 621)]
    for _ in range(75):
        payer = rng.choice(friend_group)
        payee = rng.choice([f for f in friend_group if f != payer])
        amount = round(rng.uniform(300.0, 3200.0), 2)
        transactions.append({
            "txn_id": format_txn_id(txn_counter),
            "timestamp": next_timestamp(min_gap_sec=60, max_gap_sec=400),
            "sender_account": payer,
            "receiver_account": payee,
            "sender_device_id": hard_neg_devices[payer],
            "amount_inr": amount,
            "status": "SUCCESS",
            "complaint_filed": False,
            "ground_truth": {"scenario": "normal", "ring_member_accounts": []}
        })
        txn_counter += 1

    # Sub-case 2E: Freelancers with legitimate client dispute (ACC_0621, ACC_0622)
    freelancers = [format_acc_id(621), format_acc_id(622)]
    for _ in range(20):
        client = rng.choice(normal_accounts[:40])
        fl = rng.choice(freelancers)
        amount = round(rng.uniform(12000.0, 48000.0), 2)
        complaint = rng.random() < 0.15
        transactions.append({
            "txn_id": format_txn_id(txn_counter),
            "timestamp": next_timestamp(min_gap_sec=200, max_gap_sec=1200),
            "sender_account": client,
            "receiver_account": fl,
            "sender_device_id": normal_devices[client],
            "amount_inr": amount,
            "status": "SUCCESS",
            "complaint_filed": complaint,
            "ground_truth": {"scenario": "normal", "ring_member_accounts": []}
        })
        txn_counter += 1

    # Sub-case 2F: High-value occasional legitimate transfers (ACC_0623 to ACC_0635)
    hnw_accounts = [format_acc_id(i) for i in range(623, 636)]
    for _ in range(35):
        s = rng.choice(hnw_accounts)
        r = rng.choice([a for a in hnw_accounts if a != s])
        amount = round(rng.uniform(50000.0, 95000.0), 2)
        transactions.append({
            "txn_id": format_txn_id(txn_counter),
            "timestamp": next_timestamp(min_gap_sec=300, max_gap_sec=1500),
            "sender_account": s,
            "receiver_account": r,
            "sender_device_id": hard_neg_devices[s],
            "amount_inr": amount,
            "status": "SUCCESS",
            "complaint_filed": False,
            "ground_truth": {"scenario": "normal", "ring_member_accounts": []}
        })
        txn_counter += 1

    # 3. BENIGN SHARED DEVICE FAMILIES (ACC_0201 to ACC_0260 -> 60 accounts)
    family_clusters = []
    for c_idx in range(15):
        start_acc = 201 + c_idx * 4
        members = [format_acc_id(i) for i in range(start_acc, start_acc + 4)]
        dev = format_dev_id(20 + c_idx)
        family_clusters.append((members, dev))

    all_family_members = [m for members, _ in family_clusters for m in members]

    for members, shared_dev in family_clusters:
        # Intra-family transfers
        for _ in range(22):
            s = rng.choice(members)
            r = rng.choice([m for m in members if m != s])
            amount = round(rng.uniform(50.0, 4500.0), 2)
            transactions.append({
                "txn_id": format_txn_id(txn_counter),
                "timestamp": next_timestamp(min_gap_sec=60, max_gap_sec=500),
                "sender_account": s,
                "receiver_account": r,
                "sender_device_id": shared_dev,
                "amount_inr": amount,
                "status": "SUCCESS" if rng.random() > 0.02 else "FAILED",
                "complaint_filed": False,
                "ground_truth": {
                    "scenario": "shared_device_family",
                    "ring_member_accounts": []
                }
            })
            txn_counter += 1

        # Inter-family or relative transfers
        for _ in range(8):
            s = rng.choice(members)
            other_family_members = [m for m in all_family_members if m not in members]
            r = rng.choice(other_family_members)
            amount = round(rng.uniform(200.0, 5000.0), 2)
            transactions.append({
                "txn_id": format_txn_id(txn_counter),
                "timestamp": next_timestamp(min_gap_sec=90, max_gap_sec=700),
                "sender_account": s,
                "receiver_account": r,
                "sender_device_id": shared_dev,
                "amount_inr": amount,
                "status": "SUCCESS",
                "complaint_filed": False,
                "ground_truth": {
                    "scenario": "shared_device_family",
                    "ring_member_accounts": []
                }
            })
            txn_counter += 1

        # Family members paying normal grocery/utility accounts
        for _ in range(8):
            s = rng.choice(members)
            r = rng.choice(normal_accounts[:50])
            amount = round(rng.uniform(100.0, 2500.0), 2)
            transactions.append({
                "txn_id": format_txn_id(txn_counter),
                "timestamp": next_timestamp(min_gap_sec=60, max_gap_sec=600),
                "sender_account": s,
                "receiver_account": r,
                "sender_device_id": shared_dev,
                "amount_inr": amount,
                "status": "SUCCESS",
                "complaint_filed": False,
                "ground_truth": {
                    "scenario": "normal",
                    "ring_member_accounts": []
                }
            })
            txn_counter += 1

    # 4. MULE RINGS (ACC_0101 to ACC_0185 -> 85 accounts)
    victim_accounts = [format_acc_id(i) for i in range(901, 951)]
    victim_devices = {v: format_dev_id(900 + idx) for idx, v in enumerate(victim_accounts, start=1)}

    all_mule_ring_accounts = set(format_acc_id(i) for i in range(101, 186))
    mule_devices = {acc: format_dev_id(1000 + idx) for idx, acc in enumerate(sorted(all_mule_ring_accounts), start=1)}

    def add_mule_txn(sender: str, receiver: str, dev: str, amount: float, status: str = "SUCCESS", complaint: bool = False, min_gap: int = 15, max_gap: int = 150):
        nonlocal txn_counter
        rms = [acc for acc in (sender, receiver) if acc in all_mule_ring_accounts]
        transactions.append({
            "txn_id": format_txn_id(txn_counter),
            "timestamp": next_timestamp(min_gap_sec=min_gap, max_gap_sec=max_gap),
            "sender_account": sender,
            "receiver_account": receiver,
            "sender_device_id": dev,
            "amount_inr": amount,
            "status": status,
            "complaint_filed": complaint,
            "ground_truth": {
                "scenario": "mule_ring",
                "ring_member_accounts": rms
            }
        })
        txn_counter += 1

    # Sub-Ring 1: Multi-Tier Aggregator & Funneling Network (ACC_0101 to ACC_0124 -> 24 accounts)
    aggregators_1 = [format_acc_id(i) for i in range(101, 109)]
    layering_1 = [format_acc_id(i) for i in range(109, 121)]
    cashout_1 = [format_acc_id(i) for i in range(121, 125)]

    for _ in range(140):
        vic = rng.choice(victim_accounts[:25])
        agg = rng.choice(aggregators_1)
        amount = round(rng.uniform(5000.0, 25000.0), 2)
        complaint = rng.random() < 0.45
        add_mule_txn(vic, agg, victim_devices[vic], amount, "SUCCESS", complaint, min_gap=20, max_gap=250)

    for _ in range(100):
        agg = rng.choice(aggregators_1)
        inter = rng.choice(layering_1)
        amount = round(rng.uniform(20000.0, 60000.0), 2)
        add_mule_txn(agg, inter, mule_devices[agg], amount, "SUCCESS", False, min_gap=10, max_gap=120)

    for _ in range(80):
        inter = rng.choice(layering_1)
        cash = rng.choice(cashout_1)
        amount = round(rng.uniform(35000.0, 85000.0), 2)
        add_mule_txn(inter, cash, mule_devices[inter], amount, "SUCCESS", False, min_gap=10, max_gap=100)

    # Sub-Ring 2: Circular Layering / Cycle Rings (ACC_0125 to ACC_0135 -> 11 accounts)
    cycle_a = [format_acc_id(i) for i in range(125, 129)]
    for _ in range(45):
        idx = rng.randint(0, len(cycle_a) - 1)
        s, r = cycle_a[idx], cycle_a[(idx + 1) % len(cycle_a)]
        amount = round(rng.uniform(15000.0, 40000.0), 2)
        add_mule_txn(s, r, mule_devices[s], amount, "SUCCESS", False, min_gap=15, max_gap=150)

    cycle_b = [format_acc_id(i) for i in range(129, 134)]
    for _ in range(50):
        idx = rng.randint(0, len(cycle_b) - 1)
        s, r = cycle_b[idx], cycle_b[(idx + 1) % len(cycle_b)]
        amount = round(rng.uniform(18000.0, 48000.0), 2)
        add_mule_txn(s, r, mule_devices[s], amount, "SUCCESS", False, min_gap=15, max_gap=150)

    for _ in range(25):
        s = rng.choice(cycle_a + cycle_b)
        cash = rng.choice([format_acc_id(134), format_acc_id(135)])
        amount = round(rng.uniform(30000.0, 70000.0), 2)
        add_mule_txn(s, cash, mule_devices[s], amount, "SUCCESS", False, min_gap=20, max_gap=180)

    # Sub-Ring 3: High-Velocity Smurfing / Dispersion Ring (ACC_0136 to ACC_0155 -> 20 accounts)
    masters = [format_acc_id(136), format_acc_id(137)]
    smurfs = [format_acc_id(i) for i in range(138, 156)]

    for _ in range(40):
        vic = rng.choice(victim_accounts[25:])
        m = rng.choice(masters)
        amount = round(rng.uniform(40000.0, 95000.0), 2)
        complaint = rng.random() < 0.50
        add_mule_txn(vic, m, victim_devices[vic], amount, "SUCCESS", complaint, min_gap=30, max_gap=300)

    for _ in range(110):
        m = rng.choice(masters)
        smurf = rng.choice(smurfs)
        amount = round(rng.uniform(4500.0, 9900.0), 2)
        add_mule_txn(m, smurf, mule_devices[m], amount, "SUCCESS", False, min_gap=5, max_gap=60)

    # Sub-Ring 4: Dense Mesh Layering with High Failure Rate (ACC_0156 to ACC_0170 -> 15 accounts)
    mesh_accounts = [format_acc_id(i) for i in range(156, 171)]
    for _ in range(85):
        s = rng.choice(mesh_accounts)
        r = rng.choice([m for m in mesh_accounts if m != s])
        amount = round(rng.uniform(25000.0, 65000.0), 2)
        status = "FAILED" if rng.random() < 0.22 else "SUCCESS"
        add_mule_txn(s, r, mule_devices[s], amount, status, False, min_gap=10, max_gap=120)

    # Sub-Ring 5: Device-Hopping Mule Syndicate (ACC_0171 to ACC_0185 -> 15 accounts)
    dev_syndicate = [format_acc_id(i) for i in range(171, 186)]
    syndicate_devices = [format_dev_id(171), format_dev_id(172), format_dev_id(173)]
    for idx, acc in enumerate(dev_syndicate):
        mule_devices[acc] = syndicate_devices[idx % 3]

    for _ in range(70):
        s = rng.choice(dev_syndicate)
        r = rng.choice([m for m in dev_syndicate if m != s])
        amount = round(rng.uniform(15000.0, 50000.0), 2)
        add_mule_txn(s, r, mule_devices[s], amount, "SUCCESS", False, min_gap=15, max_gap=150)

    transactions.sort(key=lambda t: (t["timestamp"], t["txn_id"]))
    return transactions


def assign_account_scenarios(transactions: list[dict]) -> dict[str, str]:
    """Assign scenario to every account according to Section 2 precedence rules:

    1. mule_ring: the account appears in ring_member_accounts of any transaction.
    2. shared_device_family: otherwise, sender or receiver in any transaction whose ground_truth.scenario is shared_device_family.
    3. normal: everything else.
    """
    mule_accounts = set()
    for txn in transactions:
        gt = txn.get("ground_truth", {})
        mule_accounts.update(gt.get("ring_member_accounts", []))

    shared_device_accounts = set()
    for txn in transactions:
        gt = txn.get("ground_truth", {})
        if gt.get("scenario") == "shared_device_family":
            for acc in (txn["sender_account"], txn["receiver_account"]):
                if acc not in mule_accounts:
                    shared_device_accounts.add(acc)

    all_accounts = set()
    for txn in transactions:
        all_accounts.add(txn["sender_account"])
        all_accounts.add(txn["receiver_account"])

    assignment = {}
    for acc in sorted(all_accounts):
        if acc in mule_accounts:
            assignment[acc] = "mule_ring"
        elif acc in shared_device_accounts:
            assignment[acc] = "shared_device_family"
        else:
            assignment[acc] = "normal"

    return assignment


def validate_dataset(transactions: list[dict]) -> dict:
    """Validate the dataset against Section 1 & Section 2 contract requirements."""
    if not transactions:
        raise ValueError("Transaction dataset is empty.")

    txn_id_pattern = re.compile(r"^T\d{6}$")
    acc_id_pattern = re.compile(r"^ACC_\d{4}$")
    dev_id_pattern = re.compile(r"^DEV_\d{4}$")
    iso_utc_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    seen_txn_ids = set()

    required_fields = {
        "txn_id",
        "timestamp",
        "sender_account",
        "receiver_account",
        "sender_device_id",
        "amount_inr",
        "status",
        "complaint_filed",
        "ground_truth"
    }

    # All-or-none ground truth check across dataset
    has_gt_list = [("ground_truth" in t and t["ground_truth"] is not None) for t in transactions]
    if not (all(has_gt_list) or not any(has_gt_list)):
        raise ValueError("ground_truth must be present on every transaction or on none (mixed input is invalid).")

    for idx, txn in enumerate(transactions):
        # Required fields check
        missing = required_fields - set(txn.keys())
        if missing:
            raise ValueError(f"Txn #{idx}: missing required fields: {sorted(missing)}")

        # 1. txn_id
        tid = txn.get("txn_id")
        if not tid or not isinstance(tid, str) or not txn_id_pattern.match(tid):
            raise ValueError(f"Txn #{idx}: invalid txn_id '{tid}' (expected T + 6 digits)")
        if tid in seen_txn_ids:
            raise ValueError(f"Duplicate txn_id '{tid}' at index #{idx}")
        seen_txn_ids.add(tid)

        # 2. timestamp (format and real calendar validity)
        ts = txn.get("timestamp")
        if not ts or not isinstance(ts, str) or not iso_utc_pattern.match(ts):
            raise ValueError(f"Txn #{tid}: invalid timestamp '{ts}' (expected ISO 8601 UTC)")
        try:
            datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError as e:
            raise ValueError(f"Txn #{tid}: timestamp '{ts}' is not a valid calendar date/time: {e}")

        # 3. accounts
        sender = txn.get("sender_account")
        receiver = txn.get("receiver_account")
        if not sender or not acc_id_pattern.match(sender):
            raise ValueError(f"Txn #{tid}: invalid sender_account '{sender}' (expected ACC_ + 4 digits)")
        if not receiver or not acc_id_pattern.match(receiver):
            raise ValueError(f"Txn #{tid}: invalid receiver_account '{receiver}' (expected ACC_ + 4 digits)")
        if sender == receiver:
            raise ValueError(f"Txn #{tid}: sender and receiver accounts must differ ('{sender}')")

        # 4. device
        dev = txn.get("sender_device_id")
        if not dev or not dev_id_pattern.match(dev):
            raise ValueError(f"Txn #{tid}: invalid sender_device_id '{dev}' (expected DEV_ + 4 digits)")

        # 5. amount (must be positive number, strictly rejecting bool as subclass of int)
        amt = txn.get("amount_inr")
        if isinstance(amt, bool) or not isinstance(amt, (int, float)) or amt <= 0:
            raise ValueError(f"Txn #{tid}: invalid amount_inr '{amt}' (must be a number > 0, boolean not allowed)")

        # 6. status
        status = txn.get("status")
        if status not in ("SUCCESS", "FAILED"):
            raise ValueError(f"Txn #{tid}: invalid status '{status}' (expected SUCCESS or FAILED)")

        # 7. complaint_filed (strictly bool)
        cf = txn.get("complaint_filed")
        if type(cf) is not bool:
            raise ValueError(f"Txn #{tid}: invalid complaint_filed '{cf}' (must be boolean)")

        # 8. ground_truth
        gt = txn.get("ground_truth")
        if not isinstance(gt, dict):
            raise ValueError(f"Txn #{tid}: missing or invalid ground_truth (must be dict)")
        scen = gt.get("scenario")
        if scen not in ("mule_ring", "shared_device_family", "normal"):
            raise ValueError(f"Txn #{tid}: invalid ground_truth.scenario '{scen}'")

        ring_members = gt.get("ring_member_accounts")
        if not isinstance(ring_members, list):
            raise ValueError(f"Txn #{tid}: ring_member_accounts must be a list of strings")
        for rm in ring_members:
            if not isinstance(rm, str) or not acc_id_pattern.match(rm):
                raise ValueError(f"Txn #{tid}: invalid ring member ID '{rm}'")
            if rm not in (sender, receiver):
                raise ValueError(f"Txn #{tid}: ring member '{rm}' must be sender or receiver of this transaction")

        if scen in ("shared_device_family", "normal") and len(ring_members) > 0:
            raise ValueError(f"Txn #{tid}: benign scenario '{scen}' must have empty ring_member_accounts")

    # Verify deterministic ordering: sorted by timestamp asc, then txn_id asc
    for i in range(1, len(transactions)):
        prev = transactions[i - 1]
        curr = transactions[i]
        if (prev["timestamp"], prev["txn_id"]) > (curr["timestamp"], curr["txn_id"]):
            raise ValueError(f"Transactions not deterministically sorted: #{prev['txn_id']} before #{curr['txn_id']}")

    # Verify device sharing logic
    device_to_senders = {}
    for txn in transactions:
        dev = txn["sender_device_id"]
        sender = txn["sender_account"]
        device_to_senders.setdefault(dev, set()).add(sender)
    shared_devices = {dev: senders for dev, senders in device_to_senders.items() if len(senders) >= 2}
    if not shared_devices:
        raise ValueError("Shared-device scenario contains no devices shared by >= 2 distinct senders.")

    # Validate account scenario distribution (Section 2 & Section 4)
    scenarios = assign_account_scenarios(transactions)
    counts = {"mule_ring": 0, "shared_device_family": 0, "normal": 0}
    for scen in scenarios.values():
        counts[scen] += 1

    for scen, count in counts.items():
        if count < 10:
            raise ValueError(
                f"Scenario '{scen}' has only {count} accounts; requires at least 10 for evaluation split."
            )

    return {
        "n_transactions": len(transactions),
        "n_accounts": len(scenarios),
        "account_counts_by_scenario": counts
    }


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic UPI transaction data for TraceUPI.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible generation (default: 42)")
    parser.add_argument(
        "--size",
        choices=["small", "expanded"],
        default="expanded",
        help="Dataset size: 'expanded' (~3,300 txns across ~477 accounts) or 'small' (280 txns across 62 accounts)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Target output file path (default: data/transactions_expanded.jsonl for expanded, data/transactions.jsonl for small)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite if target is data/transactions.jsonl when generating expanded dataset."
    )
    args = parser.parse_args()

    if args.output is None:
        target_file = "data/transactions_expanded.jsonl" if args.size == "expanded" else "data/transactions.jsonl"
    else:
        target_file = args.output

    output_path = Path(target_file)

    # Safety guard: prevent accidental overwrite of existing baseline transactions.jsonl with expanded data
    if (
        output_path.resolve() == Path("data/transactions.jsonl").resolve()
        and args.size == "expanded"
        and not args.force
    ):
        raise ValueError(
            "Safety Guard: Refusing to overwrite existing baseline 'data/transactions.jsonl' with expanded dataset. "
            "To promote the expanded dataset, explicitly pass --force."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Generating synthetic transactions (seed={args.seed}, size={args.size})...")
    transactions = generate_synthetic_transactions(seed=args.seed, size=args.size)

    print("Validating generated dataset against Contract v1.1 rules...")
    stats = validate_dataset(transactions)
    print(f"Validation successful: {stats['n_transactions']} transactions, {stats['n_accounts']} accounts.")
    for scen, cnt in stats["account_counts_by_scenario"].items():
        print(f"  - {scen}: {cnt} accounts")

    print(f"Writing dataset to {output_path}...")
    with open(output_path, "w", encoding="utf-8") as f:
        for txn in transactions:
            f.write(json.dumps(txn, ensure_ascii=False) + "\n")

    print(f"Done. Synthetic dataset saved to {output_path} ({output_path.stat().st_size} bytes).")


if __name__ == "__main__":
    main()
