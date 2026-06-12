"""Claim submission service - extracted from SubmitToPayerWorker and RetryFailedSubmissionWorker.

Handles TISS submission to payers and retry with exponential backoff.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from healthcare_platform.shared.integrations.tiss_client import TISSClientProtocol


class ClaimSubmissionService:
    """Orchestrates claim submission and retry logic."""

    def __init__(self, tiss_client: Optional[TISSClientProtocol] = None) -> None:
        self._tiss_client = tiss_client

    async def submit(
        self, tiss_xml: str, payer_id: str, claim_id: str
    ) -> Dict[str, Any]:
        """Submit TISS XML to payer. Returns submission result dict."""
        if self._tiss_client:
            try:
                result = await self._tiss_client.submit_guide(tiss_xml, payer_id)
                if result.success:
                    return {
                        "submission_success": True,
                        "protocol_number": result.protocol_number,
                        "submission_timestamp": (
                            result.submission_timestamp.isoformat()
                            if result.submission_timestamp
                            else None
                        ),
                        "payer_response_code": result.payer_response_code or "OK",
                        "payer_response_message": result.payer_response_message or "Stub submission accepted",
                    }
                else:
                    return {
                        "submission_success": False,
                        "payer_response_code": result.payer_response_code,
                        "payer_response_message": result.payer_response_message or "Falha na submissão",
                    }
            except Exception as e:
                return {
                    "submission_success": False,
                    "error": str(e),
                }

        # Fallback: mock submission if no client
        return {
            "submission_success": True,
            "protocol_number": f"PROT-{claim_id}",
            "submission_timestamp": None,
            "payer_response_code": "OK",
            "payer_response_message": "Stub submission accepted",
        }

    async def retry_submission(
        self,
        tiss_xml: str,
        payer_id: str,
        claim_id: str,
        attempt_number: int,
        max_attempts: int,
    ) -> Dict[str, Any]:
        """Retry a failed submission with exponential backoff."""
        backoff_ms = min(2 ** attempt_number * 1000, 300000)
        next_attempt = attempt_number + 1
        is_last = next_attempt >= max_attempts

        if self._tiss_client:
            try:
                result = await self._tiss_client.submit_guide(tiss_xml, payer_id)
                if result.success:
                    return {
                        "retry_success": True,
                        "protocol_number": result.protocol_number,
                        "next_attempt_number": next_attempt,
                        "backoff_ms": 0,
                        "max_attempts_reached": False,
                    }
                return {
                    "retry_success": False,
                    "protocol_number": None,
                    "next_attempt_number": next_attempt,
                    "backoff_ms": backoff_ms,
                    "max_attempts_reached": is_last,
                    "last_error": result.payer_response_message or "Falha na submissão",
                }
            except Exception as e:
                return {
                    "retry_success": False,
                    "protocol_number": None,
                    "next_attempt_number": next_attempt,
                    "backoff_ms": backoff_ms,
                    "max_attempts_reached": is_last,
                    "last_error": str(e),
                }

        # Fallback: mock success if no client
        return {
            "retry_success": True,
            "protocol_number": f"RETRY-PROT-{claim_id}",
            "next_attempt_number": next_attempt,
            "backoff_ms": backoff_ms,
            "max_attempts_reached": False,
        }
