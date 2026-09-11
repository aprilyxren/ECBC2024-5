# Alias-review workflow

1. Add only verified people/polities and their confirmed spellings to `entity_authority_seed.csv`.
2. Run `python3 NERCode/build_alias_review_queue.py`.
3. Review `variant_review_queue.csv`. It has one row per observed-name candidate, with up to three proposed identities in `proposal_1_*` through `proposal_3_*` columns. The decision columns come before the long `source_context` column. Set `decision` to `accept`, `reject`, or `uncertain`; if accepted, enter the chosen ID in `accepted_canonical_id`, its proposal number in `accepted_proposal_rank`, and its supporting authority spelling in `accepted_authority_variant`. Record the decisive context in `evidence_note`.
4. `variant_review_queue_detailed.csv` is the row-per-proposal version for sorting or analysis; it is not the primary review file.
5. Move accepted variants into the authority CSV with a source/evidence note; then regenerate the queue.

Before every rebuild, the script saves the existing queue as `variant_review_queue.previous.csv` and creates a timestamped copy in `queue_backups/`. To deliberately begin a fresh pass while retaining those backups, run `python3 NERCode/build_alias_review_queue.py --reset-reviews`.

The script is candidate generation, not entity resolution. It preserves the review columns when rebuilt, keyed by `candidate_id`. In particular, surname-only matches and names with common spellings must be confirmed by date, role, associates, and source context before they become aliases. Never use it to merge an Indigenous collective, title, place, and individual merely because forms look similar.
