-- Generated database schema for the read-only Cantonese dictionary.
-- All presentation-focused parsing and normalization is performed by build.py.
-- User cards, progress, settings and Tatoeba content belong elsewhere.
-- database_metadata includes dictionary_word_max_length for longest-match tokenization.

PRAGMA user_version = 3;

CREATE TABLE dictionary_entries (
    id INTEGER PRIMARY KEY,
    word TEXT NOT NULL UNIQUE,
    pronunciation TEXT NOT NULL DEFAULT '',
    pronunciation_normalized TEXT NOT NULL DEFAULT '',
    definition TEXT NOT NULL DEFAULT '',
    senses TEXT NOT NULL DEFAULT '',
    part_of_speech TEXT NOT NULL DEFAULT '',
    level TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '',
    synonyms TEXT NOT NULL DEFAULT '',
    related_words TEXT NOT NULL DEFAULT '',
    character_meanings TEXT NOT NULL DEFAULT '',
    antonyms TEXT NOT NULL DEFAULT '',
    usage_notes TEXT NOT NULL DEFAULT '',
    word_ruby TEXT NOT NULL DEFAULT '',
    frequency INTEGER NOT NULL DEFAULT 0,
    frequency_band INTEGER NOT NULL DEFAULT 0,
    frequency_label TEXT NOT NULL DEFAULT ''
);

CREATE TABLE characters (
    id INTEGER PRIMARY KEY,
    character TEXT NOT NULL UNIQUE,
    jyutping TEXT NOT NULL DEFAULT '',
    frequency INTEGER NOT NULL DEFAULT 0,
    gloss_pronunciation TEXT NOT NULL DEFAULT '',
    gloss TEXT NOT NULL DEFAULT ''
);

CREATE TABLE english_index (
    id INTEGER PRIMARY KEY,
    english_word TEXT NOT NULL,
    english_normalized TEXT NOT NULL,
    cantonese_word TEXT NOT NULL,
    rank INTEGER NOT NULL DEFAULT 0,
    UNIQUE(english_word, cantonese_word)
);

CREATE TABLE database_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE dictionary_words (
    word TEXT PRIMARY KEY NOT NULL
);

CREATE INDEX idx_dictionary_word ON dictionary_entries(word);
CREATE INDEX idx_dictionary_pronunciation ON dictionary_entries(pronunciation);
CREATE INDEX idx_dictionary_pronunciation_normalized ON dictionary_entries(pronunciation_normalized);
CREATE INDEX idx_dictionary_frequency ON dictionary_entries(frequency DESC);
CREATE INDEX idx_dictionary_frequency_band ON dictionary_entries(frequency_band DESC);
CREATE INDEX idx_dictionary_frequency_label ON dictionary_entries(frequency_label);
CREATE INDEX idx_dictionary_words_word ON dictionary_words(word);
CREATE INDEX idx_characters_character ON characters(character);
CREATE INDEX idx_characters_jyutping ON characters(jyutping);
CREATE INDEX idx_characters_frequency ON characters(frequency DESC);
CREATE INDEX idx_english_word ON english_index(english_word);
CREATE INDEX idx_english_normalized ON english_index(english_normalized);
CREATE INDEX idx_english_cantonese ON english_index(cantonese_word);
CREATE INDEX idx_english_rank ON english_index(english_normalized, rank);
