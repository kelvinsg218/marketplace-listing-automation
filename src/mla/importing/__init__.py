"""Import center: read client bases (CSV, XLSX, JSON, XML, PDF, ZIP), map columns, plan, review and commit.

Flow: analyze (format + preview + suggested mapping) → plan (rows validated, duplicates and changes found,
media resolved; stored in import_rows) → user decisions → commit (one transaction, cancellable) → report.
Nothing is written to the catalog before the user confirms; nothing is ever deleted by an import.
"""
