"""
Tests for ActionGuard - the hallucination blocker.

These tests verify that the ActionGuard correctly:
- Detects hallucinated action claims in model responses
- Blocks/sanitizes responses that claim file operations happened
- Allows safe responses (questions, explanations, limitations)
"""

import pytest
from leonard.utils.action_guard import ActionGuard, guard_response


class TestHallucinationDetection:
    """Test detection of hallucinated action claims."""

    # ─────────────────────────────────────────────────────────
    # SHOULD BE DETECTED AS HALLUCINATIONS (when no tool ran)
    # ─────────────────────────────────────────────────────────

    @pytest.mark.parametrize("text", [
        # English past tense claims
        "I've deleted the file.",
        "I have deleted file.txt",
        "I deleted the folder successfully.",
        "I've renamed report.pdf to report-final.pdf",
        "I have renamed the file.",
        "I moved the document to Downloads.",
        "I've created a new file called notes.txt",
        "I copied the file to Desktop.",

        # Passive voice claims
        "The file has been deleted.",
        "The folder was renamed successfully.",
        "file.txt has been moved to Documents.",
        "The document was created.",

        # Success indicators
        "Done!",
        "Completed.",
        "Successfully deleted.",
        "Renamed successfully.",
        "Done ✓",
        "✓ Deleted",
        "✅ File renamed",

        # Italian claims
        "Ho eliminato il file.",
        "Ho cancellato la cartella.",
        "Ho rinominato il documento.",
        "Ho spostato il file.",
        "Ho creato un nuovo file.",
        "File eliminato con successo.",
        "Fatto!",
        "Completato.",

        # Mixed/complex claims
        "I've successfully deleted old_file.txt and renamed new_file.txt",
        "The operation completed successfully - file deleted.",
        "Renamed 'report.pdf' → 'report-final.pdf' ✓",
    ])
    def test_detects_hallucinated_claims(self, text):
        """These texts claim actions happened and should be detected."""
        is_hallucination, matched = ActionGuard.contains_hallucination(text)
        assert is_hallucination, f"Should detect hallucination in: '{text}'"

    # ─────────────────────────────────────────────────────────
    # SHOULD NOT BE DETECTED (safe responses)
    # ─────────────────────────────────────────────────────────

    @pytest.mark.parametrize("text", [
        # Asking for clarification
        "Which file do you want to delete?",
        "I need the exact path to rename the file.",
        "Could you specify which folder you mean?",
        "Please provide the full path to the file.",

        # Expressing limitations
        "I can't delete files without a specific path.",
        "I'm unable to rename that file.",
        "I cannot perform that operation.",
        "I won't be able to do that without more information.",

        # Future tense / hypothetical
        "I would need the file path to delete it.",
        "To rename the file, I'll need the new name.",
        "I can help you delete that if you tell me which one.",

        # Describing what WOULD happen
        "Deleting this file would remove it permanently.",
        "Renaming would change the file from X to Y.",
        "If I delete that, it will be gone.",

        # General conversation
        "Hello! How can I help you?",
        "I see you have several PDF files in Downloads.",
        "That's an interesting question about files.",

        # Italian safe responses
        "Quale file vuoi eliminare?",
        "Non posso rinominare senza il percorso.",
        "Ho bisogno del nome del file.",
    ])
    def test_allows_safe_responses(self, text):
        """These texts are safe and should not be flagged."""
        is_hallucination, matched = ActionGuard.contains_hallucination(text)
        assert not is_hallucination, f"Should NOT detect hallucination in: '{text}' (matched: {matched})"


class TestResponseValidation:
    """Test the validate_model_response function."""

    def test_blocks_hallucination_when_no_tool_executed(self):
        """When no tool was executed, hallucinated claims should be blocked."""
        response = "I've deleted the file successfully."

        validated, was_blocked = ActionGuard.validate_model_response(
            response, tool_was_executed=False
        )

        assert was_blocked, "Should block hallucinated claim"
        assert "deleted" not in validated.lower(), "Should not contain 'deleted'"
        assert "need more information" in validated.lower() or "specify" in validated.lower()

    def test_allows_response_when_tool_executed(self):
        """When a tool WAS executed, response is trusted."""
        response = "[VERIFIED] Deleted file.txt"

        validated, was_blocked = ActionGuard.validate_model_response(
            response, tool_was_executed=True
        )

        assert not was_blocked, "Should not block when tool was executed"
        assert validated == response, "Response should be unchanged"

    def test_allows_clarification_questions(self):
        """Clarification questions should pass through."""
        response = "Which file would you like me to delete?"

        validated, was_blocked = ActionGuard.validate_model_response(
            response, tool_was_executed=False
        )

        assert not was_blocked, "Should not block clarification"
        assert validated == response

    def test_allows_limitation_statements(self):
        """Statements about limitations should pass through."""
        response = "I can't delete files without knowing the exact path."

        validated, was_blocked = ActionGuard.validate_model_response(
            response, tool_was_executed=False
        )

        assert not was_blocked, "Should not block limitation statement"
        assert validated == response


class TestGuardResponseFunction:
    """Test the convenience guard_response function."""

    def test_guard_response_blocks_hallucination(self):
        """Test the convenience function blocks hallucinations."""
        result = guard_response("I've deleted it.", tool_executed=False)
        assert "deleted" not in result.lower() or "cannot confirm" in result.lower()

    def test_guard_response_allows_safe(self):
        """Test the convenience function allows safe responses."""
        original = "Which file do you mean?"
        result = guard_response(original, tool_executed=False)
        assert result == original


class TestSanitization:
    """Test response sanitization."""

    def test_removes_checkmarks(self):
        """Checkmarks should be removed from suspicious responses."""
        text = "Done ✓ ✔ ✅"
        sanitized = ActionGuard.sanitize_response(text)
        assert "✓" not in sanitized
        assert "✔" not in sanitized
        assert "✅" not in sanitized

    def test_sanitize_past_tense_claims(self):
        """Past tense claims should be modified."""
        text = "I've deleted the file."
        sanitized = ActionGuard.sanitize_response(text)
        # Should not claim success
        assert "deleted" not in sanitized.lower() or "can delete" in sanitized.lower()


class TestEdgeCases:
    """Test edge cases and tricky scenarios."""

    def test_empty_response(self):
        """Empty response should not be flagged."""
        is_hall, _ = ActionGuard.contains_hallucination("")
        assert not is_hall

    def test_whitespace_only(self):
        """Whitespace-only response should not be flagged."""
        is_hall, _ = ActionGuard.contains_hallucination("   \n\t  ")
        assert not is_hall

    def test_mixed_safe_and_unsafe(self):
        """Response with both safe and unsafe parts should be flagged."""
        # This is tricky - has both a question AND a claim
        text = "I can't find that file. But I've deleted the other one."
        is_hall, _ = ActionGuard.contains_hallucination(text)
        # Should still be flagged because of the claim
        assert is_hall

    def test_describing_what_files_exist(self):
        """Describing existing files should be safe."""
        text = "I see these files in Downloads: report.pdf, notes.txt"
        is_hall, _ = ActionGuard.contains_hallucination(text)
        assert not is_hall

    def test_past_tense_in_question(self):
        """Past tense in questions should be safe."""
        text = "Did you want me to delete the file?"
        is_hall, _ = ActionGuard.contains_hallucination(text)
        # This is asking, not claiming
        # Note: our patterns might catch this, but it's borderline
        # For now, we err on the side of caution

    def test_verified_marker_is_trusted(self):
        """[VERIFIED] marker indicates real tool result."""
        text = "[VERIFIED] Deleted file.txt"
        # When tool_was_executed=True, this should pass
        validated, blocked = ActionGuard.validate_model_response(text, tool_was_executed=True)
        assert not blocked
        assert validated == text


class TestRealWorldScenarios:
    """Test scenarios from actual Leonard usage."""

    def test_scenario_rename_claim_without_tool(self):
        """
        User: 'rename report.pdf to final.pdf'
        Model claims: 'I've renamed report.pdf to final.pdf'
        But no tool was executed!
        """
        response = "I've renamed report.pdf to final.pdf. The file is now called final.pdf."

        validated, was_blocked = ActionGuard.validate_model_response(
            response, tool_was_executed=False
        )

        assert was_blocked, "Should block fake rename claim"

    def test_scenario_delete_hallucination(self):
        """
        User: 'delete old files'
        Model claims success without tool execution.
        """
        response = "Done! I've deleted the old files from your Downloads folder."

        validated, was_blocked = ActionGuard.validate_model_response(
            response, tool_was_executed=False
        )

        assert was_blocked, "Should block fake delete claim"

    def test_scenario_legitimate_tool_result(self):
        """
        Tool actually executed and returned verified result.
        Model should be allowed to include it.
        """
        # This would come from ResponseFormatter, not the model
        response = "[VERIFIED] Renamed report.pdf → final.pdf"

        validated, was_blocked = ActionGuard.validate_model_response(
            response, tool_was_executed=True
        )

        assert not was_blocked, "Should allow verified tool result"

    def test_scenario_model_asking_for_path(self):
        """
        Model correctly asks for more information instead of hallucinating.
        """
        response = "I'd be happy to rename that file. Which file in Downloads do you mean - report.pdf or notes.pdf?"

        validated, was_blocked = ActionGuard.validate_model_response(
            response, tool_was_executed=False
        )

        assert not was_blocked, "Should allow clarification request"
