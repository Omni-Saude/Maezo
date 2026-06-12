#!/usr/bin/env python3
"""
Script to add glosa methods to tasy_api_client.py.
Run this script to inject glosa methods into TasyApiClient and StubTasyApiClient.
"""

import re

FILE_PATH = "healthcare_platform/shared/integrations/tasy_api_client.py"

# Production client methods to add after get_pix_status
PRODUCTION_METHODS = '''
    @track_api_call(service_name=SERVICE_NAME, operation="post_glosa")
    async def post_glosa(self, glosa_data: dict[str, Any]) -> dict[str, Any]:
        """Create glosa record in TASY.

        Args:
            glosa_data: Glosa data including claim_id, denied_amount, reason_code

        Returns:
            Created glosa with glosa_id, status, created_at

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = "/api/v1/billing/glosa"
        self._logger.debug("Creating TASY glosa", claim_id="[REDACTED]")
        return await self._request_with_metrics("POST", endpoint, json=glosa_data)

    @track_api_call(service_name=SERVICE_NAME, operation="get_glosa")
    async def get_glosa(self, claim_id: str) -> dict[str, Any]:
        """Get glosa by claim ID from TASY.

        Args:
            claim_id: TASY claim/account ID

        Returns:
            Glosa data with items, status, amounts

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/billing/glosa/{claim_id}"
        self._logger.debug("Getting TASY glosa", claim_id="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint)

    @track_api_call(service_name=SERVICE_NAME, operation="update_glosa_status")
    async def update_glosa_status(
        self, glosa_id: str, status: str, reason: str | None = None
    ) -> dict[str, Any]:
        """Update glosa status in TASY.

        Args:
            glosa_id: TASY glosa ID
            status: New status (e.g., 'in_progress', 'resolved', 'closed')
            reason: Optional reason for status change

        Returns:
            Updated glosa with new status

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/billing/glosa/{glosa_id}/status"
        payload = {"status": status}
        if reason:
            payload["reason"] = reason
        self._logger.debug("Updating TASY glosa status", glosa_id="[REDACTED]", status=status)
        return await self._request_with_metrics("PUT", endpoint, json=payload)

    @track_api_call(service_name=SERVICE_NAME, operation="submit_glosa_appeal")
    async def submit_glosa_appeal(
        self, glosa_id: str, appeal_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Submit glosa appeal to TASY.

        Args:
            glosa_id: TASY glosa ID
            appeal_data: Appeal data including justification, documents

        Returns:
            Appeal submission result with appeal_id, protocol

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/billing/glosa/{glosa_id}/appeal"
        self._logger.debug("Submitting TASY glosa appeal", glosa_id="[REDACTED]")
        return await self._request_with_metrics("POST", endpoint, json=appeal_data)

    @track_api_call(service_name=SERVICE_NAME, operation="get_glosa_appeal_status")
    async def get_glosa_appeal_status(self, glosa_id: str) -> dict[str, Any]:
        """Get glosa appeal status from TASY.

        Args:
            glosa_id: TASY glosa ID

        Returns:
            Appeal status with protocol, payer_response, updated_at

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/billing/glosa/{glosa_id}/appeal/status"
        self._logger.debug("Getting TASY glosa appeal status", glosa_id="[REDACTED]")
        return await self._request_with_metrics("GET", endpoint)

    @track_api_call(service_name=SERVICE_NAME, operation="resolve_glosa")
    async def resolve_glosa(
        self, glosa_id: str, resolution_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Resolve glosa in TASY.

        Args:
            glosa_id: TASY glosa ID
            resolution_data: Resolution data including recovered_amount, resolution_type

        Returns:
            Resolution result with final_status, resolved_at

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = f"/api/v1/billing/glosa/{glosa_id}/resolve"
        self._logger.debug("Resolving TASY glosa", glosa_id="[REDACTED]")
        return await self._request_with_metrics("POST", endpoint, json=resolution_data)

    @track_api_call(service_name=SERVICE_NAME, operation="get_glosa_statistics")
    async def get_glosa_statistics(
        self, date_from: str, date_to: str
    ) -> dict[str, Any]:
        """Get glosa statistics from TASY.

        Args:
            date_from: Start date (ISO format)
            date_to: End date (ISO format)

        Returns:
            Statistics with total_glosas, total_denied_amount, recovery_rate

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = "/api/v1/billing/glosa/statistics"
        params = {"date_from": date_from, "date_to": date_to}
        self._logger.debug("Getting TASY glosa statistics", date_from=date_from, date_to=date_to)
        result = await self._request_with_metrics("GET", endpoint, params=params)
        return result

    @track_api_call(service_name=SERVICE_NAME, operation="batch_glosa")
    async def batch_glosa(self, glosa_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Create multiple glosas in batch.

        Args:
            glosa_list: List of glosa data dictionaries

        Returns:
            List of created glosas with IDs

        Raises:
            ExternalServiceException: On TASY API errors
        """
        endpoint = "/api/v1/billing/glosa/batch"
        self._logger.debug("Batch creating TASY glosas", count=len(glosa_list))
        result = await self._request_with_metrics("POST", endpoint, json={"glosas": glosa_list})
        return result if isinstance(result, list) else result.get("results", [])
'''

# Stub client methods to add at the end before EOF
STUB_METHODS = '''
    async def post_glosa(self, glosa_data: dict[str, Any]) -> dict[str, Any]:
        """Create glosa in stub store."""
        await asyncio.sleep(0.01)
        glosa_id = f"GLOSA-{int(time.time())}"
        from datetime import datetime
        glosa = {
            "glosa_id": glosa_id,
            "claim_id": glosa_data.get("claim_id"),
            "denied_amount": glosa_data.get("denied_amount"),
            "reason_code": glosa_data.get("reason_code"),
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
        }
        self._glosas[glosa_id] = glosa
        return glosa

    async def get_glosa(self, claim_id: str) -> dict[str, Any]:
        """Get glosa from stub store."""
        await asyncio.sleep(0.01)
        for glosa in self._glosas.values():
            if glosa.get("claim_id") == claim_id:
                return glosa
        raise ExternalServiceException(
            _("Glosa não encontrada para conta: {}").format(claim_id),
            service_name=SERVICE_NAME,
            operation="get_glosa",
            status_code=404,
        )

    async def update_glosa_status(
        self, glosa_id: str, status: str, reason: str | None = None
    ) -> dict[str, Any]:
        """Update glosa status in stub store."""
        await asyncio.sleep(0.01)
        if glosa_id not in self._glosas:
            raise ExternalServiceException(
                _("Glosa não encontrada: {}").format(glosa_id),
                service_name=SERVICE_NAME,
                operation="update_glosa_status",
                status_code=404,
            )
        from datetime import datetime
        self._glosas[glosa_id]["status"] = status
        self._glosas[glosa_id]["updated_at"] = datetime.utcnow().isoformat()
        if reason:
            self._glosas[glosa_id]["status_reason"] = reason
        return self._glosas[glosa_id]

    async def submit_glosa_appeal(
        self, glosa_id: str, appeal_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Submit glosa appeal in stub store."""
        await asyncio.sleep(0.01)
        if glosa_id not in self._glosas:
            raise ExternalServiceException(
                _("Glosa não encontrada: {}").format(glosa_id),
                service_name=SERVICE_NAME,
                operation="submit_glosa_appeal",
                status_code=404,
            )
        from datetime import datetime
        appeal_id = f"APPEAL-{int(time.time())}"
        self._glosas[glosa_id]["appeal_id"] = appeal_id
        self._glosas[glosa_id]["appeal_protocol"] = f"PROT-{int(time.time())}"
        self._glosas[glosa_id]["appeal_submitted_at"] = datetime.utcnow().isoformat()
        self._glosas[glosa_id]["appeal_status"] = "submitted"
        return {
            "appeal_id": appeal_id,
            "protocol": self._glosas[glosa_id]["appeal_protocol"],
            "submitted_at": self._glosas[glosa_id]["appeal_submitted_at"],
        }

    async def get_glosa_appeal_status(self, glosa_id: str) -> dict[str, Any]:
        """Get glosa appeal status from stub store."""
        await asyncio.sleep(0.01)
        if glosa_id not in self._glosas:
            raise ExternalServiceException(
                _("Glosa não encontrada: {}").format(glosa_id),
                service_name=SERVICE_NAME,
                operation="get_glosa_appeal_status",
                status_code=404,
            )
        glosa = self._glosas[glosa_id]
        return {
            "appeal_id": glosa.get("appeal_id"),
            "protocol": glosa.get("appeal_protocol"),
            "status": glosa.get("appeal_status", "not_submitted"),
            "submitted_at": glosa.get("appeal_submitted_at"),
            "updated_at": glosa.get("updated_at"),
        }

    async def resolve_glosa(
        self, glosa_id: str, resolution_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Resolve glosa in stub store."""
        await asyncio.sleep(0.01)
        if glosa_id not in self._glosas:
            raise ExternalServiceException(
                _("Glosa não encontrada: {}").format(glosa_id),
                service_name=SERVICE_NAME,
                operation="resolve_glosa",
                status_code=404,
            )
        from datetime import datetime
        self._glosas[glosa_id]["status"] = "resolved"
        self._glosas[glosa_id]["resolved_at"] = datetime.utcnow().isoformat()
        self._glosas[glosa_id]["recovered_amount"] = resolution_data.get("recovered_amount", 0)
        self._glosas[glosa_id]["resolution_type"] = resolution_data.get("resolution_type")
        return self._glosas[glosa_id]

    async def get_glosa_statistics(
        self, date_from: str, date_to: str
    ) -> dict[str, Any]:
        """Get glosa statistics from stub store."""
        await asyncio.sleep(0.01)
        from datetime import datetime
        date_from_dt = datetime.fromisoformat(date_from)
        date_to_dt = datetime.fromisoformat(date_to)

        filtered_glosas = []
        for glosa in self._glosas.values():
            created_at = datetime.fromisoformat(glosa.get("created_at", ""))
            if date_from_dt <= created_at <= date_to_dt:
                filtered_glosas.append(glosa)

        total_denied = sum(float(g.get("denied_amount", 0)) for g in filtered_glosas)
        total_recovered = sum(float(g.get("recovered_amount", 0)) for g in filtered_glosas)

        return {
            "total_glosas": len(filtered_glosas),
            "total_denied_amount": total_denied,
            "total_recovered_amount": total_recovered,
            "recovery_rate": (total_recovered / total_denied * 100) if total_denied > 0 else 0,
            "date_from": date_from,
            "date_to": date_to,
        }

    async def batch_glosa(self, glosa_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Create multiple glosas in stub store."""
        await asyncio.sleep(0.01)
        results = []
        for glosa_data in glosa_list:
            result = await self.post_glosa(glosa_data)
            results.append(result)
        return results
'''

def main():
    print(f"Reading {FILE_PATH}...")
    with open(FILE_PATH, 'r') as f:
        content = f.read()

    # Add glosa storage to __init__
    init_pattern = r'(self\._pix_payments: dict\[str, dict\[str, Any\]\] = \{\})'
    if '_glosas' not in content:
        content = re.sub(
            init_pattern,
            r'\1\n        self._glosas: dict[str, dict[str, Any]] = {}',
            content
        )
        print("✓ Added _glosas storage to StubTasyApiClient.__init__")

    # Add production methods after get_pix_status but before get_material_price
    material_pattern = r'(\n    @track_api_call\(service_name=SERVICE_NAME, operation="get_material_price"\))'
    if 'operation="post_glosa"' not in content:
        content = re.sub(
            material_pattern,
            PRODUCTION_METHODS + r'\1',
            content
        )
        print("✓ Added 8 glosa methods to TasyApiClient")

    # Add stub methods at the end (before final newlines)
    if 'async def post_glosa' not in content[content.rfind('class StubTasyApiClient'):]:
        content = content.rstrip() + '\n' + STUB_METHODS + '\n'
        print("✓ Added 8 glosa methods to StubTasyApiClient")

    # Write back
    with open(FILE_PATH, 'w') as f:
        f.write(content)

    print(f"\n✓ Successfully updated {FILE_PATH}")
    print("  - Added 8 methods to protocol (already done via Edit tool)")
    print("  - Added 8 methods to TasyApiClient")
    print("  - Added 8 methods to StubTasyApiClient")
    print("  - Added _glosas storage")

if __name__ == "__main__":
    main()
