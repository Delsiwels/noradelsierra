"""Per-feature business logic services.

Each module owns the computation for one user-facing feature (aging dashboard,
payroll review, depreciation, etc.), typically consumed by a single matching
blueprint and talking to the Xero API. Cross-cutting infrastructure shared
across features lives in ``webapp.services`` instead.
"""
