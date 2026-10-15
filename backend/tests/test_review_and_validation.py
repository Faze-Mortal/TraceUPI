
import unittest
import builtins
from types import ModuleType
from unittest.mock import patch

from backend.pipeline_port import PipelineUnavailableError, load_analysis_pipeline
from backend.review_transitions import (
    InvalidReviewTransition,
    apply_review_transition,
    is_allowed_review_transition,
)
from backend.validation import (
    ContractValidationError,
    validate_alert_status_filter,
    validate_as_of,
    validate_budget_k,
    validate_counterfactual_interventions,
)


class TestReviewTransitions(unittest.TestCase):
    def test_allowed_edges(self) -> None:
        self.assertTrue(is_allowed_review_transition("OPEN", "INVESTIGATING"))
        self.assertTrue(is_allowed_review_transition("OPEN", "CONFIRMED_FRAUD"))
        self.assertTrue(is_allowed_review_transition("OPEN", "DISMISSED_BENIGN"))
        self.assertTrue(is_allowed_review_transition("INVESTIGATING", "CONFIRMED_FRAUD"))
        self.assertTrue(is_allowed_review_transition("INVESTIGATING", "DISMISSED_BENIGN"))
        self.assertTrue(is_allowed_review_transition("CONFIRMED_FRAUD", "INVESTIGATING"))
        self.assertTrue(is_allowed_review_transition("DISMISSED_BENIGN", "INVESTIGATING"))

    def test_disallowed_edges(self) -> None:
        self.assertFalse(is_allowed_review_transition("CONFIRMED_FRAUD", "DISMISSED_BENIGN"))
        self.assertFalse(is_allowed_review_transition("DISMISSED_BENIGN", "CONFIRMED_FRAUD"))
        self.assertFalse(is_allowed_review_transition("INVESTIGATING", "OPEN"))
        self.assertFalse(is_allowed_review_transition("OPEN", "OPEN"))

    def test_apply_raises_contract_detail(self) -> None:
        with self.assertRaises(InvalidReviewTransition) as ctx:
            apply_review_transition("CONFIRMED_FRAUD", "DISMISSED_BENIGN")
        self.assertEqual(ctx.exception.detail, "invalid_review_transition")

    def test_apply_returns_requested_status(self) -> None:
        self.assertEqual(
            apply_review_transition("OPEN", "INVESTIGATING"),
            "INVESTIGATING",
        )


class TestHttpValidation(unittest.TestCase):
    def test_as_of_none_is_plus_infinity(self) -> None:
        self.assertIsNone(validate_as_of(None))

    def test_as_of_valid(self) -> None:
        self.assertEqual(
            validate_as_of("2026-10-01T12:00:00Z"),
            "2026-10-01T12:00:00Z",
        )

    def test_as_of_invalid_detail(self) -> None:
        with self.assertRaises(ContractValidationError) as ctx:
            validate_as_of("2026-10-01T12:00:00+00:00")
        self.assertEqual(ctx.exception.detail, "invalid_as_of_timestamp")

    def test_budget_k(self) -> None:
        self.assertEqual(validate_budget_k(10), 10)
        self.assertEqual(validate_budget_k(None, default=20), 20)

        with self.assertRaises(ContractValidationError) as ctx:
            validate_budget_k(15)
        self.assertEqual(ctx.exception.detail, "invalid_budget_k")

    def test_status_filter(self) -> None:
        self.assertEqual(validate_alert_status_filter("OPEN"), "OPEN")

        with self.assertRaises(ContractValidationError) as ctx:
            validate_alert_status_filter("CLOSED")
        self.assertEqual(ctx.exception.detail, "invalid_filter_param")

    def test_empty_counterfactual(self) -> None:
        with self.assertRaises(ContractValidationError) as ctx:
            validate_counterfactual_interventions([], False, False)
        self.assertEqual(ctx.exception.detail, "empty_counterfactual_request")

    def test_non_empty_counterfactual(self) -> None:
        validate_counterfactual_interventions(["E1"], False, False)
        validate_counterfactual_interventions([], True, False)
        validate_counterfactual_interventions([], False, True)


class TestPipelinePortFailsClosed(unittest.TestCase):
    def test_missing_pipeline_raises(self) -> None:
        original_import = builtins.__import__

        def import_without_pipeline(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "ml" and "pipeline" in (fromlist or ()):
                raise ImportError("No module named ml.pipeline")
            return original_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=import_without_pipeline):
            with self.assertRaises(PipelineUnavailableError) as ctx:
                load_analysis_pipeline()

        self.assertIn("ml.pipeline", str(ctx.exception))
        self.assertIn("mock scores", str(ctx.exception).lower())

    def test_incomplete_pipeline_raises(self) -> None:
        incomplete_pipeline = ModuleType("ml.pipeline")

        with patch("ml.pipeline", incomplete_pipeline, create=True):
            with patch(
                "builtins.__import__",
                return_value=incomplete_pipeline,
            ):
                with self.assertRaises(PipelineUnavailableError) as ctx:
                    load_analysis_pipeline()

        self.assertIn("run_analysis", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
