from odoo import _, Command, api, fields, models
from odoo.exceptions import UserError


class CustodySettlementWizard(models.TransientModel):
    _name = "custody.settlement.wizard"
    _description = "Custody Settlement Wizard"

    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        required=True,
        domain="[('is_custody_holder', '=', True)]",
    )
    request_ids = fields.Many2many(
        comodel_name="custody.request",
        string="Open Custody Requests",
        domain="[('state', 'in', ('issued', 'partially_settled'))]",
    )
    line_ids = fields.One2many(
        comodel_name="custody.settlement.wizard.line",
        inverse_name="wizard_id",
        string="Settlement Lines",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        required=True,
    )

    @api.model
    def default_get(self, fields_list):
        """Pre-populate the wizard from the active employee."""
        values = super().default_get(fields_list)
        employee = self.env["hr.employee"].browse(values.get("employee_id") or self.env.context.get("active_id"))
        if employee:
            requests = self.env["custody.request"].search([
                ("employee_id", "=", employee.id),
                ("state", "in", ("issued", "partially_settled")),
            ])
            values["employee_id"] = employee.id
            values["request_ids"] = [Command.set(requests.ids)]
            values["line_ids"] = [
                Command.create({
                    "request_id": request.id,
                    "type": "return_cash",
                    "amount": request.remaining_amount,
                    "description": _("Return remaining custody for %s") % request.name,
                })
                for request in requests
            ]
        return values

    def action_confirm(self):
        """Create and post custody settlements from wizard lines."""
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("Add at least one settlement line."))
        settlements = self.env["custody.settlement"]
        for request, lines in self.line_ids.grouped("request_id").items():
            settlement = self.env["custody.settlement"].create({
                "request_id": request.id,
                "settlement_date": fields.Date.context_today(self),
                "line_ids": [
                    Command.create(line._prepare_settlement_line_vals())
                    for line in lines
                ],
            })
            settlement.action_post()
            settlements |= settlement
        return settlements._get_records_action(name=_("Custody Settlements"))


class CustodySettlementWizardLine(models.TransientModel):
    _name = "custody.settlement.wizard.line"
    _description = "Custody Settlement Wizard Line"

    wizard_id = fields.Many2one(
        comodel_name="custody.settlement.wizard",
        required=True,
        ondelete="cascade",
    )
    request_id = fields.Many2one(
        comodel_name="custody.request",
        required=True,
        domain="[('state', 'in', ('issued', 'partially_settled'))]",
    )
    type = fields.Selection(
        selection=[
            ("return_cash", "Return Cash"),
            ("expense", "Expense"),
            ("vendor_bill", "Vendor Bill"),
        ],
        required=True,
        default="return_cash",
    )
    description = fields.Char(required=True)
    amount = fields.Monetary(required=True, currency_field="currency_id")
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Receiving Journal",
        domain="[('type', 'in', ('cash', 'bank'))]",
    )
    account_id = fields.Many2one(
        comodel_name="account.account",
        string="Expense Account",
        domain="[('account_type', 'in', ('expense', 'expense_depreciation', 'expense_direct_cost'))]",
    )
    bill_id = fields.Many2one(
        comodel_name="account.move",
        string="Vendor Bill",
        domain="[('move_type', '=', 'in_invoice'), ('state', '=', 'posted'), ('payment_state', '!=', 'paid')]",
    )
    analytic_distribution = fields.Json(string="Analytic Distribution")
    analytic_precision = fields.Integer(
        store=False,
        default=lambda self: self.env["decimal.precision"].precision_get("Percentage Analytic"),
    )
    currency_id = fields.Many2one(related="request_id.currency_id", readonly=True)

    def _prepare_settlement_line_vals(self):
        """Prepare a real settlement line from a wizard line."""
        self.ensure_one()
        return {
            "request_id": self.request_id.id,
            "type": self.type,
            "description": self.description,
            "amount": self.amount,
            "journal_id": self.journal_id.id,
            "account_id": self.account_id.id,
            "bill_id": self.bill_id.id,
            "analytic_distribution": self.analytic_distribution,
        }
