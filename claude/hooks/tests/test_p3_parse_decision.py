"""P3: both prompts require "First non-empty line must be exactly one of:
APPROVE, REVISE, BLOCK". codex-review-plan.py's parse_decision() and
codex-review-implementation.py's first_decision_token() must enforce an
exact match on that first non-blank line, not merely a leading token/word,
and must agree with each other."""
import importlib.util
import os
import sys
import unittest

HOOKS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_module(filename, module_name):
    path = os.path.join(HOOKS_DIR, filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


plan = _load_module("codex-review-plan.py", "codex_review_plan_under_test")
impl = _load_module("codex-review-implementation.py", "codex_review_implementation_under_test")


class TestParseDecision(unittest.TestCase):
    def test_ignores_approve_token_on_a_later_line(self):
        text = "無法審查\nAPPROVE is only an example."
        self.assertEqual(plan.parse_decision(text), "")

    def test_extra_text_after_approve_on_first_line_is_rejected(self):
        text = "APPROVE is only an example; unable to review."
        self.assertEqual(plan.parse_decision(text), "")

    def test_approve_with_trailing_colon_is_rejected(self):
        # "APPROVE: looks good" is not *exactly* APPROVE, so per the prompt
        # contract it must not count as an approval.
        self.assertEqual(plan.parse_decision("APPROVE: looks good"), "")

    def test_leading_blank_lines_then_revise(self):
        text = "\n\n  \nREVISE\nsome reason"
        self.assertEqual(plan.parse_decision(text), "REVISE")

    def test_exact_approve_on_first_line_is_accepted(self):
        text = "APPROVE\nlooks good"
        self.assertEqual(plan.parse_decision(text), "APPROVE")


class TestFirstDecisionTokenMatchesSameContract(unittest.TestCase):
    def test_extra_text_after_block_on_first_line_is_rejected(self):
        text = "BLOCK this diff, it deletes prod data."
        self.assertEqual(impl.first_decision_token(text), "")

    def test_exact_block_on_first_line_is_accepted(self):
        text = "BLOCK\nreason"
        self.assertEqual(impl.first_decision_token(text), "BLOCK")


if __name__ == "__main__":
    unittest.main()
