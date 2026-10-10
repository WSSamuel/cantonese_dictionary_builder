# Cantonese Dictionary Builder

This repository builds the **finished, read-only Cantonese dictionary database** downloaded by the Flutter app. The app should consume the database directly rather than parse or normalize dictionary source data at runtime.

## What the generated database contains

The final `cantonese.db` contains exactly these tables:

- `dictionary_entries` — words, pronunciations, definitions, ready-to-render senses with structured examples/ruby data, word frequency, numeric frequency bands, and precomputed frequency labels.
- `characters` — character → Jyutping mapping, character frequency, and precomputed character readings and structured glosses for unknown compound-word fallback.
- `english_index` — normalized and ranked English → Cantonese lookup mappings.
- `database_metadata` — schema version, source/build information, and preprocessing details.
- `dictionary_words` — slash-expanded spelling aliases used by the subtitle tokenizer, with invisible characters and alternative slash forms normalized. `database_metadata.dictionary_word_max_length` stores the longest alias length, so tokenization does not rescan the entire vocabulary for every subtitle.

The shipped DB intentionally excludes Tatoeba sentences/translations, user cards, FSRS history, learning progress, settings, YouTube history, and subtitles.

## Work done at build time

`build.py` performs all source parsing and one-time transformations before release:

- parses and merges Words.hk bulk dictionary entries and spelling variants;
- normalizes Jyutping for tone-flexible search and builds per-character ruby;
- translates POS abbreviations, POS names and dictionary labels into canonical English;
- creates structured senses, English-only meaning lines, example records and example ruby;
- applies word frequency and calculates numeric frequency bands plus the display labels previously derived in Flutter;
- builds and ranks the normalized English search index;
- builds character readings and precomputes character gloss lines and compound-word character breakdowns;
- expands/normalizes the dictionary word aliases used for subtitle segmentation and stores the maximum alias length for the app's tokenizer;
- creates and validates the final SQLite schema and indexes.

Flutter still performs query-specific work such as selecting/ranking lookup results, laying out ruby text, tokenizing the current subtitle and rendering UI. It does not repeat data preparation that can be done once by the builder.

## Frequency

`dictionary_entries.frequency` stores Words.hk word-frequency values. `frequency_band` is a numeric category derived from the current dictionary distribution (`5` very common, `4` common, `3` medium, `2` uncommon, `1` rare, `0` no frequency data). `frequency_label` stores the UI label computed from the prior rank thresholds, so the app does not scan dictionary ranks on startup.

`characters.frequency` is character frequency and is independent of word frequency. `characters.gloss_pronunciation` and `characters.gloss` supply a precomputed fallback for unknown compound words.

## Build locally

Requirements: Python 3.11+ and internet access.

```bash
python -m pip install -r requirements.txt
python build.py
```

Expected outputs:

```text
dist/cantonese.db
dist/cantonese.db.gz
dist/cantonese.json
```

Run the optional inspection helper:

```bash
python scripts/check_db.py dist/cantonese.db
```

`build.py` validates the database before compression and manifest generation. Run the preprocessing regression tests with `python -m unittest discover -s tests -v`.

## GitHub Actions / releases

`.github/workflows/build.yml` builds monthly and can be triggered manually. The workflow builds and validates SQLite, compresses it, then attaches `cantonese.db.gz` and `cantonese.json` to the release. Flutter downloads the gzip artifact and validates the version/tables/columns before replacing the active dictionary database.

```text
Words.hk → build.py → cantonese.db → gzip + manifest → GitHub Release → Flutter
```

## Source data and licensing

The builder downloads the Words.hk bulk dictionary, word-frequency data, character-frequency data, character/Jyutping list and English index. Source URLs are stored in `database_metadata`. Review the current Words.hk licensing and attribution requirements before redistributing generated dictionary data.

## Flutter integration

See [`docs/flutter_integration.md`](docs/flutter_integration.md).
