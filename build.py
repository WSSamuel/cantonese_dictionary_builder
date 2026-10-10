#!/usr/bin/env python3
"""
Build the app-ready Cantonese SQLite dictionary used by the Flutter app.

The output DB is intentionally a finished application artifact.

The build pipeline is responsible for:
- parsing Words.hk bulk dictionary data
- merging word/Jyutping variants
- parsing English definitions and examples
- generating word ruby JSON
- generating normalized Jyutping
- applying word frequency
- calculating frequency bands
- building the English search index
- building the character/Jyutping/frequency table
- creating all indexes required by the app
- validating the final DB

Flutter should NOT need to repair, normalize, migrate, or calculate
dictionary-data properties at runtime.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import re
import sqlite3
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

WORDS_HK = "https://words.hk"

REQUEST_DATA_URL = f"{WORDS_HK}/faiman/request_data/"
FREQUENCY_URL = f"{WORDS_HK}/faiman/analysis/existingwordcount.json"
CHAR_FREQUENCY_URL = f"{WORDS_HK}/faiman/analysis/charcount.json"
CHARLIST_URL = f"{WORDS_HK}/faiman/analysis/charlist.csv"
ENGLISH_INDEX_URL = f"{WORDS_HK}/faiman/analysis/englishindex.json"


# ---------------------------------------------------------------------------
# DB version
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 3
USER_AGENT = "cantonese-dictionary-builder/3.0"

# Presentation labels ported from the Flutter dictionary UI. Keep these mappings
# here so generated databases are display-ready and Flutter does not carry a
# second copy of the linguistic mapping table.
PART_OF_SPEECH_NAMES = {
    '名詞': 'noun',
    '名词': 'noun',
    '動詞': 'verb',
    '动词': 'verb',
    '形容詞': 'adjective',
    '形容词': 'adjective',
    '副詞': 'adverb',
    '副词': 'adverb',
    '代詞': 'pronoun',
    '代词': 'pronoun',
    '數詞': 'numeral',
    '数词': 'numeral',
    '量詞': 'classifier',
    '量词': 'classifier',
    '介詞': 'preposition',
    '介词': 'preposition',
    '助詞': 'particle',
    '助词': 'particle',
    '語助詞': 'particle',
    '语助词': 'particle',
    '語氣詞': 'modal particle',
    '语气词': 'modal particle',
    '情態詞': 'modal particle',
    '情态词': 'modal particle',
    '動助詞': 'auxiliary',
    '动助词': 'auxiliary',
    '助動詞': 'auxiliary',
    '助动词': 'auxiliary',
    '連詞': 'conjunction',
    '连词': 'conjunction',
    '感嘆詞': 'interjection',
    '感叹词': 'interjection',
    '感歎詞': 'interjection',
    '感嘆词': 'interjection',
    '嘆詞': 'interjection',
    '叹词': 'interjection',
    '感嘩詞': 'interjection',
    '感哗词': 'interjection',
    '結嘩詞': 'interjection',
    '呼詞': 'vocative',
    '呼词': 'vocative',
    '召喚詞': 'vocative',
    '召唤词': 'vocative',
    '擬聲詞': 'onomatopoeia',
    '拟声词': 'onomatopoeia',
    '擬音詞': 'onomatopoeia',
    '象聲詞': 'onomatopoeia',
    '象声词': 'onomatopoeia',
    '冠詞': 'article',
    '冠词': 'article',
    '限定詞': 'determiner',
    '限定词': 'determiner',
    '指示詞': 'determiner',
    '指示词': 'determiner',
    '方位詞': 'directional word',
    '方位词': 'directional word',
    '處所詞': 'place word',
    '处所词': 'place word',
    '時間詞': 'time word',
    '时间词': 'time word',
    '程度詞': 'degree word',
    '程度词': 'degree word',
    '範圍詞': 'scope word',
    '范围词': 'scope word',
    '區別詞': 'distinguishing word',
    '区别词': 'distinguishing word',
    '承接詞': 'linking word',
    '承接词': 'linking word',
    '轉折詞': 'contrastive word',
    '转折词': 'contrastive word',
    '因果詞': 'causal word',
    '因果词': 'causal word',
    '條件詞': 'conditional word',
    '条件词': 'conditional word',
    '目的詞': 'purpose word',
    '目的词': 'purpose word',
    '結果詞': 'consequential word',
    '结果词': 'consequential word',
    '比較詞': 'comparative word',
    '比较词': 'comparative word',
    '疑問詞': 'question word',
    '疑问词': 'question word',
    '指示代詞': 'demonstrative pronoun',
    '疑问代词': 'interrogative pronoun',
    '人稱代詞': 'personal pronoun',
    '不定代詞': 'indefinite pronoun',
    '接頭詞': 'prefix',
    '接头词': 'prefix',
    '前綴': 'prefix',
    '接尾詞': 'suffix',
    '接尾词': 'suffix',
    '後綴': 'suffix',
    '詞綴': 'affix',
    '词缀': 'affix',
    '語素': 'morpheme',
    '语素': 'morpheme',
    '詞根': 'root',
    '词根': 'root',
    '語根': 'root',
    '複合詞': 'compound word',
    '复合词': 'compound word',
    '派生詞': 'derived word',
    '轉寫詞': 'transcription',
    '轉寫': 'transcription',
    '拉丁字母': 'Latin letter',
    '拼音': 'pinyin',
    '羅馬字': 'Romanisation',
    '罗马字': 'Romanisation',
    '詞': 'word',
    '词': 'word',
    '字': 'character',
    '漢字': 'character',
    '汉字': 'character',
    '詞語': 'word',
    '词语': 'word',
    '詞組': 'phrase',
    '词组': 'phrase',
    '片語': 'phrase',
    '短语': 'phrase',
    '短語': 'phrase',
    '語塊': 'phrase',
    '固定詞組': 'fixed phrase',
    '固定词组': 'fixed phrase',
    '成語': 'idiom',
    '成语': 'idiom',
    '慣用語': 'idiom',
    '惯用语': 'idiom',
    '俗語': 'colloquialism',
    '俗语': 'colloquialism',
    '諺語': 'proverb',
    '谚语': 'proverb',
    '歇後語': 'xiehouyu',
    '歇后语': 'xiehouyu',
    '俚語': 'slang',
    '俚语': 'slang',
    '縮寫': 'abbreviation',
    '縮寫詞': 'abbreviation',
    '缩写词': 'abbreviation',
    '略語': 'abbreviation',
    '略语': 'abbreviation',
    '簡稱': 'short form',
    '简称': 'short form',
    '綽號': 'nickname',
    '绰号': 'nickname',
    '專門詞': 'technical term',
    '专门词': 'technical term',
    '術語': 'term',
    '术语': 'term',
    '外來詞': 'loanword',
    '外来词': 'loanword',
    '借詞': 'loanword',
    '借词': 'loanword',
    '音譯詞': 'transliteration',
    '音译词': 'transliteration',
    '音譯': 'transliteration',
    '敬語': 'polite language',
    '敬语': 'polite language',
    '謙語': 'humble language',
    '谦语': 'humble language',
    '委婉語': 'euphemism',
    '委婉语': 'euphemism',
    '粗話': 'vulgar language',
    '粗话': 'vulgar language',
    '俚語字': 'slang',
    '書面語': 'written language',
    '书面语': 'written language',
    '粵語': 'Cantonese',
    '廣東話': 'Cantonese',
    '广东话': 'Cantonese',
    '國語': 'Mandarin',
    '國語詞': 'Mandarin',
    '普通話': 'Mandarin',
    '普通话': 'Mandarin',
    '語': 'word',
    '語句': 'sentence',
    '语句': 'sentence',
    '句子': 'sentence',
    '句': 'sentence',
    '成句': 'sentence',
    '話': 'word',
    '話語': 'expression',
    '话语': 'expression',
    '句詞': 'sentence word',
    '句词': 'sentence word',
    '證態詞': 'verbal noun',
    '動詞片語': 'verb phrase',
    '名词短语': 'noun phrase',
    '名詞短語': 'noun phrase',
    '介系詞': 'preposition',
    '介系词': 'preposition',
    '前置詞': 'preposition',
    '前置词': 'preposition',
    '連接詞': 'conjunction',
    '连接词': 'conjunction',
    '複合形容詞': 'compound adjective',
    '專名': 'proper noun',
    '专名': 'proper noun',
    '香港': 'Hong Kong',
    '外來語': 'loanword',
    '外来语': 'loanword',
    '黃賭毒': 'vice',
    '黄赌毒': 'vice',
    '粗俗': 'vulgar',
    '潮語': 'trendy slang',
    '潮语': 'trendy slang',
    '文言': 'classical Chinese',
    '台灣': 'Taiwan',
    '台湾': 'Taiwan',
    '大陸': 'Mainland China',
    '大陆': 'Mainland China',
    '爭議': 'controversial',
    '争议': 'controversial',
    '口語': 'spoken language',
    '口语': 'spoken language',
    '錯字': 'wrong character',
    '错字': 'wrong character',
    '舊式': 'old-fashioned',
    '旧式': 'old-fashioned',
    '玩嘢': 'playful',
    '澳門': 'Macau',
    '澳门': 'Macau',
    '馬來西亞': 'Malaysia',
    '马来西亚': 'Malaysia',
    '民間傳說': 'folk legend',
    '民間傳説': 'folk legend',
    '民间传说': 'folk legend',
}

POS_ABBREVIATIONS = {
    'n': 'noun',
    'v': 'verb',
    'vt': 'verb',
    'vi': 'verb',
    'aux': 'auxiliary',
    'adj': 'adjective',
    'a': 'adjective',
    'adv': 'adverb',
    'pron': 'pronoun',
    'conj': 'conjunction',
    'interj': 'interjection',
    'excl': 'interjection',
    'prep': 'preposition',
    'art': 'article',
    'num': 'numeral',
    'modal': 'modal particle',
    'det': 'determiner',
    'phr': 'phrase',
    'abbr': 'abbreviation',
}

LEADING_POS_ABBREVIATION = re.compile(
    r"^(?:n|v|vt|vi|adj|adv|pron|conj|interj|prep|art|num|aux|modal|det|phr|abbr|excl)\.?\s+",
    re.IGNORECASE,
)
TAG_SEPARATORS = re.compile(r"[,、|;；/／]")
INVISIBLE_ALIAS_CHARS = re.compile(r"[\u200B-\u200D\uFEFF]")
ALTERNATIVE_SLASHES = str.maketrans({"／": "/", "∕": "/", "⁄": "/"})



# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def get_json(
    s: requests.Session,
    url: str,
    timeout: int = 60,
):
    response = s.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


def download_words_hk_bulk(
    s: requests.Session,
) -> tuple[bytes, str]:
    """Perform the Words.hk CSRF negotiation and download the bulk CSV."""

    r = s.get(REQUEST_DATA_URL, timeout=30)
    r.raise_for_status()

    match = re.search(
        r'name="csrfmiddlewaretoken"\s+value="([^"]+)"',
        r.text,
    )

    if not match:
        raise RuntimeError("Could not find Words.hk CSRF token")

    token = match.group(1)

    cookies = s.cookies.get_dict()

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": REQUEST_DATA_URL,
        "Origin": WORDS_HK,
    }

    if "csrftoken" in cookies:
        headers["Cookie"] = f"csrftoken={cookies['csrftoken']}"

    post = s.post(
        REQUEST_DATA_URL,
        headers=headers,
        data={"csrfmiddlewaretoken": token},
        timeout=60,
    )

    post.raise_for_status()

    links = re.findall(
        r'href="([^"]+all-[^"]+\.csv\.gz)"',
        post.text,
    )

    if not links:
        raise RuntimeError(
            "Could not find all-*.csv.gz in Words.hk response"
        )

    href = links[0]
    url = urljoin(WORDS_HK, href)

    response = s.get(url, timeout=180)
    response.raise_for_status()

    return response.content, url


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def decode_maybe_gzip(data: bytes) -> str:
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)

    return data.decode("utf-8", errors="replace")


def normalize_jyutping(value: str) -> str:
    """
    Remove tone numbers while preserving syllable boundaries.

    Example:
        "maa5 maa1" -> "maa maa"

    Multiple alternatives remain separated by '/'.
    """

    if not value:
        return ""

    alternatives = []

    for alternative in value.split("/"):
        alternative = alternative.strip()

        if not alternative:
            continue

        normalized = re.sub(
            r"[1-6]",
            "",
            alternative.lower(),
        )

        normalized = re.sub(
            r"\s+",
            " ",
            normalized,
        ).strip()

        if normalized:
            alternatives.append(normalized)

    # Preserve order but remove duplicates.
    result = []
    seen = set()

    for item in alternatives:
        if item not in seen:
            seen.add(item)
            result.append(item)

    return "/".join(result)


def normalize_english(value: str) -> str:
    """
    Normalize English search terms.

    Examples:
        "Highlight!" -> "highlight"
        "right-away" -> "right away"
    """

    if not value:
        return ""

    value = value.lower().strip()

    value = re.sub(
        r"[^\w\s'-]",
        " ",
        value,
        flags=re.UNICODE,
    )

    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_tag(tag: str) -> str:
    """Translate one POS/label tag to its display-ready English name."""
    text = tag.strip()
    if not text:
        return ""

    abbreviated = POS_ABBREVIATIONS.get(text.replace(".", "").lower())
    if abbreviated:
        return abbreviated

    text = LEADING_POS_ABBREVIATION.sub("", text).strip()
    if not text:
        return ""

    abbreviated = POS_ABBREVIATIONS.get(text.replace(".", "").lower())
    return abbreviated or PART_OF_SPEECH_NAMES.get(text, text)


def normalize_tag_list(raw: str) -> str:
    """Translate, split and deduplicate the tags exactly once at build time."""
    if not raw.strip():
        return ""
    result = []
    seen = set()
    for part in TAG_SEPARATORS.split(raw):
        value = normalize_tag(part)
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return ", ".join(result)


def clean_dictionary_alias(value: str) -> str:
    """Mirror the tokenizer's alias cleanup while preparing dictionary_words."""
    return INVISIBLE_ALIAS_CHARS.sub("", value).translate(ALTERNATIVE_SLASHES).strip()


def dictionary_aliases(value: str) -> list[str]:
    """Expand only slash-separated spelling alternatives, not word characters."""
    normalized = clean_dictionary_alias(value)
    result = []
    seen = set()
    for part in normalized.split("/"):
        alias = clean_dictionary_alias(part)
        if alias and alias not in seen:
            seen.add(alias)
            result.append(alias)
    return result


def example_ruby(cantonese: str) -> list[dict[str, str]]:
    """Extract explicit Jyutping supplied in an example, if it is unambiguous."""
    match = re.search(r"\(([^)]+)\)", cantonese)
    if not match:
        return []

    raw_reading = match.group(1).strip()
    if not re.search(r"[1-6]", raw_reading):
        return []
    if not re.fullmatch(r"[a-z0-9]+(?:[\s/|,]+[a-z0-9]+)*", raw_reading, re.IGNORECASE):
        return []

    jyutping = re.sub(r"[^a-z0-9\s]", " ", raw_reading, flags=re.IGNORECASE).strip()
    chinese = cantonese[:match.start()].strip()
    cleaned = re.sub(r"[#\s，。！？、；：]", "", chinese)
    syllables = [part for part in re.split(r"\s+", jyutping) if part]
    characters = list(cleaned)
    if not characters or len(characters) != len(syllables):
        return []
    return [
        {"character": character, "reading": reading}
        for character, reading in zip(characters, syllables)
    ]


def extract_variant(field: str) -> str:
    field = field.strip()

    if not field:
        return ""

    if " " in field or "\n" in field:
        return ""

    if field == "未有內容 NO DATA":
        return ""

    if "NO DATA" in field:
        return ""

    if not re.search(
        r"[\u3400-\u4dbf\u4e00-\u9fff]",
        field,
    ):
        return ""

    return field


def union_values(a: str, b: str) -> str:
    if not a:
        return b

    if not b:
        return a

    result = []
    seen = set()

    for raw in f"{a}/{b}".split("/"):
        value = raw.strip()

        if value and value not in seen:
            seen.add(value)
            result.append(value)

    return "/".join(result)


def parse_word_jyutping_field(
    field: str,
) -> list[tuple[str, str]]:
    result = []

    for segment in field.split(","):
        segment = segment.strip()

        if not segment:
            continue

        if ":" not in segment:
            result.append((segment, ""))
            continue

        word, jp = segment.split(":", 1)

        word = word.strip()
        jp = jp.strip()

        if word:
            result.append((word, jp))

    return result


# ---------------------------------------------------------------------------
# Language extraction
# ---------------------------------------------------------------------------

def extract_lang_text(
    text: str,
    prefix: str,
) -> str:
    lines = text.split("\n")

    buffer = []
    found = False

    stop_markers = (
        "yue:",
        "eng:",
        "<",
        "(pos:",
        "*(廣東話)*",
        "*(英文)*",
        "*(粵)*",
        "*(英)*",
    )

    for line in lines:
        if line.startswith(prefix):
            found = True
            buffer.append(line[len(prefix):])

        elif found:
            if any(
                line.startswith(marker) or marker in line
                for marker in stop_markers
            ):
                break

            buffer.append("\n" + line)

    return "".join(buffer).strip()


# ---------------------------------------------------------------------------
# Words.hk explanation parser
# ---------------------------------------------------------------------------

def parse_all_csv_content(content: str) -> dict:
    definitions = []
    pos_list = []
    tags = []
    senses = []

    for sense in content.split("----"):
        explanation_lines = []
        example_blocks: list[list[str]] = []
        current_example: list[str] | None = None
        current = None

        for line in sense.split("\n"):
            trimmed = line.strip()

            if trimmed.startswith("<explanation>"):
                current = "explanation"
                continue

            if trimmed.startswith("<eg>"):
                current = "eg"
                current_example = []
                example_blocks.append(current_example)
                continue

            if trimmed.startswith("(pos:"):
                for match in re.finditer(
                    r"pos:([^)]+)",
                    trimmed,
                ):
                    value = match.group(1).strip()

                    if value and value not in pos_list:
                        pos_list.append(value)

                for match in re.finditer(
                    r"label:([^)]+)",
                    trimmed,
                ):
                    value = match.group(1).strip()

                    if value and value not in tags:
                        tags.append(value)

                continue

            if current == "explanation":
                explanation_lines.append(trimmed)

            elif current == "eg":
                if trimmed:
                    if current_example is None:
                        current_example = []
                        example_blocks.append(current_example)
                    current_example.append(trimmed)

            elif (
                trimmed.startswith(("yue:", "eng:"))
                or "*(廣東話)*" in trimmed
                or "*(英文)*" in trimmed
                or "*(粵)*" in trimmed
                or "*(英)*" in trimmed
            ):
                explanation_lines.append(trimmed)

        explanation = "\n".join(
            x for x in explanation_lines if x
        )

        english_main = extract_lang_text(
            explanation,
            "*(英文)*",
        )

        english_part = extract_lang_text(
            explanation,
            "eng:",
        )

        english_definition = (
            english_main.strip()
            if english_main
            else english_part.strip()
        )

        if english_definition:
            definitions.append(english_definition)

        sense_example_details = []

        for example_lines in example_blocks:
            example = "\n".join(example_lines)
            cantonese = (
                extract_lang_text(example, "*(粵)*")
                or extract_lang_text(example, "yue:")
            )

            english = (
                extract_lang_text(example, "*(英)*")
                or extract_lang_text(example, "eng:")
            )

            if not cantonese and not english:
                continue

            detail = {
                "cantonese": cantonese,
                "english": english,
                "ruby": example_ruby(cantonese),
            }
            if (cantonese or english) and detail not in sense_example_details:
                sense_example_details.append(detail)

        if english_definition or sense_example_details:
            senses.append(
                {
                    "definition": english_definition,
                    "meaningLines": definition_lines(english_definition),
                    "exampleDetails": sense_example_details,
                }
            )

    return {
        "definition": "\n\n".join(definitions),
        "definitions": definitions,
        "partOfSpeech": normalize_tag_list(", ".join(pos_list)),
        "tags": normalize_tag_list(", ".join(tags)),
        "senses": senses,
    }


# ---------------------------------------------------------------------------
# Ruby
# ---------------------------------------------------------------------------

def build_word_ruby(
    word: str,
    jyutping: str,
) -> list[dict[str, str]]:
    if not jyutping:
        return []

    alternatives = [
        value.strip()
        for value in re.split(r"[:/]", jyutping)
        if value.strip()
    ]

    syllable_sets = []

    for pronunciation in alternatives:
        syllables = [
            re.sub(r"[^a-z0-9]", "", value.lower())
            for value in pronunciation.split()
        ]

        syllables = [
            value for value in syllables if value
        ]

        syllable_sets.append(syllables)

    chars = list(word)

    if not syllable_sets:
        return []

    if any(
        len(syllables) != len(chars)
        for syllables in syllable_sets
    ):
        return []

    result = []

    for index, character in enumerate(chars):
        readings = sorted(
            {
                syllables[index]
                for syllables in syllable_sets
                if syllables[index]
            }
        )

        result.append(
            {
                "character": character,
                "reading": "/".join(readings),
            }
        )

    return result


def build_combined_word_ruby(
    word: str,
    pronunciation: str,
) -> list[dict[str, str]]:
    """
    Handles combined entries such as:

        行/行:haang4/hang4

    """

    words = [
        value.strip()
        for value in word.split("/")
        if value.strip()
    ]

    readings = [
        value.strip()
        for value in pronunciation.split("/")
        if value.strip()
    ]

    result = []

    for index, current_word in enumerate(words):
        reading = (
            readings[index]
            if index < len(readings)
            else (
                readings[-1]
                if readings
                else ""
            )
        )

        ruby = build_word_ruby(
            current_word,
            reading,
        )

        if ruby:
            result.extend(ruby)

        if index < len(words) - 1:
            result.append(
                {
                    "character": "/",
                    "reading": "",
                }
            )

    return result


# ---------------------------------------------------------------------------
# Bulk dictionary
# ---------------------------------------------------------------------------

def parse_bulk_csv(
    csv_text: str,
) -> dict[str, dict]:

    merged: OrderedDict[str, dict] = OrderedDict()

    reader = csv.reader(
        io.StringIO(csv_text)
    )

    for row in reader:
        if len(row) < 3:
            continue

        word_jp = row[1].strip()
        content = row[2].strip()
        variant_field = (
            row[3].strip()
            if len(row) > 3
            else ""
        )

        if not word_jp:
            continue

        variants = parse_word_jyutping_field(
            word_jp
        )

        if not variants:
            continue

        parsed = parse_all_csv_content(content)

        combined_word = "/".join(
            word
            for word, _ in variants
            if word
        )

        combined_jp = "/".join(
            jp
            for _, jp in variants
            if jp
        )

        if not combined_word:
            continue

        variant = extract_variant(
            variant_field
        )

        dictionary_key = (
            f"{combined_word}/{variant}"
            if variant
            else combined_word
        )

        normalized = normalize_jyutping(
            combined_jp
        )

        if dictionary_key not in merged:
            merged[dictionary_key] = {
                "word": dictionary_key,
                "pronunciation": combined_jp,
                "pronunciation_normalized": normalized,
                "definition": parsed["definition"],
                "part_of_speech": parsed["partOfSpeech"],
                "level": "",
                "tags": parsed["tags"],
                "definitions": list(parsed["definitions"]),
                "synonyms": "",
                "related_words": "",
                "character_meanings": "",
                "antonyms": "",
                "usage_notes": "",
                "word_ruby": "",
                "senses": list(parsed["senses"]),
                "frequency": 0,
            }

        entry = merged[dictionary_key]

        entry["pronunciation"] = union_values(
            entry["pronunciation"],
            combined_jp,
        )

        entry["pronunciation_normalized"] = (
            normalize_jyutping(
                entry["pronunciation"]
            )
        )

        if parsed["definition"]:
            entry["definition"] = (
                parsed["definition"]
            )

        if parsed["partOfSpeech"]:
            entry["part_of_speech"] = (
                parsed["partOfSpeech"]
            )

        if parsed["tags"]:
            entry["tags"] = parsed["tags"]

        for definition in parsed["definitions"]:
            if definition not in entry["definitions"]:
                entry["definitions"].append(
                    definition
                )

        for sense in parsed["senses"]:
            existing = next(
                (
                    item
                    for item in entry["senses"]
                    if item["definition"]
                    == sense["definition"]
                ),
                None,
            )

            if existing is None:
                entry["senses"].append(
                    {
                        "definition": sense["definition"],
                        "meaningLines": list(sense.get("meaningLines", [])),
                        "exampleDetails": list(
                            sense["exampleDetails"]
                        ),
                    }
                )

            else:
                for line in sense.get("meaningLines", []):
                    if line not in existing.setdefault("meaningLines", []):
                        existing["meaningLines"].append(line)
                for detail in sense["exampleDetails"]:
                    if detail not in existing["exampleDetails"]:
                        existing["exampleDetails"].append(detail)

        ruby = build_combined_word_ruby(
            dictionary_key,
            entry["pronunciation"],
        )

        entry["word_ruby"] = json.dumps(
            ruby,
            ensure_ascii=False,
            separators=(",", ":"),
        ) if ruby else ""

    for entry in merged.values():
        # `definition` is the sole searchable/displayable definition text. Keep
        # every distinct definition merged for variants rather than the last row.
        entry["definition"] = "\n\n".join(entry["definitions"])

    return merged


# ---------------------------------------------------------------------------
# English index
# ---------------------------------------------------------------------------

def extract_cantonese_words(
    text: str,
) -> list[str]:

    result = []

    for segment in text.strip().split(","):
        value = segment.strip()

        if not value:
            continue

        paren = value.find(" (")

        if paren != -1:
            value = value[:paren].strip()

        else:
            colon = value.find(":")

            if colon != -1:
                value = value[:colon].strip()

        if value:
            result.append(value)

    return result


def parse_english_index(
    data,
) -> list[tuple[str, str]]:

    if not isinstance(data, dict):
        raise ValueError(
            "English index is not a JSON object"
        )

    result = []

    for raw_key, raw_value in data.items():

        english = normalize_english(
            str(raw_key).lstrip("!")
        )

        if not english:
            continue

        items = (
            raw_value
            if isinstance(raw_value, list)
            else [raw_value]
        )

        for item in items:

            if isinstance(item, str):
                raw = item

            elif isinstance(item, list) and item:
                raw = str(item[0])

            elif (
                isinstance(item, dict)
                and "word" in item
            ):
                raw = str(item["word"])

            else:
                continue

            for cantonese_word in extract_cantonese_words(raw):
                result.append(
                    (
                        english,
                        cantonese_word,
                    )
                )

    return result


# ---------------------------------------------------------------------------
# Frequency
# ---------------------------------------------------------------------------

def safe_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def frequency_for_word(
    word: str,
    frequency: dict,
) -> int:

    candidates = [
        word,
        *word.split("/"),
    ]

    best = 0

    for candidate in candidates:
        value = safe_int(
            frequency.get(candidate, 0)
        )

        if value > best:
            best = value

    return best


def calculate_frequency_bands(
    frequencies: list[int],
) -> dict[int, int]:
    """
    Convert raw existing-word-count frequency into a stable 1-5 band.

    Higher frequency = more common.

        5 = very common
        4 = common
        3 = medium
        2 = uncommon
        1 = rare
        0 = no frequency data

    Percentile-style thresholds are calculated from the actual dictionary
    distribution rather than hard-coded raw frequency values.
    """

    positive = sorted(
        set(
            value
            for value in frequencies
            if value > 0
        ),
        reverse=True,
    )

    if not positive:
        return {}

    def percentile(index: float) -> int:
        position = int(
            round(
                (len(positive) - 1)
                * index
            )
        )

        position = max(
            0,
            min(
                len(positive) - 1,
                position,
            ),
        )

        return positive[position]

    # Top 1%, top 5%, top 20%, top 50%.
    thresholds = {
        5: percentile(0.01),
        4: percentile(0.05),
        3: percentile(0.20),
        2: percentile(0.50),
    }

    result = {}

    for frequency in positive:
        if frequency >= thresholds[5]:
            band = 5
        elif frequency >= thresholds[4]:
            band = 4
        elif frequency >= thresholds[3]:
            band = 3
        elif frequency >= thresholds[2]:
            band = 2
        else:
            band = 1

        result[frequency] = band

    return result


def calculate_frequency_labels(entries: list[dict]) -> dict[str, str]:
    """Precompute the six display labels previously recalculated by Flutter."""
    positive = sorted(
        (entry for entry in entries if entry["frequency"] > 0),
        key=lambda entry: (-entry["frequency"], entry["word"]),
    )
    if not positive:
        return {entry["word"]: "" for entry in entries}

    ranks = (100, 500, 1500, 3000, 10000)
    thresholds = [
        positive[min(rank - 1, len(positive) - 1)]["frequency"]
        for rank in ranks
    ]
    labels = ("Very common", "Common", "Frequent", "Less common", "Uncommon", "Rare")
    result = {}
    for entry in entries:
        frequency = entry["frequency"]
        if frequency <= 0:
            result[entry["word"]] = ""
            continue
        label = labels[-1]
        for index, threshold in enumerate(thresholds):
            if frequency >= threshold:
                label = labels[index]
                break
        result[entry["word"]] = label
    return result


def definition_lines(value: str) -> list[str]:
    """Return the display-ready English meaning lines for a definition block."""
    result = []
    for line in value.splitlines():
        text = line.strip()
        if not text:
            continue
        if text.startswith("(Eng.)"):
            text = text[len("(Eng.)"):].strip()
        elif text.startswith("*(英)*"):
            text = text[len("*(英)*"):].strip()
        elif text.startswith("(英)"):
            text = text[len("(英)"):].strip()
        elif text.startswith(("(Cant.)", "*(廣東話)*", "(廣東話)", "*(粵)*", "(粵)")):
            continue
        if text:
            result.append(text)
    return result


def gloss_text_for_entry(entry: dict) -> str:
    """Precompute the character-gloss text formerly assembled in Flutter."""
    parts = []
    seen = set()
    raw_values = [entry.get("definition", "")]
    raw_values.extend(
        sense.get("definition", "")
        for sense in entry.get("senses", [])
        if isinstance(sense, dict)
    )
    for raw in raw_values:
        for line in definition_lines(str(raw or "")):
            cleaned = re.sub(r"\s+", " ", line)
            cleaned = re.sub(r"[;；,，、:：]+$", "", cleaned).strip()
            folded = cleaned.casefold()
            if cleaned and folded not in seen:
                seen.add(folded)
                parts.append(cleaned)
    if not parts:
        return ""

    kept = []
    length = 0
    for part in parts:
        if length + len(part) > 420:
            break
        kept.append(part)
        length += len(part) + 2
    omitted = len(parts) - len(kept)
    text = "; ".join(kept)
    return f"{text}; …{omitted} more" if omitted > 0 else text


_CJK_CHARACTER = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")


def _unique_cjk_characters(word: str) -> list[str]:
    result = []
    seen = set()
    for character in word:
        if _CJK_CHARACTER.fullmatch(character) and character not in seen:
            seen.add(character)
            result.append(character)
    return result


def _character_variant_index(entries: dict[str, dict]) -> dict[str, dict]:
    """Index slash aliases once for character-gloss fallback lookups."""
    index: dict[str, dict] = {}
    for entry in entries.values():
        for alias in dictionary_aliases(entry.get("word", "")):
            current = index.get(alias)
            if current is None or entry.get("frequency", 0) > current.get("frequency", 0):
                index[alias] = entry
    return index


def _lookup_entry_for_word(
    word: str,
    entries: dict[str, dict],
    variant_index: dict[str, dict],
) -> dict | None:
    """Mirror exact-first, then highest-frequency slash-variant lookup."""
    exact = entries.get(word)
    if exact is not None:
        return exact
    return variant_index.get(word)


def preprocess_character_data(
    entries: dict[str, dict],
    char_csv: str,
    char_frequency: dict,
) -> dict[str, tuple[str, int, str, str]]:
    """Build character readings and structured glosses before shipping."""
    character_map: dict[str, tuple[str, int]] = {}
    char_reader = csv.reader(io.StringIO(char_csv))
    for row in char_reader:
        if len(row) < 2:
            continue
        character = row[0].strip()
        jyutping = row[1].strip()
        if (not character or not jyutping or character.lower() == "source"
                or "http" in character.lower()):
            continue
        character_map[character] = (jyutping, safe_int(char_frequency.get(character, 0)))

    # The official character list wins. Fill gaps from word ruby in frequency order,
    # the same precedence the old Flutter startup scan used.
    for entry in sorted(entries.values(), key=lambda item: (-item["frequency"], item["word"])):
        try:
            ruby_items = json.loads(entry.get("word_ruby") or "[]")
        except (TypeError, json.JSONDecodeError):
            continue
        for item in ruby_items:
            if not isinstance(item, dict):
                continue
            character = str(item.get("character", "")).strip()
            reading = str(item.get("reading", "")).strip()
            if not character or character == "/":
                continue
            if character not in character_map and reading:
                character_map[character] = (
                    reading,
                    safe_int(char_frequency.get(character, 0)),
                )

    # Also represent characters found in dictionary words even where a source did
    # not supply ruby. A blank reading is preferable to dropping the character.
    for entry in entries.values():
        for character in _unique_cjk_characters(entry["word"]):
            if character not in character_map:
                character_map[character] = (
                    "",
                    safe_int(char_frequency.get(character, 0)),
                )
    for character, entry in entries.items():
        if len(_unique_cjk_characters(character)) == 1 and character in character_map:
            current_reading, current_frequency = character_map[character]
            if not current_reading and entry.get("pronunciation"):
                character_map[character] = (entry["pronunciation"], current_frequency)

    variant_index = _character_variant_index(entries)
    output: dict[str, tuple[str, int, str, str]] = {}
    for character, (jyutping, frequency) in character_map.items():
        character_entry = _lookup_entry_for_word(character, entries, variant_index)
        pronunciation = (
            str(character_entry.get("pronunciation", ""))
            if character_entry is not None
            else ""
        )
        gloss = gloss_text_for_entry(character_entry) if character_entry else ""
        if not gloss:
            gloss = "No definition."
        output[character] = (jyutping, frequency, pronunciation, gloss)

    # Character breakdowns are structured JSON, not formatted text. The app can
    # render this directly and no longer needs to guess whether text after a
    # character is Jyutping, a gloss, or a separator.
    for entry in entries.values():
        if entry.get("character_meanings"):
            continue
        characters = _unique_cjk_characters(entry["word"])
        if len(characters) < 2:
            continue
        details = []
        for character in characters:
            prepared = output.get(character)
            if prepared is None:
                details.append({
                    "character": character,
                    "pronunciation": "",
                    "gloss": "No definition.",
                })
            else:
                details.append({
                    "character": character,
                    "pronunciation": prepared[2],
                    "gloss": prepared[3],
                })
        entry["character_meanings"] = json.dumps(
            details, ensure_ascii=False, separators=(",", ":")
        )
    return output


# ---------------------------------------------------------------------------
# SQLite schema
# ---------------------------------------------------------------------------

def create_schema(
    conn: sqlite3.Connection,
) -> None:

    conn.executescript(
        """
        PRAGMA journal_mode = DELETE;
        PRAGMA synchronous = NORMAL;
        PRAGMA foreign_keys = ON;
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

            UNIQUE(
                english_word,
                cantonese_word
            )
        );

        CREATE TABLE database_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE dictionary_words (
            word TEXT PRIMARY KEY NOT NULL
        );

        CREATE INDEX idx_dictionary_word
            ON dictionary_entries(word);

        CREATE INDEX idx_dictionary_pronunciation
            ON dictionary_entries(pronunciation);

        CREATE INDEX idx_dictionary_pronunciation_normalized
            ON dictionary_entries(pronunciation_normalized);

        CREATE INDEX idx_dictionary_frequency
            ON dictionary_entries(frequency DESC);

        CREATE INDEX idx_dictionary_frequency_band
            ON dictionary_entries(frequency_band DESC);

        CREATE INDEX idx_dictionary_frequency_label
            ON dictionary_entries(frequency_label);

        CREATE INDEX idx_dictionary_words_word
            ON dictionary_words(word);

        CREATE INDEX idx_characters_character
            ON characters(character);

        CREATE INDEX idx_characters_jyutping
            ON characters(jyutping);

        CREATE INDEX idx_characters_frequency
            ON characters(frequency DESC);

        CREATE INDEX idx_english_word
            ON english_index(english_word);

        CREATE INDEX idx_english_normalized
            ON english_index(english_normalized);

        CREATE INDEX idx_english_cantonese
            ON english_index(cantonese_word);

        CREATE INDEX idx_english_rank
            ON english_index(
                english_normalized,
                rank
            );
        """
    )


# ---------------------------------------------------------------------------
# Database build
# ---------------------------------------------------------------------------

def build_database(
    out_db: Path,
    bulk_bytes: bytes,
    bulk_url: str,
    frequency: dict,
    char_frequency: dict,
    char_csv: str,
    english_index_data: dict,
) -> dict:

    if out_db.exists():
        out_db.unlink()

    conn = sqlite3.connect(out_db)

    try:
        create_schema(conn)

        # ---------------------------------------------------------------
        # Parse dictionary
        # ---------------------------------------------------------------

        bulk_text = decode_maybe_gzip(
            bulk_bytes
        )

        entries = parse_bulk_csv(
            bulk_text
        )

        # ---------------------------------------------------------------
        # Apply word frequency
        # ---------------------------------------------------------------

        for entry in entries.values():
            entry["frequency"] = frequency_for_word(
                entry["word"],
                frequency,
            )

        frequency_bands = calculate_frequency_bands(
            [entry["frequency"] for entry in entries.values()]
        )
        frequency_labels = calculate_frequency_labels(list(entries.values()))

        for entry in entries.values():
            entry["frequency_band"] = frequency_bands.get(entry["frequency"], 0)
            entry["frequency_label"] = frequency_labels.get(entry["word"], "")

            # The app consumes ready-to-render senses; `senses` is the canonical
            # home for meaning lines and structured examples.
            if not entry["senses"]:
                fallback_definitions = list(entry["definitions"])
                if not fallback_definitions and entry["definition"]:
                    fallback_definitions = [entry["definition"]]
                entry["senses"] = [
                    {
                        "definition": definition,
                        "meaningLines": definition_lines(definition),
                        "exampleDetails": [],
                    }
                    for definition in fallback_definitions
                ]

        character_map = preprocess_character_data(entries, char_csv, char_frequency)

        # ---------------------------------------------------------------
        # Dictionary rows
        # ---------------------------------------------------------------

        rows = []

        for entry in entries.values():

            rows.append(
                (
                    entry["word"],
                    entry["pronunciation"],
                    entry["pronunciation_normalized"],
                    entry["definition"],
                    json.dumps(
                        entry["senses"],
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    if entry["senses"]
                    else "",
                    entry["part_of_speech"],
                    entry["level"],
                    entry["tags"],
                    entry["synonyms"],
                    entry["related_words"],
                    entry["character_meanings"],
                    entry["antonyms"],
                    entry["usage_notes"],
                    entry["word_ruby"],
                    entry["frequency"],
                    entry["frequency_band"],
                    entry["frequency_label"],
                )
            )

        conn.executemany(
            """
            INSERT INTO dictionary_entries (
                word,
                pronunciation,
                pronunciation_normalized,
                definition,
                senses,
                part_of_speech,
                level,
                tags,
                synonyms,
                related_words,
                character_meanings,
                antonyms,
                usage_notes,
                word_ruby,
                frequency,
                frequency_band,
                frequency_label
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?
            )
            """,
            rows,
        )

        # ---------------------------------------------------------------
        # Characters
        # ---------------------------------------------------------------

        conn.executemany(
            """
            INSERT OR REPLACE INTO characters (
                character, jyutping, frequency, gloss_pronunciation, gloss
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (character, jyutping, frequency, gloss_pronunciation, gloss)
                for character, (jyutping, frequency, gloss_pronunciation, gloss)
                in character_map.items()
            ],
        )

        # ---------------------------------------------------------------
        # English index
        # ---------------------------------------------------------------

        raw_english_rows = parse_english_index(
            english_index_data
        )

        # Remove duplicates first.
        unique_pairs = sorted(
            set(raw_english_rows)
        )

        # Only index Cantonese words that actually exist
        # in the dictionary.
        existing_words = {
            row[0]
            for row in conn.execute(
                "SELECT word FROM dictionary_entries"
            )
        }

        filtered = [
            (
                english,
                cantonese,
            )
            for english, cantonese
            in unique_pairs
            if cantonese in existing_words
        ]

        # Rank each English meaning by the frequency of
        # its Cantonese result.
        grouped: dict[str, list[str]] = {}

        for english, cantonese in filtered:
            grouped.setdefault(
                english,
                [],
            ).append(cantonese)

        english_rows = []

        for english, cantonese_words in grouped.items():

            cantonese_words.sort(
                key=lambda word: (
                    -frequency_for_word(
                        word,
                        frequency,
                    ),
                    len(word),
                    word,
                )
            )

            for rank, cantonese in enumerate(
                cantonese_words,
                start=1,
            ):
                english_rows.append(
                    (
                        english,
                        normalize_english(
                            english
                        ),
                        cantonese,
                        rank,
                    )
                )

        dictionary_word_aliases = sorted({
            alias
            for entry in entries.values()
            for alias in dictionary_aliases(entry["word"])
        })
        conn.executemany(
            "INSERT OR IGNORE INTO dictionary_words(word) VALUES (?)",
            [(word,) for word in dictionary_word_aliases],
        )

        conn.executemany(
            """
            INSERT OR IGNORE INTO english_index (
                english_word,
                english_normalized,
                cantonese_word,
                rank
            )
            VALUES (?, ?, ?, ?)
            """,
            english_rows,
        )

        # ---------------------------------------------------------------
        # Metadata
        # ---------------------------------------------------------------

        built_at = datetime.now(
            timezone.utc
        ).isoformat()

        metadata = {
            "schema_version": str(
                SCHEMA_VERSION
            ),
            "language": "yue",
            "language_name": "Cantonese",
            "source_dictionary": "Words.hk",
            "source_bulk_url": bulk_url,
            "frequency_url": FREQUENCY_URL,
            "character_frequency_url": (
                CHAR_FREQUENCY_URL
            ),
            "charlist_url": CHARLIST_URL,
            "english_index_url": (
                ENGLISH_INDEX_URL
            ),
            "built_at_utc": built_at,
            "frequency_band_definition": (
                "5=very common, "
                "4=common, "
                "3=medium, "
                "2=uncommon, "
                "1=rare, "
                "0=no data"
            ),
            "preprocessing": (
                "POS/tags, frequency labels, word ruby, example ruby, "
                "character readings/glosses, subtitle aliases/max length, and sense meaning lines"
            ),
            "dictionary_word_max_length": str(
                max((len(word) for word in dictionary_word_aliases), default=1)
            ),
            "license_note": (
                "Review current Words.hk "
                "licensing/attribution requirements "
                "before redistribution."
            ),
        }

        conn.executemany(
            """
            INSERT INTO database_metadata(
                key,
                value
            )
            VALUES (?, ?)
            """,
            metadata.items(),
        )

        conn.commit()

        # ---------------------------------------------------------------
        # Statistics
        # ---------------------------------------------------------------

        stats = {
            "dictionary_entries": conn.execute(
                """
                SELECT COUNT(*)
                FROM dictionary_entries
                """
            ).fetchone()[0],

            "frequency_nonzero": conn.execute(
                """
                SELECT COUNT(*)
                FROM dictionary_entries
                WHERE frequency > 0
                """
            ).fetchone()[0],

            "frequency_band_5": conn.execute(
                """
                SELECT COUNT(*)
                FROM dictionary_entries
                WHERE frequency_band = 5
                """
            ).fetchone()[0],

            "frequency_band_4": conn.execute(
                """
                SELECT COUNT(*)
                FROM dictionary_entries
                WHERE frequency_band = 4
                """
            ).fetchone()[0],

            "frequency_band_3": conn.execute(
                """
                SELECT COUNT(*)
                FROM dictionary_entries
                WHERE frequency_band = 3
                """
            ).fetchone()[0],

            "frequency_band_2": conn.execute(
                """
                SELECT COUNT(*)
                FROM dictionary_entries
                WHERE frequency_band = 2
                """
            ).fetchone()[0],

            "frequency_band_1": conn.execute(
                """
                SELECT COUNT(*)
                FROM dictionary_entries
                WHERE frequency_band = 1
                """
            ).fetchone()[0],

            "characters": conn.execute(
                """
                SELECT COUNT(*)
                FROM characters
                """
            ).fetchone()[0],
            "characters_with_gloss": conn.execute(
                "SELECT COUNT(*) FROM characters WHERE gloss <> ''"
            ).fetchone()[0],

            "english_index": conn.execute(
                "SELECT COUNT(*) FROM english_index"
            ).fetchone()[0],
            "dictionary_words": conn.execute(
                "SELECT COUNT(*) FROM dictionary_words"
            ).fetchone()[0],
            "dictionary_word_max_length": max(
                (len(word) for word in dictionary_word_aliases), default=1
            ),
            "entries_with_part_of_speech": conn.execute(
                "SELECT COUNT(*) FROM dictionary_entries WHERE part_of_speech <> ''"
            ).fetchone()[0],

            "entries_with_ruby": conn.execute(
                """
                SELECT COUNT(*)
                FROM dictionary_entries
                WHERE word_ruby <> ''
                """
            ).fetchone()[0],

            "entries_with_senses": conn.execute(
                """
                SELECT COUNT(*)
                FROM dictionary_entries
                WHERE senses <> ''
                """
            ).fetchone()[0],
        }

        return stats

    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate(
    db: Path,
) -> None:

    conn = sqlite3.connect(db)

    try:
        required_tables = {
            "dictionary_entries",
            "characters",
            "english_index",
            "database_metadata",
            "dictionary_words",
        }

        actual_tables = {
            row[0]
            for row in conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table'
                """
            )
        }

        missing = (
            required_tables - actual_tables
        )

        if missing:
            raise RuntimeError(
                f"Missing tables: {sorted(missing)}"
            )

        # The shipped dictionary DB is intentionally small and self-contained.
        # Reject legacy/accidental tables instead of silently publishing them.
        unexpected = (
            actual_tables - required_tables
        )

        if unexpected:
            raise RuntimeError(
                "Unexpected tables in dictionary DB: "
                f"{sorted(unexpected)}"
            )

        required_columns = {
            "dictionary_entries": {
                "word",
                "pronunciation",
                "pronunciation_normalized",
                "definition",
                "senses",
                "part_of_speech",
                "level",
                "tags",
                "synonyms",
                "related_words",
                "character_meanings",
                "antonyms",
                "usage_notes",
                "word_ruby",
                "frequency",
                "frequency_band",
                "frequency_label",
            },
            "characters": {
                "character",
                "jyutping",
                "frequency",
                "gloss_pronunciation",
                "gloss",
            },
            "english_index": {
                "english_word",
                "english_normalized",
                "cantonese_word",
                "rank",
            },
            "database_metadata": {
                "key",
                "value",
            },
            "dictionary_words": {"word"},
        }

        for table, expected in required_columns.items():
            actual = {
                row[1]
                for row in conn.execute(
                    f"PRAGMA table_info({table})"
                )
            }

            missing_columns = expected - actual

            if missing_columns:
                raise RuntimeError(
                    f"Missing columns in {table}: "
                    f"{sorted(missing_columns)}"
                )

        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
        if user_version != SCHEMA_VERSION:
            raise RuntimeError(
                f"SQLite user_version is {user_version}; expected {SCHEMA_VERSION}"
            )
        metadata_version = conn.execute(
            "SELECT value FROM database_metadata WHERE key = 'schema_version'"
        ).fetchone()
        if not metadata_version or metadata_version[0] != str(SCHEMA_VERSION):
            raise RuntimeError("database_metadata schema_version does not match builder")
        max_length_row = conn.execute(
            "SELECT value FROM database_metadata WHERE key = 'dictionary_word_max_length'"
        ).fetchone()
        actual_max_length = conn.execute(
            "SELECT MAX(LENGTH(word)) FROM dictionary_words"
        ).fetchone()[0] or 1
        if not max_length_row or int(max_length_row[0]) != actual_max_length:
            raise RuntimeError("dictionary_word_max_length metadata does not match aliases")

        integrity = conn.execute("PRAGMA quick_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"SQLite quick_check failed: {integrity}")

        # Catch malformed preprocessed JSON before publishing a release asset.
        for word, ruby_json, senses_json, characters_json in conn.execute(
            "SELECT word, word_ruby, senses, character_meanings FROM dictionary_entries"
        ):
            if ruby_json:
                ruby = json.loads(ruby_json)
                if not isinstance(ruby, list) or any(
                    not isinstance(item, dict)
                    or not isinstance(item.get("character"), str)
                    or not isinstance(item.get("reading"), str)
                    for item in ruby
                ):
                    raise RuntimeError(f"Invalid word ruby JSON for {word}")
            if senses_json:
                senses = json.loads(senses_json)
                if not isinstance(senses, list):
                    raise RuntimeError(f"Invalid senses JSON for {word}")
                for sense in senses:
                    if not isinstance(sense, dict):
                        raise RuntimeError(f"Invalid sense record for {word}")
                    if not isinstance(sense.get("meaningLines"), list):
                        raise RuntimeError(f"Missing meaningLines for {word}")
                    details = sense.get("exampleDetails", [])
                    if not isinstance(details, list):
                        raise RuntimeError(f"Invalid exampleDetails for {word}")
                    for detail in details:
                        if not isinstance(detail, dict) or not isinstance(detail.get("ruby", []), list):
                            raise RuntimeError(f"Invalid example detail for {word}")
            if characters_json:
                characters = json.loads(characters_json)
                if not isinstance(characters, list) or any(
                    not isinstance(item, dict)
                    or not isinstance(item.get("character"), str)
                    or not isinstance(item.get("pronunciation"), str)
                    or not isinstance(item.get("gloss"), str)
                    for item in characters
                ):
                    raise RuntimeError(f"Invalid character meanings JSON for {word}")

        count = conn.execute(
            """
            SELECT COUNT(*)
            FROM dictionary_entries
            """
        ).fetchone()[0]

        if count < 1000:
            raise RuntimeError(
                "Dictionary validation failed: "
                f"only {count} entries"
            )

        jp_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM dictionary_entries
            WHERE pronunciation <> ''
            """
        ).fetchone()[0]

        if jp_count == 0:
            raise RuntimeError(
                "Dictionary validation failed: "
                "no pronunciations"
            )

        english_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM english_index
            """
        ).fetchone()[0]

        if english_count == 0:
            raise RuntimeError(
                "Dictionary validation failed: "
                "empty English index"
            )

        character_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM characters
            """
        ).fetchone()[0]

        if character_count == 0:
            raise RuntimeError(
                "Dictionary validation failed: "
                "empty character table"
            )

        character_gloss_count = conn.execute(
            "SELECT COUNT(*) FROM characters WHERE gloss <> ''"
        ).fetchone()[0]
        if character_gloss_count == 0:
            raise RuntimeError("Dictionary validation failed: no precomputed character glosses")

        alias_count = conn.execute(
            "SELECT COUNT(*) FROM dictionary_words"
        ).fetchone()[0]
        if alias_count == 0:
            raise RuntimeError("Dictionary validation failed: empty subtitle word list")

        ruby_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM dictionary_entries
            WHERE word_ruby <> ''
            """
        ).fetchone()[0]

        if ruby_count == 0:
            raise RuntimeError(
                "Dictionary validation failed: "
                "no ruby data"
            )

        # Check important real entries.
        for word in (
            "火",
            "十",
            "馬",
        ):
            row = conn.execute(
                """
                SELECT
                    word,
                    pronunciation,
                    pronunciation_normalized,
                    frequency,
                    frequency_band
                FROM dictionary_entries
                WHERE word = ?
                LIMIT 1
                """,
                (word,),
            ).fetchone()

            if row:
                print(
                    f"  {word}: "
                    f"jp={row[1]} "
                    f"norm={row[2]} "
                    f"freq={row[3]} "
                    f"band={row[4]}"
                )

        # Verify indexes exist.
        indexes = {
            row[0]
            for row in conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='index'
                """
            )
        }

        required_indexes = {
            "idx_dictionary_word",
            "idx_dictionary_pronunciation",
            "idx_dictionary_pronunciation_normalized",
            "idx_dictionary_frequency",
            "idx_dictionary_frequency_band",
            "idx_dictionary_frequency_label",
            "idx_dictionary_words_word",
            "idx_characters_character",
            "idx_characters_jyutping",
            "idx_characters_frequency",
            "idx_english_word",
            "idx_english_normalized",
            "idx_english_rank",
        }

        missing_indexes = (
            required_indexes - indexes
        )

        if missing_indexes:
            raise RuntimeError(
                "Missing indexes: "
                f"{sorted(missing_indexes)}"
            )

        print()
        print("Validation OK")
        print(
            f"  dictionary_entries: {count:,}"
        )
        print(
            f"  with pronunciation: {jp_count:,}"
        )
        print(
            f"  characters: {character_count:,}"
        )
        print(
            f"  english_index rows: {english_count:,}"
        )
        print(
            f"  entries with ruby: {ruby_count:,}"
        )

    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Manifest / hashing
# ---------------------------------------------------------------------------

def sha256(
    path: Path,
) -> str:

    h = hashlib.sha256()

    with path.open("rb") as f:
        for block in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            h.update(block)

    return h.hexdigest()


def write_manifest(
    path: Path,
    db: Path,
    stats: dict,
) -> None:

    data = {
        "language": "yue",
        "language_name": "Cantonese",
        "schema_version": SCHEMA_VERSION,
        "database_file": db.name,
        "database_sha256": sha256(db),
        "database_size_bytes": db.stat().st_size,
        "stats": stats,
        "release_asset": "cantonese.db.gz",
        "latest_release_url_template": (
            "https://github.com/WSSamuel/cantonese_dictionary_builder/"
            "releases/latest/download/"
            "cantonese.db.gz"
        ),
    }

    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output",
        default="dist",
    )

    args = parser.parse_args()

    out = Path(args.output)
    out.mkdir(
        parents=True,
        exist_ok=True,
    )

    s = session()

    print(
        "Downloading Words.hk bulk dictionary..."
    )

    bulk_bytes, bulk_url = (
        download_words_hk_bulk(s)
    )

    print(
        f"  source: {bulk_url}"
    )

    print(
        f"  bytes: {len(bulk_bytes):,}"
    )

    print(
        "Downloading word frequency..."
    )

    frequency = get_json(
        s,
        FREQUENCY_URL,
    )

    print(
        "Downloading character usage frequency..."
    )

    char_frequency = get_json(
        s,
        CHAR_FREQUENCY_URL,
    )

    print(
        "Downloading character list..."
    )

    char_response = s.get(
        CHARLIST_URL,
        timeout=60,
    )

    char_response.raise_for_status()

    char_csv = char_response.content.decode(
        "utf-8",
        errors="replace",
    )

    print(
        "Downloading English index..."
    )

    english_index = get_json(
        s,
        ENGLISH_INDEX_URL,
        timeout=120,
    )

    db = out / "cantonese.db"

    print(
        "Building SQLite database..."
    )

    stats = build_database(
        db,
        bulk_bytes,
        bulk_url,
        frequency,
        char_frequency,
        char_csv,
        english_index,
    )

    print(
        "Validating..."
    )

    validate(db)

    # ---------------------------------------------------------------
    # Compress
    # ---------------------------------------------------------------

    gz = out / "cantonese.db.gz"

    with (
        db.open("rb") as src,
        gzip.open(
            gz,
            "wb",
            compresslevel=9,
        ) as dst,
    ):
        while True:
            block = src.read(
                1024 * 1024
            )

            if not block:
                break

            dst.write(block)

    # ---------------------------------------------------------------
    # Manifest
    # ---------------------------------------------------------------

    manifest = out / "cantonese.json"

    write_manifest(
        manifest,
        db,
        stats,
    )

    print()
    print("Build complete:")
    print(f"  {db}")
    print(f"  {gz}")
    print(f"  {manifest}")
    print(
        f"  SHA-256: {sha256(db)}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
