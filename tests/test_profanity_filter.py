import unittest

from clausy.filter import ProfanityFilter, ProfanityFilterConfig


class ProfanityFilterTests(unittest.TestCase):
    def test_masks_whole_word_case_insensitive(self):
        f = ProfanityFilter(
            ProfanityFilterConfig(mode="mask", words=("badword",), replacement="[CENSORED]")
        )

        text = "BADWORD should be hidden, but badwording should stay."
        self.assertEqual(
            f.filter_text(text),
            "[CENSORED] should be hidden, but badwording should stay.",
        )

    def test_block_mode_replaces_message(self):
        f = ProfanityFilter(
            ProfanityFilterConfig(mode="block", words=("toxic",), block_message="Blocked")
        )

        self.assertEqual(f.filter_text("this is toxic content"), "Blocked")

    def test_off_mode_is_noop(self):
        f = ProfanityFilter(
            ProfanityFilterConfig(mode="off", words=("badword",), replacement="[CENSORED]")
        )
        self.assertEqual(f.filter_text("badword"), "badword")


if __name__ == "__main__":
    unittest.main()
