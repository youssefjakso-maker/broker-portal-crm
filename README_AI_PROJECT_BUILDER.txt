BROKER PORTAL V16 - PROJECT BUILDER
===================================

NEW ADMIN FEATURE
- Open Admin / Data Management.
- Select "AI Project Builder" or open /admin/projects/ai-import.
- Paste a raw project summary and choose Analyze Summary.
- Review and edit project fields and each detected unit.
- Select Confirm & Create Project to save the project and reviewed units.

SAFETY
- Analyze only creates an editable draft; it does not write to inventory.
- Saving requires an explicit Admin confirmation.
- Project and unit creation use the existing manual inventory tables and create_manual_unit flow.
- A project creation audit event is recorded.
- The source line for each detected unit is retained in the unit's original_json.
- Missing fields remain blank and must be completed by the Admin.

EXTRACTION LIMITATION
This V16 build uses conservative local extraction rules. It does not connect to an external LLM/API and does not require an API key. The interface is designed for review-first import, but every extracted value must be checked against the pasted source. A real LLM provider can be connected later behind the same draft/review workflow.

The existing Manual Entry workflow, Excel import/publish flow, broker views, and Update Intelligence page remain in place.
