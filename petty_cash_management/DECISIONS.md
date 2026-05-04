# Architectural Decisions — petty_cash_management

## ADR-001: Model name `hr.petty.cash` for custody
**Decision:** Use `hr.petty.cash` instead of `petty.cash.custody` for the main custody model.  
**Reason:** Follows Odoo convention for HR-related models and integrates naturally with `hr.employee`. Makes ACL rules easier to write using standard HR department/manager patterns.

## ADR-002: Balance computed from `account.move.line`
**Decision:** `petty.cash.fund.current_balance` is computed from posted journal entry lines on the fund's account, not stored as a float field updated manually.  
**Reason:** Eliminates any risk of balance drift. A manual float could become desynchronized from the actual accounting records. Computing from `account.move.line` is the Odoo-standard approach and always reflects the true accounting state.  
**Trade-off:** Slightly heavier computation. Mitigated by `store=True` with proper `@api.depends`.

## ADR-003: Single custody model for temporary + permanent
**Decision:** Both temporary (عهدة مؤقتة) and permanent (عهدة دائمة) custodies live in the same model `hr.petty.cash` with `custody_type` selection field, rather than two separate models.  
**Reason:** 80% of fields and workflows are shared. Two models would lead to code duplication and harder reporting. Visibility of permanent-only fields is controlled via `invisible` in views.

## ADR-004: Settlement uses `account.move` posted directly
**Decision:** On `action_post()`, settlement creates and immediately posts an `account.move`.  
**Reason:** Prevents orphaned draft moves. Settlement approval is the business approval — the accounting post should be atomic with it.  
**Trade-off:** Cannot unpost without a credit note. This is intentional for audit integrity.

## ADR-005: `petty.cash.config.settings` extends `res.config.settings` (TransientModel)
**Decision:** Configuration uses `res.config.settings` with `config_parameter` storage.  
**Reason:** Standard Odoo approach. Avoids a custom settings model that would require its own access rules and singleton management.

## ADR-006: OWL Dashboard registered as list view override
**Decision:** Dashboard is registered as a custom list view controller (`js_class="petty_cash_dashboard"`) rather than a client action.  
**Reason:** Allows the dashboard to be embedded in the normal menu/breadcrumb flow without losing navigation context. Client actions can feel disconnected on mobile.

## ADR-007: No hard-coded account codes anywhere
**Decision:** All accounting accounts are taken from `petty.cash.config.settings` or from the fund/journal configuration.  
**Reason:** Different companies use different chart of accounts. Egyptian COA, Gulf IFRS, and standard Odoo accounts all have different codes. Hard-coding would break on first real client.

## ADR-008: Wizard views in separate file
**Decision:** All wizard views are consolidated in `views/petty_cash_wizard_views.xml` and added to `__manifest__.py` data list.  
**Reason:** Keeps the main model view files clean. Easier to find and maintain wizard UIs.

## ADR-009: `noupdate="1"` on seed data
**Decision:** Expense categories and email templates use `noupdate="1"`.  
**Reason:** Allows clients to customize categories and templates after install without those customizations being overwritten on module upgrade.

## ADR-010: Multi-company enforced via record rules + `company_id` fields
**Decision:** Multi-company isolation uses standard Odoo record rules with `company_ids` domain.  
**Reason:** Odoo 19 standard approach. Avoids reinventing company isolation logic.

## ADR-011: `res.branch` field optional on fund
**Decision:** `branch_id` on `petty.cash.fund` uses `check_company=True` but is not required.  
**Reason:** Not all Odoo installations have `res.branch` (it's part of `branch` module). Making it optional ensures compatibility. If branch module is not installed, the field is simply unused.

## ADR-012: Email templates use `auto_delete=True`
**Decision:** All email templates have `auto_delete=True`.  
**Reason:** Petty cash notifications can be high-volume (daily overdue checks). Keeping all sent emails in the DB would cause unnecessary storage growth.
