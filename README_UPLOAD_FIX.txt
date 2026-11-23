BROKER PORTAL V13 — UPLOAD DIAGNOSTIC BUILD

This build keeps the V13 features and adds:
- Upload stage messages in the server CMD window.
- A log file at data/upload_debug.log.
- An admin-only Download upload diagnostics link.
- Visible submit feedback and protection against double-clicking the upload button.
- A 32 MB upload limit with a readable error message.
- Explicit closing of the read-only Excel workbook after parsing.

IMPORTANT: This is a diagnostic/hardening build. The exact cause of the user's current hanging request is not yet confirmed. Do not describe this build as a proven root-cause fix until one upload completes or the new log identifies the blocking stage.

SAFE UPDATE STEPS:
1. Stop the currently spinning browser request with Esc or the browser Stop button.
2. In the black server CMD window, press Ctrl+C once.
3. Do not delete or overwrite the old portal folder.
4. Extract this ZIP into a NEW folder.
5. Copy the complete data folder from the current V13 folder into the new folder's Broker_Portal_Final folder, merging/replacing the new data folder. This preserves broker_portal.db, .session_secret, and prior uploaded files.
6. Run run_portal.bat in the new folder.
7. Try the upload once. The CMD will show [UPLOAD] stage messages. If it fails, use Admin > Download upload diagnostics and share upload_debug.log.

Do not copy only the sample Excel workbook; copy the whole data folder so existing CRM data is retained.
