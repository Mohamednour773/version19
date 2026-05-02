# PDC Management — Changelog

All notable changes to this module are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [1.0.0] — Unreleased

### Added

#### Phase 1 — Model Architecture
- `pdc.check` model with full state machine for received, issued, and guarantee checks
- `pdc.check.book` — check book management with sequential number assignment
- `pdc.check.operation` — immutable audit log of every workflow action
- `pdc.bank` — PDC bank registry
- `pdc.bank.layout` — configurable print layout coordinates per bank
- `pdc.bounce.reason` — configurable bounce reason catalogue
- Multi-company record rules; three security groups
  (`group_pdc_user`, `group_pdc_manager`, `group_pdc_accountant`)
- `amount_in_words` (EN + AR) via `num2words`
- Hijri date display via `hijri_converter` (both optional dependencies)

#### Phase 2 — Views
- Full form, list, kanban, search, pivot, graph, and calendar views
- Option B conditional statusbar (three separate statusbar widgets,
  mutually exclusive by `check_type`)
- Nine window actions (All, Received, Issued, Guarantee, Under Collection,
  Due Soon, Overdue, Bounced, My Checks)
- Inherited views: `account.journal` (PDC Configuration tab),
  `account.payment`, `res.partner`, `res.config.settings`

#### Phase 3 — Accounting Integration
- Real journal entries for all 13 PDC workflows:

  | Workflow | Entry |
  |---|---|
  | Register (received) | Dr PDC-Received / Cr Partner-Receivable |
  | Register (issued) | Dr Partner-Payable / Cr PDC-Issued |
  | Deposit | Dr PDC-Under-Collection / Cr PDC-Received |
  | Clear | Dr Bank / Cr PDC-Under-Collection |
  | Bounce (received) | Dr Partner-Receivable + Dr Charges / Cr Collection + Cr Bank |
  | Bounce (issued) | Dr PDC-Issued-Delivered + Dr Charges / Cr Partner-Payable + Cr Bank |
  | Deliver | Dr PDC-Issued / Cr PDC-Issued-Delivered |
  | Pay | Dr PDC-Issued-Delivered / Cr Bank |
  | Settle | State-only — payment recorded separately |
  | Print | State-only |
  | Return Guarantee | State-only |
  | Activate Guarantee | Type conversion + opening entry (same as Register) |
  | Cancel | Reversal of all posted moves via `_reverse_moves(cancel=True)` |

- Multi-currency: `amount_currency` set correctly on all move lines when
  check currency differs from company currency; charges converted via
  `currency._convert()`
- All moves always posted (`action_post()`); never deleted; linked to `move_ids`
- Pre-flight journal account validation on every workflow action
- **User-selectable bounce charges source** — see Design Decisions below

### Design Decisions

#### Bounce Charges Source (`bounce_charges_source`)
In Egyptian and Saudi banking practice, the bank that books bounce charges varies:
- **Received checks**: most commonly the *collecting/deposit bank* raises the
  charge (approx. 60% of cases in Egypt/GCC) → default `deposit_journal`
- **Issued checks**: most commonly *your own bank* raises the charge →
  default `original_journal`
- Some companies use a dedicated expense account regardless of journal →
  `custom_account` option

The field `bounce_charges_source` (Selection, on `pdc.check`) allows per-check
selection of the source. The Phase 5 bounce wizard will pre-set this from
company configuration; users can override on a per-check basis.

Three options:

| Value | Charges Account From | Bank Credit From |
|---|---|---|
| `deposit_journal` | `deposit_journal_id.pdc_bounce_charges_account_id` | `deposit_journal_id.default_account_id` |
| `original_journal` | `journal_id.pdc_bounce_charges_account_id` | `journal_id.default_account_id` |
| `custom_account` | `bounce_charges_account_id` (user-set P&L account) | deposit or original journal default |

Defaults by check type:
- Received check created → `bounce_charges_source = 'deposit_journal'`
- Issued check created → `bounce_charges_source = 'original_journal'`

#### Move Date Policy
- **Registration**: uses `check.issue_date` (economic reality date)
- **Deposit, Clear, Deliver, Pay**: uses `fields.Date.today()` at time of action
- **Bounce**: uses `check.bounce_date` (defaults to today if not set)
- **Cancel reversals**: always today

Rationale: registration reflects when the check instrument was created;
operational actions reflect when they were processed in the system.

#### No Auto-Reconciliation in Phase 3
Journal entries are created and posted. Reconciliation of the PDC-Received/
PDC-Issued suspense account lines with specific invoice AR/AP lines is
deferred to Phase 5 wizards, which will call `account.move.line.reconcile()`
after collecting the user's invoice selections.

---

### Known Limitations (Accepted for v1.0.0 MVP)

#### 1 — Historical FX Rate Not Applied
All move lines use `fields.Date.today()` as the conversion date when computing
the company-currency equivalent of a foreign-currency check amount. For checks
with an `issue_date` in the past, the current exchange rate is applied rather
than the historical rate on the economic transaction date.

**Impact**: Minor variance in company-currency P&L/BS reporting when exchange
rates have moved significantly between the check date and the processing date.
The original-currency amounts (`amount_currency` on move lines) are always
exact and correct.

**Future improvement** (post-MVP): Pass the workflow's intended date to
`currency._convert()` — e.g., `issue_date` for registration, `deposit_date`
for deposit, etc. — to use the rate that was active on that day.

#### 2 — Invoice Auto-Reconciliation Deferred to Phase 5
The `invoice_ids` M2M field correctly links a check to customer/vendor invoices,
but Phase 3 does not automatically mark those invoices as paid or reconcile
their open move lines with the PDC entries.

**Impact**: Invoices linked to a cleared/paid check remain "open" in the AR/AP
aging report until Phase 5 wizards are used or the user reconciles manually
through standard Odoo accounting.

**Resolution in Phase 5**: The deposit/clear/pay wizards will collect the
user's invoice selection and call `account.move.line.reconcile()` to properly
close the open items.

---

## Unreleased Phases

| Phase | Content | Status |
|---|---|---|
| Phase 4 | 8 reports (PDF + Excel): receipt voucher, delivery receipt, check print, aging, partner statement, under collection, due soon, bounced | Pending |
| Phase 5 | 6 wizards + cron + mail templates + default data | Pending |
| Phase 6 | Demo data | Pending |
| Phase 7 | i18n polish, Apps Store materials | Pending |
