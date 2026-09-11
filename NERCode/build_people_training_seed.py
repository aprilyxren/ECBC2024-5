"""Build reviewable seed data for people/group annotation in Virginia Company texts.

This deliberately does not infer identity from a name, place, or colonial language.
It keeps individuals, Indigenous polities, titles, places, and colonial umbrella
terms in distinct labels.  Run from the repository root with:

    python3 NERCode/build_people_training_seed.py
"""

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "training_seed"

# Canonical forms are deliberately conservative: a row is included only when the
# spelling appears in the OCR or is a predictable OCR/transcription variant.
GAZETTEER = [
    ("Powhatan", "Powhatan|Powhaton|Powhatanes", "PERSON", "Indigenous_named_person", "leader/title-bearing individual; do not use for every Powhatan polity mention"),
    ("Opechancanough", "Opechancanough|Opachancano|Oppachancano|Opichankano", "PERSON", "Indigenous_named_person", "leader/title-bearing individual"),
    ("Tomakin", "Tomakin", "PERSON", "Indigenous_named_person", "individual; reported as intermediary/messenger in the text"),
    ("Gepanocon", "Gepanocon|Gepanocun", "PERSON", "Indigenous_named_person", "described as a weroance in the text"),
    ("Powhatan paramount polity", "Powhatans?", "INDIGENOUS_POLITY", "Indigenous_named_polity", "apply only when context is collective/territorial, not the named person"),
    ("Chickahominy", "Chickahomini(?:es)?|Chickahominy", "INDIGENOUS_POLITY", "Indigenous_named_polity", "do not label Chickahominy River as a polity"),
    ("Pamunkey", "Pamunkeys?|Pamaunkok|Pomunkies", "INDIGENOUS_POLITY", "Indigenous_named_polity", "do not label Pamunkey River as a polity"),
    ("Chesapeake", "Chesapeake|Chesceak|Cheskacke", "AMBIGUOUS", "needs_context", "can name a polity, bay, or place; adjudicate from local context"),
    ("Accomac", "Accomack|Accomac", "AMBIGUOUS", "needs_context", "can name a polity/shore/place; adjudicate from local context"),
    ("Rappahannock", "Rappahannock", "AMBIGUOUS", "needs_context", "often a river; do not infer a polity without contextual evidence"),
    ("Monacan", "Monocon|Monacan", "INDIGENOUS_POLITY", "Indigenous_named_polity", "spelling varies in colonial records"),
    ("Manahoac", "Manahockes|Manahoac", "INDIGENOUS_POLITY", "Indigenous_named_polity", "spelling varies in colonial records"),
    ("Tanx Powhatans", "Tanx Powhatans", "INDIGENOUS_POLITY", "Indigenous_named_polity", "collective term in volume IV index/text"),
    ("Tanx Weyanokes", "Tanx Weyonaques|Tanx Weyanokes", "INDIGENOUS_POLITY", "Indigenous_named_polity", "collective term in volume IV index/text"),
    ("weroance", "Weroances?|Werowances?", "INDIGENOUS_TITLE", "Indigenous_title", "office/title, not a personal name or one people"),
    ("sachem", "Sachems?", "INDIGENOUS_TITLE", "Indigenous_title", "office/title, not a personal name or one people"),
    ("Indian", "Indians?|Indian", "COLONIAL_UMBRELLA_LABEL", "colonial_umbrella", "source language; never normalize to a single polity"),
    ("Savage", "Savages?|Savage", "COLONIAL_UMBRELLA_LABEL", "colonial_umbrella", "source language; retain only as quoted mention text"),
    ("native", "Natives?|native", "COLONIAL_UMBRELLA_LABEL", "colonial_umbrella", "source language; context may be non-Indigenous"),
]

NAME_STOPLIST = {
    "Company", "Virginia", "England", "London", "King", "Council", "Court",
    "Colony", "Plantation", "Indians", "Indian", "Savages", "Savage", "Native",
    "Counsell", "Deputy", "Governor", "Treasurer", "Secretary", "Captain",
    "Master", "Lord", "Earl", "Sir", "Committee", "Commissioners", "General",
    "Adventure", "Adventurers", "Court Book", "Council of State", "Privy Council",
}


def normalized(value):
    return re.sub(r"\s+", " ", value.strip())


def context(text, start, end, width=190):
    return normalized(text[max(0, start - width): min(len(text), end + width)])


def unique_texts(paths):
    """The volume-IV OCR has repeated blocks; avoid multiplying labels by duplication."""
    seen = set()
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        digest = hashlib.sha256(text.encode()).hexdigest()
        if digest not in seen:
            seen.add(digest)
            yield path.name, text


def write_indigenous_mentions():
    files = [ROOT / "OCRTXT" / f"v{i}FullOCR.txt" for i in (2, 3, 4)]
    # This combined page-level JSON is the only local source that includes volume I.
    # Keep its page marker in the text so later reviewers can recover a page source.
    pages = json.loads((ROOT / "chatGPTCode" / "allFourVCLCombinedPerPage.json").read_text(encoding="utf-8"))
    combined = "\n".join(f"[combined_page={page}] {value}" for page, value in pages.items())
    rows, seen = [], set()
    sources = [("allFourVCLCombinedPerPage.json", combined), *unique_texts(files)]
    for source, text in sources:
        # De-duplicate repeated *paragraphs* within a file while retaining distinct evidence.
        paragraph_seen = set()
        for canonical, variants, entity_type, group, note in GAZETTEER:
            for match in re.finditer(r"\b(?:" + variants + r")\b", text, re.I):
                snippet = context(text, match.start(), match.end())
                fingerprint = (canonical, snippet.lower())
                if fingerprint in paragraph_seen:
                    continue
                paragraph_seen.add(fingerprint)
                # The source files overlap. One reviewable copy of identical evidence is enough.
                key = (canonical, match.group(0).lower(), snippet.lower())
                if key not in seen:
                    seen.add(key)
                    rows.append({
                        "mention_id": f"IM{len(rows)+1:05d}", "mention": match.group(0),
                        "canonical_candidate": canonical, "entity_type_suggestion": entity_type,
                        "group_suggestion": group, "source_file": source,
                        "char_offset": match.start(), "context": snippet,
                        "annotation_status": "seed_unreviewed", "notes": note,
                    })
    with (OUT / "indigenous_mentions_seed.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader(); writer.writerows(rows)
    return Counter(row["canonical_candidate"] for row in rows), len(rows)


def write_person_candidates():
    """Reuse the existing spaCy output as candidates, rather than presenting it as truth."""
    source = ROOT / "NERCode" / "cleanedSection1NERNames.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    occurrences = defaultdict(list)
    for date, pages in data.items():
        for page in pages:
            for entity in page.get("entities", []):
                value = normalized(entity.get("entity", ""))
                if entity.get("label") == "PERSON" and value and value not in NAME_STOPLIST:
                    occurrences[value].append(date)
    rows = []
    for value, dates in sorted(occurrences.items(), key=lambda item: (-len(item[1]), item[0].casefold())):
        rows.append({
            "candidate_id": f"PC{len(rows)+1:05d}", "mention": value,
            "canonical_candidate": "", "entity_type_suggestion": "PERSON",
            "group_suggestion": "Virginia_Company_or_colonial_unverified",
            "mention_count": len(dates), "first_document_date": dates[0],
            "source_file": source.name, "annotation_status": "seed_unreviewed",
            "review_note": "NER candidate only; merge spelling variants and verify against context before training.",
        })
    with (OUT / "person_candidates_from_existing_ner.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader(); writer.writerows(rows)
    return len(rows)


def main():
    OUT.mkdir(exist_ok=True)
    counts, indigenous_total = write_indigenous_mentions()
    person_total = write_person_candidates()
    (OUT / "build_summary.json").write_text(json.dumps({
        "indigenous_seed_mentions": indigenous_total,
        "indigenous_mentions_by_canonical_candidate": counts,
        "existing_ner_person_candidates": person_total,
        "important_limit": "These are annotation candidates, not an exhaustive or authoritative list of people."
    }, indent=2, default=dict) + "\n", encoding="utf-8")
    print(f"Wrote {indigenous_total} Indigenous-term mentions and {person_total} person candidates to {OUT}")


if __name__ == "__main__":
    main()
