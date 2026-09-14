"""Consolidate human-accepted alias-review decisions without changing the review queue.

Run from the repository root:
    python3 NERCode/build_consolidated_people.py
"""

import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALIAS_DIR = ROOT / "NERCode" / "alias_review"
QUEUE = ALIAS_DIR / "variant_review_queue.csv"
AUTHORITY = ALIAS_DIR / "entity_authority_seed.csv"
OUT = ALIAS_DIR / "consolidated_people.csv"
UNRESOLVED_OUT = ALIAS_DIR / "unresolved_name_clusters.csv"
SUMMARY_OUT = ALIAS_DIR / "consolidation_summary.json"


def unique(values):
    return list(dict.fromkeys(value for value in values if value))


def main():
    with QUEUE.open(newline="", encoding="utf-8") as f:
        queue = list(csv.DictReader(f))
    with AUTHORITY.open(newline="", encoding="utf-8") as f:
        authority_rows = list(csv.DictReader(f))

    authority = {}
    for row in authority_rows:
        authority.setdefault(row["canonical_id"], row)

    accepted = defaultdict(list)
    unresolved = []
    for row in queue:
        if row["decision"] == "accept" and row.get("accepted_canonical_id", "").strip():
            accepted[row["accepted_canonical_id"]].append(row)
        elif row["decision"] != "accept":
            unresolved.append(row)

    output_rows = []
    for canonical_id, rows in sorted(accepted.items(), key=lambda item: authority.get(item[0], {}).get("canonical_name", item[0])):
        record = authority.get(canonical_id, {})
        output_rows.append({
            "canonical_id": canonical_id,
            "canonical_name": record.get("canonical_name", "UNRESOLVED AUTHORITY RECORD"),
            "entity_type": record.get("entity_type", ""),
            "group": record.get("group", ""),
            "accepted_cluster_count": len(rows),
            "observed_mentions": " | ".join(unique(row["observed_mention"] for row in rows)),
            "accepted_authority_variants": " | ".join(unique(row.get("accepted_authority_variant", "") for row in rows)),
            "first_document_dates": " | ".join(unique(row["first_document_date"] for row in rows)),
            "review_cluster_ids": " | ".join(row["cluster_id"] for row in rows),
            "reviewer_notes": " | ".join(unique(row.get("evidence_note", "") for row in rows)),
        })

    fields = list(output_rows[0]) if output_rows else ["canonical_id", "canonical_name"]
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader(); writer.writerows(output_rows)

    unresolved_fields = [
        "cluster_id", "observed_mention", "decision", "first_document_date",
        "proposal_1_canonical_id", "proposal_1_canonical_name", "proposal_1_score",
        "reviewer", "evidence_note", "source_context",
    ]
    with UNRESOLVED_OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=unresolved_fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(unresolved)

    summary = {
        "reviewed_clusters": len(queue),
        "accepted_clusters": sum(len(rows) for rows in accepted.values()),
        "consolidated_people": len(output_rows),
        "unresolved_clusters": len(unresolved),
        "decision_counts": {decision: sum(row["decision"] == decision for row in queue)
                            for decision in sorted(set(row["decision"] for row in queue))},
    }
    SUMMARY_OUT.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(output_rows)} consolidated people and {len(unresolved)} unresolved clusters.")


if __name__ == "__main__":
    main()
