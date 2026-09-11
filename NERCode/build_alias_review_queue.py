"""Create a human-review queue for possible historical/OCR name variants.

This never changes the authority file or automatically assigns an identity. It only
proposes candidates for review. Run after build_people_training_seed.py:

    python3 NERCode/build_alias_review_queue.py
"""

import csv
import argparse
import json
import re
import shutil
from datetime import datetime
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / "NERCode" / "alias_review" / "entity_authority_seed.csv"
CANDIDATES = ROOT / "NERCode" / "training_seed" / "person_candidates_from_existing_ner.csv"
NER_SOURCE = ROOT / "NERCode" / "cleanedSection1NERNames.json"
OUT = ROOT / "NERCode" / "alias_review" / "variant_review_queue.csv"
DETAIL_OUT = ROOT / "NERCode" / "alias_review" / "variant_review_queue_detailed.csv"
PREVIOUS_OUT = ROOT / "NERCode" / "alias_review" / "variant_review_queue.previous.csv"
BACKUP_DIR = ROOT / "NERCode" / "alias_review" / "queue_backups"

TITLES = {"sir", "mr", "mrs", "master", "capt", "captain", "lord", "lady", "dr", "doctor"}
ABBREVIATIONS = {"tho": "thomas", "thos": "thomas", "nich": "nicholas", "geo": "george", "wm": "william", "willm": "william", "rob": "robert", "edw": "edward", "io": "john"}


def words(value):
    """Normalize typography and common early-modern/OCR forms for matching only."""
    value = value.casefold().replace("ſ", "s")
    tokens = re.findall(r"[a-z]+", value)
    # Initial ``ff`` is a frequent early-modern rendering of an initial F (ffarrer).
    tokens = ["f" + token[2:] if token.startswith("ff") else token for token in tokens]
    return [ABBREVIATIONS.get(token, token) for token in tokens if token not in TITLES]


def historical_key(token):
    """A deliberately small rule set: y/i, terminal silent e, and common typography."""
    token = token.replace("ph", "f").replace("y", "i")
    return token[:-1] if token.endswith("e") and len(token) > 3 else token


def levenshtein(left, right):
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        current = [i]
        for j, b in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (a != b)))
        previous = current
    return previous[-1]


def similarity(left, right):
    if not left or not right:
        return 0.0
    if historical_key(left) == historical_key(right):
        return 1.0
    return 1 - levenshtein(left, right) / max(len(left), len(right))


def score(observed, variant):
    observed_words, variant_words = words(observed), words(variant)
    if not observed_words or not variant_words:
        return 0.0, "no usable name tokens"
    # Surnames are the strongest evidence. First names increase confidence when present.
    surname_score = similarity(observed_words[-1], variant_words[-1])
    first_score = max((similarity(word, variant_words[0]) for word in observed_words[:-1]), default=0.0)
    if len(observed_words) == 1:
        return surname_score, "surname-only comparison"
    return 0.75 * surname_score + 0.25 * first_score, "surname plus given-name comparison"


def clean_context(text, start, end, width=230):
    excerpt = text[max(0, start - width): min(len(text), end + width)]
    return re.sub(r"\s+", " ", excerpt).strip()


def source_contexts():
    """Return up to two dated primary-text excerpts for every existing NER mention."""
    data = json.loads(NER_SOURCE.read_text(encoding="utf-8"))
    examples = defaultdict(list)
    for date, pages in data.items():
        for page in pages:
            text = page.get("text", "")
            for entity in page.get("entities", []):
                mention = entity.get("entity", "")
                if entity.get("label") != "PERSON" or not mention:
                    continue
                found = re.search(re.escape(mention), text, re.I)
                if found:
                    key = mention.casefold()
                    example = f"{date}: {clean_context(text, found.start(), found.end())}"
                    if example not in examples[key] and len(examples[key]) < 2:
                        examples[key].append(example)
    return {key: " || ".join(value) for key, value in examples.items()}


def main(reset_reviews=False):
    with AUTHORITY.open(newline="", encoding="utf-8") as f:
        aliases = list(csv.DictReader(f))
    by_id = defaultdict(list)
    for row in aliases:
        by_id[row["canonical_id"]].append(row)

    with CANDIDATES.open(newline="", encoding="utf-8") as f:
        candidates = list(csv.DictReader(f))
    contexts = source_contexts()
    # Keep one recoverable copy before any generated queue is overwritten.
    if OUT.exists():
        shutil.copy2(OUT, PREVIOUS_OUT)
        BACKUP_DIR.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        shutil.copy2(OUT, BACKUP_DIR / f"variant_review_queue_{timestamp}.csv")
    # Preserve manual review decisions when the generated columns are rebuilt.
    previous_reviews = {}
    if OUT.exists() and not reset_reviews:
        with OUT.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                previous_reviews[row.get("candidate_id", "")] = row

    queue, detailed = [], []
    for candidate in candidates:
        proposed = []
        for canonical_id, alias_rows in by_id.items():
            best = max(alias_rows, key=lambda alias: score(candidate["mention"], alias["approved_variant"])[0])
            match_score, rationale = score(candidate["mention"], best["approved_variant"])
            # 0.78 retains plausible OCR variants; exact historical-key matches always pass.
            if match_score >= 0.78:
                proposed.append((match_score, best, rationale))
        proposals = sorted(proposed, key=lambda item: -item[0])[:3]
        if not proposals:
            continue
        previous = previous_reviews.get(candidate["candidate_id"], {})
        cluster = {
            "cluster_id": f"VC{len(queue)+1:05d}", "observed_mention": candidate["mention"],
            "candidate_id": candidate["candidate_id"], "mention_count": candidate["mention_count"],
            "first_document_date": candidate["first_document_date"],
            "decision": previous.get("decision", "needs_review"),
            "accepted_canonical_id": previous.get("accepted_canonical_id", ""),
            "accepted_proposal_rank": previous.get("accepted_proposal_rank", ""),
            "accepted_authority_variant": previous.get("accepted_authority_variant", ""),
            "reviewer": previous.get("reviewer", ""), "evidence_note": previous.get("evidence_note", ""),
            "source_context": contexts.get(candidate["mention"].casefold(), "No source excerpt recovered; inspect the NER source manually."),
        }
        for rank, (match_score, alias, rationale) in enumerate(proposals, 1):
            cluster.update({
                f"proposal_{rank}_canonical_id": alias["canonical_id"],
                f"proposal_{rank}_canonical_name": alias["canonical_name"],
                f"proposal_{rank}_matched_variant": alias["approved_variant"],
                f"proposal_{rank}_score": f"{match_score:.3f}",
                f"proposal_{rank}_rationale": rationale,
            })
            detailed.append({
                "detail_id": f"VR{len(detailed)+1:05d}", "cluster_id": cluster["cluster_id"],
                "observed_mention": candidate["mention"], "candidate_id": candidate["candidate_id"],
                "rank": rank, "proposed_canonical_id": alias["canonical_id"],
                "proposed_canonical_name": alias["canonical_name"],
                "matched_authority_variant": alias["approved_variant"], "match_score": f"{match_score:.3f}",
                "matching_rationale": rationale,
            })
        queue.append(cluster)
    fields = [
        "cluster_id", "observed_mention", "candidate_id", "mention_count", "first_document_date",
        "decision", "accepted_canonical_id", "accepted_proposal_rank", "accepted_authority_variant",
        *[field for rank in range(1, 4) for field in (
            f"proposal_{rank}_canonical_id", f"proposal_{rank}_canonical_name", f"proposal_{rank}_matched_variant",
            f"proposal_{rank}_score", f"proposal_{rank}_rationale",
        )],
        "reviewer", "evidence_note", "source_context",
    ]
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader(); writer.writerows(queue)
    detail_fields = list(detailed[0]) if detailed else ["detail_id", "cluster_id", "observed_mention"]
    with DETAIL_OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=detail_fields)
        writer.writeheader(); writer.writerows(detailed)
    print(f"Wrote {len(queue)} name clusters to {OUT} and {len(detailed)} detailed proposals to {DETAIL_OUT}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the alias-review queue.")
    parser.add_argument("--reset-reviews", action="store_true", help="Start every queue row at needs_review; the prior queue is saved as .previous.csv.")
    main(reset_reviews=parser.parse_args().reset_reviews)
