"""
ActionGuard: Prevents LLM from hallucinating action confirmations.

The model must NEVER claim that file operations happened unless a verified
ToolResult confirms it. This guard detects and blocks such hallucinations.
"""

import re
from typing import Optional, Tuple


class ActionGuard:
    """
    Validates model responses to ensure they don't contain hallucinated
    action confirmations for file operations.

    The model can:
    - Describe what it WOULD do
    - Ask for clarification
    - Explain why it can't do something
    - Discuss files generally

    The model CANNOT:
    - Claim it deleted/renamed/moved/created files
    - Say "Done", "Completed", "Success" for file operations
    - Use past tense for file actions ("I deleted", "I renamed")
    """

    # Patterns that indicate the model is claiming an action happened
    # These are RED FLAGS when no tool was executed
    HALLUCINATION_PATTERNS = [
        # English - past tense claims with "I"
        r"\b(i('ve)?|i have)\s+(deleted|removed|renamed|moved|created|copied|written|made)\b",

        # English - passive voice claims
        r"\b(file|folder|directory|document)\s+(has been|was|is)\s+(deleted|removed|renamed|moved|created|copied)\b",
        r"\b[\w\.-]+\.(txt|pdf|doc|jpg|png|mp4|zip)\s+(has been|was)\s+(deleted|removed|renamed|moved|created|copied)\b",
        r"\b(the\s+)?(document|item)\s+(was|has been)\s+(deleted|created|renamed|moved|copied)\b",

        # English - success indicators
        r"\b(successfully|done|completed|finished)\s*(deleted|renamed|moved|created|copied)?\b",
        r"\b(deleted|removed|renamed|moved|created|copied)\s+(successfully|done|completed)\b",

        # Rename with arrow
        r"\brename[d]?\s+.*\s*(→|->|to)\s+.*\s*(successfully|done|✓|✔)?\b",

        # "is now" claims
        r"\b(the\s+)?(file|folder|document)\s+.*\s+(is\s+now|has\s+been)\s+(renamed|deleted|moved|created)\b",

        # Italian - past tense claims
        r"\b(ho|abbiamo)\s+(eliminato|cancellato|rinominato|spostato|creato|copiato)\b",
        r"\b(file|cartella|documento)\s+(è\s+stat[ao]|sono\s+stati)\s+(eliminat|cancellat|rinominat|spostat|creat|copiat)\b",
        r"\b(fatto|completato|eseguito)\s*(con\s+successo)?\b",
        r"\b(eliminato|cancellato|rinominato|spostato|creato|copiato)\s+con\s+successo\b",
        r"\b(file|documento)\s+(eliminato|cancellato|rinominato|spostato|creato)\b",

        # Checkmarks and completion indicators (suspicious without tool)
        r"[✓✔☑️✅]\s*(deleted|renamed|moved|created|done|fatto|eliminato)?",

        # "Done" or completion claims (standalone)
        r"^\s*(done|fatto|ecco|ready|pronto)[.!]?\s*$",

        # "But I've deleted" - mixed claims
        r"\bbut\s+(i('ve)?|i have)\s+(deleted|renamed|moved|created)\b",
    ]

    # Patterns that are OK - the model is being honest about limitations
    SAFE_PATTERNS = [
        r"\b(can'?t|cannot|unable|won'?t|couldn'?t)\b",
        r"\b(need|require|provide|specify|tell me)\b.*\b(path|file|name)\b",
        r"\b(which|what)\s+(file|folder|one)\b",
        r"\bI('d| would) need\b",
        r"\bplease (provide|specify|confirm)\b",
        r"\b(non posso|non riesco|ho bisogno)\b",  # Italian limitations
    ]

    # Action verbs that should ONLY appear in ToolResult-generated text
    ACTION_VERBS_PAST = [
        "deleted", "removed", "renamed", "moved", "created", "copied", "written",
        "eliminato", "cancellato", "rinominato", "spostato", "creato", "copiato",
    ]

    @classmethod
    def contains_hallucination(cls, text: str) -> Tuple[bool, Optional[str]]:
        """
        Check if text contains hallucinated action confirmations.

        Returns:
            (is_hallucination, matched_pattern) - True if text claims actions
            that should only come from verified tool results.
        """
        text_lower = text.lower()

        # First check for hallucination patterns - these are the RED FLAGS
        hallucination_match = None
        for pattern in cls.HALLUCINATION_PATTERNS:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                hallucination_match = match.group(0)
                break

        # If no hallucination found, it's safe
        if not hallucination_match:
            return False, None

        # Hallucination found - check if the ENTIRE response is ONLY about limitations
        # (i.e., no actual action claims, just discussing what can't be done)
        # Safe patterns only apply if they negate the action claim directly
        # e.g., "I can't delete" is safe, but "I can't find it. I deleted it." is NOT safe

        # Check if any safe pattern appears and the response doesn't contain
        # an actual action claim after "but", "however", "though", etc.
        has_contrasting_claim = bool(re.search(
            r"\b(but|however|though|although)\s+.*(i('ve)?|i have)\s+(deleted|removed|renamed|moved|created|copied)",
            text_lower, re.IGNORECASE
        ))

        if has_contrasting_claim:
            # Response says something like "I can't X. But I've deleted Y."
            # This is STILL a hallucination
            return True, hallucination_match

        # Check if this is a purely limitation-focused response
        is_purely_limitation = False
        for pattern in cls.SAFE_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                # Check if the hallucination pattern is negated by the safe pattern
                # e.g., "I can't delete" vs "I deleted"
                # Safe pattern must appear BEFORE or encompass the action
                safe_match = re.search(pattern, text_lower, re.IGNORECASE)
                if safe_match:
                    safe_pos = safe_match.start()
                    hall_pos = text_lower.find(hallucination_match)
                    # If safe pattern comes after hallucination, it doesn't negate it
                    if hall_pos < safe_pos:
                        continue
                    # Check if they're in the same clause (no sentence break between)
                    text_between = text_lower[safe_pos:hall_pos]
                    if '.' not in text_between and '!' not in text_between:
                        is_purely_limitation = True
                        break

        if is_purely_limitation:
            return False, None

        return True, hallucination_match

    @classmethod
    def sanitize_response(cls, text: str) -> str:
        """
        Remove or replace hallucinated action claims from model response.

        Instead of claiming success, the response will indicate the action
        wasn't verified.
        """
        is_hallucination, matched = cls.contains_hallucination(text)

        if not is_hallucination:
            return text

        # Replace the hallucinated success with an honest message
        # This is a fallback - ideally we block before this
        sanitized = text

        # Remove checkmarks
        sanitized = re.sub(r'[✓✔☑️✅]', '', sanitized)

        # Replace past tense action claims with present/future
        replacements = [
            (r'\b(I\'ve|I have) (deleted|renamed|moved|created)', r"I can \2"),
            (r'\b(file|folder) (has been|was) (deleted|renamed|moved|created)',
             r"\1 needs to be \3"),
            (r'\bsuccessfully (deleted|renamed|moved|created)', r"to \1"),
            (r'\b(done|completed|finished)\.?$', ""),
        ]

        for pattern, replacement in replacements:
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

        return sanitized.strip()

    @classmethod
    def create_honest_response(cls, original: str, reason: str = "") -> str:
        """
        Create an honest response when the model tried to hallucinate.

        Args:
            original: The model's original (hallucinated) response
            reason: Why the action couldn't be executed

        Returns:
            An honest response that doesn't claim success
        """
        if reason:
            return reason

        # Default honest response
        return (
            "I wasn't able to complete that action. "
            "Please provide the exact file path or try a more specific command."
        )

    @classmethod
    def validate_model_response(
        cls,
        response: str,
        tool_was_executed: bool,
    ) -> Tuple[str, bool]:
        """
        Validate and potentially modify a model response.

        Args:
            response: The model's response
            tool_was_executed: Whether a tool was actually executed this turn

        Returns:
            (validated_response, was_modified) - The response to show user,
            and whether it was modified due to hallucination detection.
        """
        if tool_was_executed:
            # If a tool was executed, the response should be from ResponseFormatter
            # and is trusted. No validation needed.
            return response, False

        # Tool was NOT executed - model should not claim success
        is_hallucination, matched = cls.contains_hallucination(response)

        if is_hallucination:
            # Block the hallucination
            honest_response = (
                "I need more information to complete that action. "
                "Could you specify the exact file path or which file you mean?"
            )
            return honest_response, True

        return response, False


def guard_response(response: str, tool_executed: bool) -> str:
    """
    Convenience function to guard a model response.

    Args:
        response: The model's response
        tool_executed: Whether a tool was executed

    Returns:
        Safe response (original if OK, modified if hallucination detected)
    """
    validated, _ = ActionGuard.validate_model_response(response, tool_executed)
    return validated
