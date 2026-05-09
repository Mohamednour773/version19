# Configurable Approval Workflow — Odoo 19 Module

## Overview

A production-ready, configurable approval workflow engine for Odoo 19.
Attach sequential multi-stage approvals to **any Odoo model** without modifying
the target module's source code (for blocking enforcement, see Integration below).

---

## Module Structure

```
approval_workflow/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── approval_workflow_config.py   # Master workflow configuration per model
│   ├── approval_stage.py             # Individual approval stages (sequential)
│   ├── approval_request.py           # Request instance + line decisions
│   └── approval_mixin.py             # Abstract mixin + enforcer helper
├── wizard/
│   └── approval_action_wizard.py     # Refuse + blocked-action wizards
├── views/
│   ├── approval_workflow_config_views.xml
│   ├── approval_stage_views.xml
│   ├── approval_request_views.xml
│   ├── approval_dashboard_views.xml
│   └── approval_workflow_menus.xml
├── wizard/
│   └── approval_action_wizard_views.xml
├── security/
│   ├── approval_workflow_security.xml
│   └── ir.model.access.csv
├── data/
│   └── approval_workflow_data.xml    # Sequence
└── static/src/
    ├── css/approval_workflow.css
    └── js/approval_status_widget.js
```

---

## Installation

1. Copy the `approval_workflow` folder into your Odoo addons directory.
2. Update the apps list: `Settings → Activate developer mode → Apps → Update Apps List`.
3. Search for **"Configurable Approval Workflow"** and click **Install**.

---

## Quick Start: Configuring a Workflow

### Step 1 — Create a Workflow Configuration

Navigate to **Approvals → Configuration → Workflow Configurations → New**.

| Field | Description |
|---|---|
| Workflow Name | Human-readable label |
| Target Model | Select the Odoo model (e.g. `Purchase Order`) |
| Notify Requester | Email the submitter when status changes |
| Notify Next Approver | Email each approver when it's their turn |

### Step 2 — Define Approval Stages

In the **Approval Stages** tab, add rows for each sequential step:

| Field | Description |
|---|---|
| Sequence | Order (lower = first) — drag to reorder |
| Stage Name | e.g. "Manager Approval", "Finance Review" |
| Approver Type | `Specific User`, `User Group`, or `Dynamic Field` |
| Approver | The user/group/field that must approve |
| Allow Self-Approval | Let the requester approve their own document |
| Auto-approve if Missing | Skip stage if no approver can be resolved |
| Only Apply If | Odoo domain — stage only required if record matches |

### Step 3 — Configure Action Blocking

In the **Action Blocking** tab:

- **Block Write/Edit**: Prevents editing the record while approval is pending
- **Block Delete**: Prevents record deletion
- **Block Custom Methods**: Comma-separated method names (e.g. `action_confirm,action_validate`)

---

## Integration: Enabling Blocking on a Target Model

The approval blocking check must be hooked into the target model.
There are **three approaches** — choose the one that fits your setup:

### Option A — Inherit the Mixin (recommended for custom modules)

```python
# In your custom module's model:
class PurchaseOrder(models.Model):
    _name = 'purchase.order'
    _inherit = ['purchase.order', 'approval.mixin']

    def action_confirm(self):
        self._check_approval_block('action_confirm')
        return super().action_confirm()

    def write(self, vals):
        self._check_approval_block('write')
        return super().write(vals)
```

### Option B — Standalone Override (no source modification needed)

Create a small bridge module that patches the target model:

```python
# my_approval_bridge/models/purchase_order.py
from odoo import models, _
from odoo.exceptions import UserError

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def action_confirm(self):
        enforcer = self.env['approval.enforcer']
        result = enforcer.check_and_block(
            self._name, self.ids, 'action_confirm'
        )
        if result.get('blocked'):
            raise UserError(_(
                'Action blocked: pending approvals exist for this document.\n'
                'Please complete all approvals before confirming.'
            ))
        return super().action_confirm()
```

### Option C — Server Actions (no-code approach)

Use **Settings → Technical → Actions → Server Actions** to create
a "Before Action" hook that calls `approval.enforcer` `check_and_block`.

---

## Adding the "Submit for Approval" Button to Any Form View

Inherit the target model's form view and add the button:

```xml
<!-- In your bridge module or theme: -->
<record id="view_purchase_order_form_approval" model="ir.ui.view">
    <field name="name">purchase.order.form.approval</field>
    <field name="model">purchase.order</field>
    <field name="inherit_id" ref="purchase.purchase_order_form"/>
    <field name="arch" type="xml">
        <xpath expr="//header/button[1]" position="before">
            <button name="action_submit_for_approval"
                    string="Submit for Approval"
                    type="object"
                    class="btn-warning"
                    invisible="approval_state in ('pending','in_progress','approved')"/>
        </xpath>
    </field>
</record>
```

The `action_submit_for_approval` method is provided by `approval.mixin`.

---

## Approval Dashboard

All approval-related views are available under the **Approvals** top menu:

| Menu | Description |
|---|---|
| My Approval Queue | Lines pending specifically **your** approval — approve/refuse in one click |
| My Pending Requests | Requests **you submitted** that are still in progress |
| All Approvals → Pending | All pending approval lines across all workflows |
| All Approvals → All Requests | Full request list with kanban/list/form |
| Configuration → Workflow Configurations | Manage workflow configs (managers only) |

---

## Approver Types

### Specific User
A single named user must approve. Simplest option.

### User Group
Any user in the group can approve (OR logic).
With **Require ALL Group Members**: every member must approve (AND logic).

### Dynamic Field
A Many2one field on the target model pointing to `res.users`.
Useful for "the manager of whoever created the document" patterns.
Example: select the `user_id` or `manager_id` field.

---

## Conditional Stages

Use the **Only Apply If** domain to make stages optional:

```python
# Only require Finance approval for large orders:
[('amount_total', '>', 10000)]

# Only for specific department:
[('department_id.name', '=', 'Engineering')]
```

---

## Security Groups

| Group | Access |
|---|---|
| `Approval Workflow / User` | Submit requests, approve own assigned lines |
| `Approval Workflow / Manager` | Full configuration access, view all requests |

---

## Sequence of Events

```
User submits document
        ↓
approval.request created (state: draft)
        ↓
action_submit() called
        ↓
approval.request.line records created (one per approver per applicable stage)
        ↓
state → 'in_progress', current_stage_id = Stage 1
        ↓
Stage 1 approver(s) notified by email
        ↓
Approver clicks Approve / Refuse
        ↓
[If Refused] → request.state = 'refused', all pending lines cancelled, requester notified
[If Approved] → check if stage complete
        ↓
[Stage Complete] → advance to Stage 2, notify next approver
        ↓
[All Stages Complete] → request.state = 'approved', requester notified
        ↓
Action blocking lifted — document can now be edited/confirmed/validated
```

---

## Frequently Asked Questions

**Q: Can I have parallel (non-sequential) approvals?**
A: The engine is sequential by design. For parallel approvals within a stage,
use the "User Group" approver type with "Require ALL Group Members" enabled.

**Q: Can a refused request be resubmitted?**
A: Yes. Cancel the refused request → Reset to Draft → resubmit.

**Q: Does this work with multi-company?**
A: The sequence is company-agnostic. For multi-company, add a domain filter
on the workflow config or stage conditions.

**Q: Can I send custom email templates?**
A: Override `_notify_approvers` and `_notify_requester_approved` in a subclass
or use Odoo's mail template system by extending the notification methods.

---

## Changelog

| Version | Changes |
|---|---|
| 19.0.1.0.0 | Initial release — sequential approvals, dashboard, mixin |
