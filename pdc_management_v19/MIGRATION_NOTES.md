# PDC Management — Odoo 17 → 19 Migration Notes

## Overview

| Item | Value |
|---|---|
| Migration started | 2026-05-01 |
| Source version | 17.0.1.0.0 |
| Target version | 19.0.2.0.0 |
| Source module | `pdc_management/` |
| Target module | `pdc_management_v19/` |

---

## Breaking Changes — Odoo 19

### 1. `<tree>` renamed to `<list>` (Phase 2)

**Status:** Pending (Phase 2)

**What changed:**
In Odoo 17, both `<tree>` and `<list>` tags were accepted for list views,
with `<tree>` being the historical name. In Odoo 18/19, `<tree>` is fully
deprecated and will trigger warnings or errors. The canonical tag is now
`<list>`.

**Scope in this module:**
- `views/pdc_check_views.xml` — main list view + 2 inline trees (invoices, operations pages)
- `views/pdc_check_book_views.xml` — list view
- `views/pdc_bank_views.xml` — list view
- `views/pdc_bank_layout_views.xml` — list view
- `views/pdc_bounce_reason_views.xml` — list view
- `views/pdc_check_operation_views.xml` — list view
- `views/account_journal_views.xml` — list view
- `views/account_payment_views.xml` — list view
- `views/res_partner_views.xml` — list view
- `views/res_config_settings_views.xml` — may have inline trees
- `wizards/*.xml` — wizard list views
- `reports/*.xml` — report list views (if any)

**Pattern change:**
```xml
<!-- Before (Odoo 17) -->
<tree string="..." decoration-success="...">
    ...
</tree>

<!-- After (Odoo 19) -->
<list string="..." decoration-success="...">
    ...
</list>
```

**`view_mode` strings:**
```python
# Before
'view_mode': 'tree,form'

# After
'view_mode': 'list,form'
```

Note: The *action* `view_mode` fields in this module already use `list`
(e.g. `list,kanban,form,pivot,graph,calendar`), but the Python smart-button
action dicts in `pdc_check.py` lines 1208, 1218, 1228 still use `'tree,form'`
— those will be fixed in Phase 3.

**Sources:**
- Odoo 17→18 Migration Guide: "The `tree` view type has been renamed to `list`"
- Odoo 18 Upgrade Technical Notes (official): `<tree>` → `<list>` everywhere
- Community consensus: this change was introduced in Odoo 17 (both valid) and
  enforced from Odoo 18 onwards

---

### 2. Chatter Widget (Phase 2)

**Status:** Already correct — no change needed

**Observation:**
The v17 module already uses the simplified `<chatter/>` syntax (introduced in
Odoo 17) in `views/pdc_check_views.xml`. This is the same syntax used in
Odoo 19. No migration needed.

```xml
<!-- Current (already correct for Odoo 19) -->
<chatter/>
```

The old multi-element pattern has been absent from this module since its
initial development on Odoo 17.

---

### 3. Python API Changes (Phase 3)

**Status:** Pending (Phase 3)

#### 3a. `view_mode: 'tree,form'` in Python action dicts

Smart-button actions in `pdc_check.py` return dicts with `'view_mode': 'tree,form'`.
These need to become `'view_mode': 'list,form'` for Odoo 19.

Affected: `action_view_moves`, `action_view_invoices`, `action_view_operations`
in `models/pdc_check.py`.

#### 3b. `name_get()` deprecation

In Odoo 17, `name_get()` was still the standard way to compute display names.
In Odoo 18+, `name_get()` is deprecated in favour of overriding the
`display_name` computed field directly:

```python
# Before (Odoo 17)
def name_get(self):
    return [(rec.id, f"{rec.name} [{rec.code}]") for rec in self]

# After (Odoo 19)
def _compute_display_name(self):
    for rec in self:
        rec.display_name = f"{rec.name} [{rec.code}]"
```

Scope: Must check all model files for `name_get` overrides.

#### 3c. `@api.returns` deprecation

`@api.returns` was soft-deprecated in Odoo 17 and is removed in Odoo 19.
Any method decorated with `@api.returns('self')` must be updated.

Scope: Must audit all model files.

#### 3d. ORM `(4, id)` command in M2M writes

The ORM `(4, id)` command (link without replace) remains valid in Odoo 19
but is worth noting: this module uses it in `_post_move()` and
`_reverse_all_moves()` to add moves to `move_ids`. No change needed unless
Odoo 19 introduces a new preferred pattern.

#### 3e. `account.move` API changes

Odoo 18/19 introduced changes to the accounting ORM:
- `action_post()` is still valid
- `_reverse_moves()` may have signature changes — must verify

---

### 4. JavaScript / Owl (Phase 4)

**Status:** Pending (Phase 4)

This module has no custom JavaScript files in `static/src/`.
Only `static/description/` contains `icon.png`, `banner.png`, and
`index.html` — none of which require JS migration.

If Phase 4 audit confirms no JS, this section will be marked complete
with no changes.

---

### 5. Other XML Patterns to Verify (Phase 2)

| Pattern | Odoo 17 | Odoo 19 | Action |
|---|---|---|---|
| `<field ... invisible="1"/>` | Valid | Valid (also `column_invisible`) | No change |
| `invisible="not field"` expressions | Valid | Valid | No change |
| `decoration-*` attributes on `<tree>` | Valid | Valid (on `<list>`) | Tag rename only |
| `widget="badge"` | Valid | Valid | No change |
| `widget="statusbar"` | Valid | Valid | No change |
| `widget="monetary"` | Valid | Valid | No change |
| `<chatter/>` | Valid | Valid | No change |
| `t-name="card"` (Kanban) | Valid | Valid | No change |
| `optional="show/hide"` | Valid | Valid | No change |

---

### 6. `ir.actions.report` vs `ir.actions.act_window`

No changes anticipated. The module uses `ir.actions.act_window` for menus
and `ir.actions.report` for PDF reports — both remain valid in Odoo 19.

---

## Phase Completion Log

| Phase | Description | Status | Date |
|---|---|---|---|
| 1 | Initial module setup & manifest | ✅ Complete | 2026-05-01 |
| 2 | View migration (`<tree>` → `<list>`) | Pending | — |
| 3 | Python API updates | Pending | — |
| 4 | JS/Owl audit | Pending | — |
