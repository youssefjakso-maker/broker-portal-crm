BROKER PORTAL — UPDATE INTELLIGENCE (V15)

What was added:
- Admin-only Update Intelligence page at /admin/update-intelligence
- Paste WhatsApp project-update messages into one inbox
- Review-first extraction of likely project context and update type
- Project grouping and confidence indicator
- One-click Copy Full Summary for admin copy/paste into the manual inventory workflow
- Analysis history stored in SQLite
- Audit-log entry when an analysis is created
- No automatic mutation of inventory; admin remains the final source of truth

Important:
This first implementation intentionally uses a deterministic local parser. It does not require an external AI API key and does not change inventory automatically. It is designed as the safe V1 foundation for a later LLM-assisted extraction layer.
