# Universal Approval Engine Pro for Odoo 19

Production-oriented approval engine for any Odoo model.

## Included in the core module

- Per-model workflow configuration.
- Simple and advanced routing modes.
- Sequential, parallel, hybrid, and hierarchy-based approval stages.
- Conditional routing with Odoo domains.
- Approval matrix by model, company, amount, currency, and custom domain.
- Delegation: permanent, temporary, partial, and HR leave-oriented.
- SLA reminders and escalation rules.
- Secure email magic links for approve/reject actions.
- Notification queue for Odoo, email, WhatsApp, Telegram, SMS, push, Slack, and Teams connectors.
- Request modification, forwarding, withdrawal, reset, and re-submit flows.
- Live approval tracker on the request.
- Comment history, attachments, reason library, audit trail, and anomaly warnings.
- Re-approval detection based on tracked fields.
- Smart inbox and analytics views.
- Server action generator to add "Request Approval" to any configured model.

## Optional adapter modules

Install only the adapters for apps used by the customer:

- `universal_approval_purchase_19`: blocks Purchase Order confirmation until approval.
- `universal_approval_sale_19`: blocks Sales Order confirmation until approval.
- `universal_approval_account_19`: blocks invoice, bill, journal entry, and payment posting until approval.
- `universal_approval_stock_19`: blocks stock transfer and scrap validation until approval.
- `universal_approval_hr_19`: blocks leave validation until approval.
- `universal_approval_mrp_19`: blocks manufacturing confirmation and completion until approval.

## Quick setup

1. Install `universal_approval_engine_19`.
2. Add users to the Approval User, Manager, or Administrator groups.
3. Create an Approval Workflow and choose the target model.
4. Set the workflow trigger domain.
5. Add stages and approver sources.
6. Click **Create Request Action** on the workflow.
7. Open a target document and use **Action > Request Approval**.
8. Install optional adapter modules to lock Confirm/Post/Validate actions.

## Notes

- The core engine is generic and does not force Purchase/Sales/Accounting dependencies.
- External WhatsApp, Telegram, SMS, Push, Slack, and Teams delivery is queued through `universal.approval.notification`; connector modules can send and mark queue entries as sent.
- Inline buttons on native documents can be added per customer view. The generated server action already supports every configured model.
- Superusers or direct database administrators can always bypass business logic technically; this is normal in Odoo and ERP systems generally.

