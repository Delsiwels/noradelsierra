"""Shared HTTP helpers for Xero API requests."""


def xero_headers(
    access_token: str,
    tenant_id: str,
    *,
    json_content: bool = False,
) -> dict[str, str]:
    """Build the standard Xero API request headers.

    Args:
        access_token: Xero OAuth access token.
        tenant_id: Xero tenant ID.
        json_content: When ``True``, also set ``Content-Type: application/json``
            (for write requests that send a JSON body).
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Xero-Tenant-Id": tenant_id,
        "Accept": "application/json",
    }
    if json_content:
        headers["Content-Type"] = "application/json"
    return headers
