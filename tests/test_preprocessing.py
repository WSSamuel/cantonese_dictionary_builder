"""Regression tests for app-ready dictionary preprocessing."""

import unittest

import build


class TagPreprocessingTests(unittest.TestCase):
    def test_pos_abbreviations_and_chinese_labels_are_normalized(self):
        self.assertEqual(build.normalize_tag("v."), "verb")
        self.assertEqual(build.normalize_tag("n 名詞"), "noun")
        self.assertEqual(build.normalize_tag("口語"), "spoken language")

    def test_tag_lists_are_deduplicated(self):
        self.assertEqual(
            build.normalize_tag_list("名詞、n. / 口語, 口語"),
            "noun, spoken language",
        )


class SubtitlePreprocessingTests(unittest.TestCase):
    def test_aliases_strip_invisible_chars_and_expand_slash_variants(self):
        self.assertEqual(
            build.dictionary_aliases(" 鍾意／中意\u200b/鍾意 "),
            ["鍾意", "中意"],
        )

    def test_example_jyutping_is_only_attached_when_unambiguous(self):
        self.assertEqual(
            build.example_ruby("你好 (nei5 hou2)"),
            [
                {"character": "你", "reading": "nei5"},
                {"character": "好", "reading": "hou2"},
            ],
        )
        self.assertEqual(build.example_ruby("你好 (hello)"), [])
        self.assertEqual(build.example_ruby("你好 (nei5)"), [])


class FrequencyPreprocessingTests(unittest.TestCase):
    def test_display_frequency_labels_are_built_from_rank_boundaries(self):
        entries = [
            {"word": f"word-{i}", "frequency": 11000 - i}
            for i in range(10001)
        ]
        labels = build.calculate_frequency_labels(entries)
        self.assertEqual(labels["word-0"], "Very common")
        self.assertEqual(labels["word-100"], "Common")
        self.assertEqual(labels["word-500"], "Frequent")
        self.assertEqual(labels["word-1500"], "Less common")
        self.assertEqual(labels["word-3000"], "Uncommon")
        self.assertEqual(labels["word-10000"], "Rare")

    def test_zero_frequency_has_no_display_label(self):
        self.assertEqual(
            build.calculate_frequency_labels(
                [{"word": "unknown", "frequency": 0}]
            ),
            {"unknown": ""},
        )


class StructuredSenseTests(unittest.TestCase):
    def test_cantonese_and_english_example_lines_stay_in_one_record(self):
        parsed = build.parse_all_csv_content(
            "<explanation>\n*(英文)* greeting\n(pos:n) (label:口語)\n"
            "<eg>\nyue:你好 (nei5 hou2)\neng:hello"
        )
        self.assertEqual(parsed["partOfSpeech"], "noun")
        self.assertEqual(parsed["tags"], "spoken language")
        self.assertEqual(len(parsed["senses"]), 1)
        details = parsed["senses"][0]["exampleDetails"]
        self.assertEqual(len(details), 1)
        self.assertEqual(details[0]["cantonese"], "你好 (nei5 hou2)")
        self.assertEqual(details[0]["english"], "hello")
        self.assertEqual(len(details[0]["ruby"]), 2)


if __name__ == "__main__":
    unittest.main()
