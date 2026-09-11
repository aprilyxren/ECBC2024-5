# Virginia Company people/group annotation seed

Run `python3 NERCode/build_people_training_seed.py` from the repository root to regenerate the CSV files in this directory.

The desired research question requires two separate decisions for every mention:

1. What kind of thing is named? (`PERSON`, `INDIGENOUS_POLITY`, `INDIGENOUS_TITLE`, `PLACE_OR_HYDRONYM`, `COLONIAL_UMBRELLA_LABEL`, or `AMBIGUOUS`.)
2. If it is a person or polity, can a historically specific identity be supported by the immediate text and an approved authority file?

Do **not** train the model to map `Indian`, `Savage`, `native`, or `Powhatan` automatically to one modern or historical people. Those are colonial umbrella labels or context-dependent forms. Preserve the source word in `mention`; put any modern/historical reconciliation in `canonical_candidate` only after review.

`indigenous_mentions_seed.csv` is a high-recall, reviewable set of corpus evidence. It intentionally includes terms that are ambiguous between a polity and a river/place, such as Chesapeake, Accomac, Pamunkey, and Rappahannock. `person_candidates_from_existing_ner.csv` is a separate candidate list from the project’s existing spaCy pass. It includes false positives and must not be used as gold data.

Suggested gold labels use BIO spans plus the entity types above. Add these fields during review: `document_id`, `page`, `span_start`, `span_end`, `adjudicator`, `certainty` (`high`, `medium`, `low`), and `evidence_note`. Split training/test data by document/date, rather than randomly by sentence, to avoid leakage from repeated formulae and names.
