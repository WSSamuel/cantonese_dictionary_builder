# Flutter integration

The app is a consumer of a finished, read-only Cantonese dictionary database. Download the latest database artifact from the release endpoint configured in Flutter, decompress it to a temporary file, validate it, then replace the active file and reopen the database connection. Do not parse Words.hk source datasets in the app.

## Builder-owned preprocessing

The builder prepares POS/tags, frequency labels, word and example ruby, English-only sense meaning lines, normalized Jyutping, the ranked English index, character readings and gloss lines, compound character breakdowns, and normalized slash-expanded subtitle aliases. The app's remaining dictionary code should focus on queries and UI rendering.

## Schema version 3

The generated database contains exactly:

- `dictionary_entries`
- `characters`
- `english_index`
- `database_metadata`
- `dictionary_words`

`dictionary_entries` includes `frequency_label` alongside numeric `frequency_band`. Its `senses` JSON stores ready-to-render `meaningLines` and structured `exampleDetails` with optional `ruby` arrays; duplicated top-level `definitions` and `examples` columns are omitted. `part_of_speech` and `tags` already use the builder's canonical display wording. `character_meanings` is precomputed as structured JSON for compound words.

`characters` contains `character`, `jyutping`, `frequency`, `gloss_pronunciation`, and `gloss`. The last two fields are the builder-prepared fallback for an unknown compound word. `dictionary_words` contains pre-expanded spelling aliases for longest-match subtitle tokenization. The builder stores `dictionary_word_max_length` in `database_metadata` so the tokenizer can avoid scanning the full alias set for every subtitle.

The app should reject an artifact when its schema version or required columns differ. The schema is a static artifact; user cards, FSRS/review history, progress, settings, YouTube history/subtitles, and Tatoeba data are not stored here.

## Build and inspect

```bash
python -m pip install -r requirements.txt
python build.py
python scripts/check_db.py dist/cantonese.db
```

The manifest emitted by the builder records schema version, compressed/uncompressed sizes, SHA-256 and build statistics.
