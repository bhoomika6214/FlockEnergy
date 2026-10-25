"""Network Hierarchy reconstruction, anomaly detection, and reconciliation service."""

from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from app.models.hierarchy import (
    HierarchyAnomaly,
    HierarchyAnomalyReport,
    HierarchyNode,
    HierarchyTreeResponse,
)
from app.models.meter import MeterDetail


class HierarchyService:
    """Builds electrical network hierarchy trees and reports legacy data inconsistencies."""

    TIERS = ["zone", "circle", "division", "subdivision", "substation", "feeder", "dt"]

    @classmethod
    def analyze_and_build(cls, meters: List[MeterDetail]) -> Tuple[HierarchyTreeResponse, HierarchyAnomalyReport]:
        """Process meter collection into a clean hierarchy tree and comprehensive anomaly report."""
        anomalies: List[HierarchyAnomaly] = []

        # 1. Inspect Tier Codes & Names for Inconsistencies
        # Track: tier -> code -> Counter of names seen
        code_to_names: Dict[str, Dict[str, Counter]] = {t: defaultdict(Counter) for t in cls.TIERS}
        code_to_meters: Dict[str, Dict[str, List[str]]] = {t: defaultdict(list) for t in cls.TIERS}

        # Track parent mappings: (child_tier, child_code) -> Counter of (parent_tier, parent_code)
        parent_mappings: Dict[Tuple[str, str], Counter] = defaultdict(Counter)

        for m in meters:
            if not m.hierarchy:
                continue

            tier_values: Dict[str, Tuple[Optional[str], Optional[str]]] = {
                "zone": (m.hierarchy.zone.code if m.hierarchy.zone else None, m.hierarchy.zone.name if m.hierarchy.zone else None),
                "circle": (m.hierarchy.circle.code if m.hierarchy.circle else None, m.hierarchy.circle.name if m.hierarchy.circle else None),
                "division": (m.hierarchy.division.code if m.hierarchy.division else None, m.hierarchy.division.name if m.hierarchy.division else None),
                "subdivision": (m.hierarchy.subdivision.code if m.hierarchy.subdivision else None, m.hierarchy.subdivision.name if m.hierarchy.subdivision else None),
                "substation": (m.hierarchy.substation.code if m.hierarchy.substation else None, m.hierarchy.substation.name if m.hierarchy.substation else None),
                "feeder": (m.hierarchy.feeder.code if m.hierarchy.feeder else None, m.hierarchy.feeder.name if m.hierarchy.feeder else None),
                "dt": (m.hierarchy.dt.code if m.hierarchy.dt else None, m.hierarchy.dt.name if m.hierarchy.dt else None),
            }

            for tier, (code, name) in tier_values.items():
                if code:
                    code_clean = code.strip()
                    name_clean = (name or "").strip()
                    code_to_names[tier][code_clean][name_clean] += 1
                    code_to_meters[tier][code_clean].append(m.meter_id)

            # Record parent-child links along the canonical tier ladder
            for i in range(len(cls.TIERS) - 1):
                p_tier = cls.TIERS[i]
                c_tier = cls.TIERS[i + 1]
                p_code = tier_values[p_tier][0]
                c_code = tier_values[c_tier][0]
                if p_code and c_code:
                    parent_mappings[(c_tier, c_code.strip())][(p_tier, p_code.strip())] += 1

        # 2. Detect Naming Anomalies (Aliasing, Empty Strings)
        canonical_names: Dict[str, Dict[str, str]] = {t: {} for t in cls.TIERS}

        for tier, code_map in code_to_names.items():
            for code, name_counts in code_map.items():
                # Pick best non-empty name by highest frequency
                non_empty = {n: cnt for n, cnt in name_counts.items() if n}
                if non_empty:
                    best_name = max(non_empty.items(), key=lambda x: x[1])[0]
                else:
                    best_name = f"{tier.capitalize()} {code}"

                canonical_names[tier][code] = best_name

                # Check if multiple names exist
                all_variants = list(name_counts.keys())
                if len(all_variants) > 1:
                    non_empty_variants = [v for v in all_variants if v]
                    if len(non_empty_variants) > 1:
                        # Genuine alias conflict (e.g. DT-007)
                        anomalies.append(
                            HierarchyAnomaly(
                                anomaly_type="naming_alias",
                                tier=tier,
                                entity_code=code,
                                details=(
                                    f"{tier.upper()} entity '{code}' is registered under multiple conflicting names: "
                                    f"{non_empty_variants}. Canonicalized to '{best_name}'."
                                ),
                                variants=non_empty_variants,
                                meter_ids=code_to_meters[tier][code][:5],
                            )
                        )
                    elif "" in all_variants:
                        # Incomplete name field
                        anomalies.append(
                            HierarchyAnomaly(
                                anomaly_type="missing_name",
                                tier=tier,
                                entity_code=code,
                                details=(
                                    f"{tier.upper()} entity '{code}' is missing name on {name_counts['']} records. "
                                    f"Canonicalized to '{best_name}'."
                                ),
                                variants=all_variants,
                                meter_ids=code_to_meters[tier][code][:5],
                            )
                        )

        # 3. Detect Multi-Parenting / Shared Upstream Topology
        canonical_parents: Dict[Tuple[str, str], Tuple[str, str]] = {}
        for (c_tier, c_code), p_counts in parent_mappings.items():
            best_parent = max(p_counts.items(), key=lambda x: x[1])[0]
            canonical_parents[(c_tier, c_code)] = best_parent

            if len(p_counts) > 1:
                parents_str = [f"{pt}:{pc} ({cnt}x)" for (pt, pc), cnt in p_counts.items()]
                anomalies.append(
                    HierarchyAnomaly(
                        anomaly_type="multi_parent_mapping",
                        tier=c_tier,
                        entity_code=c_code,
                        details=(
                            f"{c_tier.capitalize()} '{c_code}' is mapped across multiple parent nodes: {parents_str}. "
                            f"Canonical parent resolved to '{best_parent[0]}:{best_parent[1]}'."
                        ),
                        variants=[f"{pt}:{pc}" for pt, pc in p_counts.keys()],
                        meter_ids=code_to_meters[c_tier][c_code][:5],
                    )
                )

        # 4. Construct Clean Hierarchical Tree
        # Nodes dictionary: (tier, code) -> HierarchyNode
        node_registry: Dict[Tuple[str, str], HierarchyNode] = {}

        def get_or_create_node(tier: str, code: str) -> HierarchyNode:
            key = (tier, code)
            if key not in node_registry:
                name = canonical_names.get(tier, {}).get(code, f"{tier.capitalize()} {code}")
                node_registry[key] = HierarchyNode(
                    id=f"{tier}:{code}",
                    tier=tier,
                    code=code,
                    name=name,
                    meter_count=0,
                    children=[],
                )
            return node_registry[key]

        # Attach meters to DTs and count up
        dt_meter_counts: Counter = Counter()
        for m in meters:
            dt_code = m.dt_code or (m.hierarchy.dt.code if m.hierarchy and m.hierarchy.dt else None)
            if dt_code:
                dt_meter_counts[dt_code.strip()] += 1

        for dt_code, count in dt_meter_counts.items():
            dt_node = get_or_create_node("dt", dt_code)
            dt_node.meter_count = count

        # Link tiers bottom-up: DT -> Feeder -> Substation -> Subdivision -> Division -> Circle -> Zone
        for i in reversed(range(len(cls.TIERS) - 1)):
            p_tier = cls.TIERS[i]
            c_tier = cls.TIERS[i + 1]

            # Find all child nodes currently in registry
            child_keys = [k for k in list(node_registry.keys()) if k[0] == c_tier]
            for _, c_code in child_keys:
                c_node = node_registry[(c_tier, c_code)]
                parent_info = canonical_parents.get((c_tier, c_code))
                if parent_info:
                    p_node = get_or_create_node(parent_info[0], parent_info[1])
                    if c_node not in p_node.children:
                        p_node.children.append(c_node)
                        p_node.meter_count += c_node.meter_count

        # Extract root nodes (Zones)
        root_nodes = [
            node for (tier, code), node in sorted(node_registry.items(), key=lambda x: x[1].code)
            if tier == "zone"
        ]

        # In case some nodes had no parent (orphan feeder or DT), attach to an 'Unassigned' zone
        attached_child_ids = set()
        for node in node_registry.values():
            for child in node.children:
                attached_child_ids.add(child.id)

        orphans = [
            node for node in node_registry.values()
            if node.tier != "zone" and node.id not in attached_child_ids
        ]
        if orphans:
            unassigned_zone = HierarchyNode(
                id="zone:Z-UNASSIGNED",
                tier="zone",
                code="Z-UNASSIGNED",
                name="Unassigned Utility Assets",
                meter_count=sum(o.meter_count for o in orphans),
                children=orphans,
            )
            root_nodes.append(unassigned_zone)

        # Count tier totals
        tree_response = HierarchyTreeResponse(
            total_meters_indexed=len(meters),
            total_zones=len(root_nodes),
            total_circles=len([n for (t, c), n in node_registry.items() if t == "circle"]),
            total_feeders=len([n for (t, c), n in node_registry.items() if t == "feeder"]),
            total_dts=len([n for (t, c), n in node_registry.items() if t == "dt"]),
            anomalies_count=len(anomalies),
            tree=root_nodes,
        )

        anomaly_report = HierarchyAnomalyReport(
            total_anomalies=len(anomalies),
            anomalies=anomalies,
            reconciliation_strategy=(
                "1. Canonical Naming: Resolved conflicting name aliases (e.g. DT-007 'Sanganer DT 7' vs "
                "'Old Malviya Nagar Xfmr') by modal frequency weighting. "
                "2. Multi-Parent Topology: Feeders and substations shared across multiple parents are mapped to "
                "their primary dominant parent in the tree view, with multi-parent mappings recorded in diagnostics. "
                "3. Missing Labels: Null or empty tier strings were backfilled with tier codes or canonical aliases."
            ),
        )

        return tree_response, anomaly_report
