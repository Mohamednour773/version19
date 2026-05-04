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

---

## FIXES — v19.0.1.0.1

### FIX-001: `current_balance` — removed `store=True` and wrong `@api.depends`
**Problem:** `@api.depends('journal_id', 'account_id')` does not trigger recompute when new journal entries are posted. `store=True` on a field that reads `account.move.line` causes stale data.
**Fix:** Removed `store=True` (field is now always computed fresh). Removed the `@api.depends` decorator entirely since non-stored computed fields recompute on every access. Added `journal_id` filter to the domain so multiple funds sharing the same account code are properly isolated.

### FIX-002: Return Wizard — wrong config key
**Problem:** `config.get('default_custody_account_id')` always returned `None` because `_get_values()` returns key `'custody_account_id'`.
**Fix:** Changed to `config.get('custody_account_id')`.

### FIX-003: Settlement `action_post` — deprecated `analytic_account_id`
**Problem:** `analytic_account_id` on `account.move.line` is removed in Odoo 17+/19. Using it raises a field-not-found error silently or on post.
**Fix:** Replaced with `analytic_distribution` (JSON dict) for all move line creation in settlement and custody disbursement.

### FIX-004: `petty.cash.expense.category` — deprecated `name_get()`
**Problem:** `name_get()` is deprecated in Odoo 17+. Causes a deprecation warning on every Many2one dropdown render.
**Fix:** Added `_rec_name = 'display_name_combined'` and a stored computed field `display_name_combined` that produces the bilingual label.

### FIX-005: Settlement line `receipt_attachment` — Binary field replaced with `ir.attachment` M2M
**Problem:** `fields.Binary` stores file contents directly in the DB column. Large PDFs/images cause DB bloat and slow queries. Odoo's standard pattern is `ir.attachment`.
**Fix:** Replaced with `receipt_attachment_ids = fields.Many2many('ir.attachment', ...)`. Updated the `_check_receipt_required` constraint accordingly.

### FIX-006: Cron `_cron_check_fund_balance` — wrong model reference
**Problem:** XML `model_id` pointed to `petty.cash.fund.transfer` but the method logically belongs on `petty.cash.fund`. When Odoo's cron executor calls `model._cron_check_fund_balance()`, it calls it on the wrong model class.
**Fix:** Moved method to `petty.cash.fund`. Updated XML `model_id` ref to `model_petty_cash_fund`.
