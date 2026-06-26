"""Cross-cutting infrastructure services.

Modules here provide app-wide capabilities that are not tied to any single
feature — scheduling, runtime health, operational alerts, PDF export, BAS
deadline calendaring, readiness checklists, startup checks. Per-feature
business logic lives in ``webapp.app_services`` instead.
"""
