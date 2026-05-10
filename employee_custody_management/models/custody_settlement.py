from odoo import _, Command, api, fields, models
from odoo.exceptions import UserError, ValidationError


class CustodySettlement(models.Model):
    _name = "custody.settlement"
    _description = "Custody Settlement"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _check_company_auto = True
    _order = "settlement_date desc, id desc"

    name = fields.Char(default="/", readonly=True, copy=False, tracking=True)
    settlement_date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    total_settled = fields.Monetary(
        compute="_compute_total_settled",
        store=True,
        compute_sudo=True,
        currency_field="currency_id",
        tracking=True,
    )
    move_id = fields.Many2one(
        comodel_name="account.move",
        string="Settlement Journal Entry",
        readonly=True,
        copy=False,
        check_company=True,
    )
    request_id = fields.Many2one(
        comodel_name="custody.request",
        required=True,
        tracking=True,
        check_company=True,
        domain="[('state', 'in', ('issued', 'partially_settled'))]",
    )
    employee_id = fields.Many2one(related="request_id.employee_id", store=True, readonly=True)
    partner_id = fields.Many2one(related="request_id.partner_id", store=True, readonly=True)
    line_ids = fields.One2many(
        comodel_name="custody.settlement.line",
        inverse_name="settlement_id",
        string="Settlement Lines",
        copy=True,
    )
    currency_id = fields.Many2one(related="request_id.currency_id", store=True, readonly=True)
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("posted", "Posted"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
        tracking=True,
        copy=False,
    )
    company_id = fields.Many2one(
        related="request_id.company_id",
        store=True,
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Assign settlement sequences."""
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                company = self.env["res.company"].browse(vals.get("company_id")) if vals.get("company_id") else self.env.company
                vals["name"] = self.env["ir.sequence"].with_company(company).next_by_code("custody.settlement.seq") or "/"
        return super().create(vals_list)

    @api.depends("line_ids.amount")
    def _compute_total_settled(self):
        """Compute the total settlement amount."""
        for settlement in self:
            settlement.total_settled = sum(settlement.line_ids.mapped("amount"))

    @api.constrains("total_settled", "request_id")
    def _check_total_settled(self):
        """Prevent over-settlement."""
        for settlement in self:
            if settlement.total_settled <= 0:
                continue
            remaining = settlement.request_id.remaining_amount
            if settlement.state == "draft" and settlement.total_settled > remaining:
                raise ValidationError(_(
                    "The settlement amount %(amount).2f exceeds the remaining custody balance %(remaining).2f.",
                    amount=settlement.total_settled,
                    remaining=remaining,
                ))

    def action_post(self):
        """Post the settlement journal entry and reconcile linked vendor bills."""
        for settlement in self:
            if settlement.state != "draft":
                continue
            settlement._validate_before_post()
            move = self.env["account.move"].create(settlement._prepare_move_vals())
            move.action_post()
            settlement.move_id = move
            settlement._reconcile_vendor_bill_lines()
            settlement.state = "posted"
            settlement.request_id._refresh_state_from_settlement()

    def action_cancel(self):
        """Cancel posted or draft settlements."""
        for settlement in self:
            if settlement.state == "cancelled":
                continue
            if settlement.move_id:
                settlement.move_id.line_ids.remove_move_reconcile()
                settlement.move_id.button_cancel()
            settlement.state = "cancelled"
            settlement.request_id._refresh_state_from_settlement()

    def _validate_before_post(self):
        """Validate settlement line content before accounting entry creation."""
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("Add at least one settlement line before posting."))
        if self.total_settled > self.request_id.remaining_amount:
            raise UserError(_(
                "This settlement exceeds the remaining custody balance. Reduce the lines to %(remaining).2f.",
                remaining=self.request_id.remaining_amount,
            ))
        for line in self.line_ids:
            line._validate_line()

    def _get_settlement_journal(self):
        """Return the journal used for the settlement entry."""
        self.ensure_one()
        return (
            self.line_ids.filtered(lambda line: line.type == "return_cash").mapped("journal_id")[:1]
            or self.company_id.custody_default_journal_id
            or self.env["account.journal"].search([
                ("company_id", "=", self.company_id.id),
                ("type", "=", "general"),
            ], limit=1)
        )

    def _prepare_move_vals(self):
        """Prepare the settlement account.move values."""
        self.ensure_one()
        journal = self._get_settlement_journal()
        if not journal:
            raise UserError(_("Configure an accounting journal before posting custody settlements."))
        line_commands = []
        for line in self.line_ids:
            line_commands.extend(line._prepare_move_line_commands())
        return {
            "move_type": "entry",
            "ref": self.name,
            "date": self.settlement_date,
            "journal_id": journal.id,
            "company_id": self.company_id.id,
            "currency_id": self.currency_id.id,
            "line_ids": line_commands,
        }

    def _reconcile_vendor_bill_lines(self):
        """Reconcile AP lines generated for vendor-bill settlement lines."""
        self.ensure_one()
        for line in self.line_ids.filtered(lambda item: item.type == "vendor_bill"):
            payable_lines = line.bill_id.line_ids.filtered(
                lambda item: item.account_id.account_type == "liability_payable" and not item.reconciled
            )
            settlement_lines = self.move_id.line_ids.filtered(
                lambda item: item.account_id in payable_lines.account_id
                and item.partner_id == line.bill_id.partner_id
                and not item.reconciled
            )
            for account in payable_lines.account_id:
                (payable_lines + settlement_lines).filtered(lambda item: item.account_id == account).reconcile()


class CustodySettlementLine(models.Model):
    _name = "custody.settlement.line"
    _description = "Custody Settlement Line"
    _check_company_auto = True
    _order = "settlement_id, sequence, id"

    sequence = fields.Integer(default=10)
    type = fields.Selection(
        selection=[
            ("return_cash", "Return Cash"),
            ("expense", "Expense"),
            ("vendor_bill", "Vendor Bill"),
        ],
        required=True,
        default="return_cash",
    )
    description = fields.Char(required=True, default=lambda self: _("Custody settlement"))
    amount = fields.Monetary(required=True, currency_field="currency_id")
    analytic_distribution = fields.Json(string="Analytic Distribution")
    analytic_precision = fields.Integer(
        store=False,
        default=lambda self: self.env["decimal.precision"].precision_get("Percentage Analytic"),
    )
    settlement_id = fields.Many2one(
        comodel_name="custody.settlement",
        required=True,
        ondelete="cascade",
        check_company=True,
    )
    request_id = fields.Many2one(related="settlement_id.request_id", store=True, readonly=True)
    employee_id = fields.Many2one(related="settlement_id.employee_id", store=True, readonly=True)
    partner_id = fields.Many2one(related="settlement_id.partner_id", store=True, readonly=True)
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Receiving Journal",
        domain="[('type', 'in', ('cash', 'bank'))]",
        check_company=True,
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
        check_company=True,
    )
    currency_id = fields.Many2one(related="settlement_id.currency_id", store=True, readonly=True)
    company_id = fields.Many2one(related="settlement_id.company_id", store=True, readonly=True)

    @api.constrains("amount")
    def _check_amount(self):
        """Ensure line amounts are positive."""
        for line in self:
            if line.amount <= 0:
                raise ValidationError(_("Settlement line amounts must be greater than zero."))

    def _validate_line(self):
        """Validate type-specific settlement line requirements."""
        self.ensure_one()
        if self.type == "return_cash" and not self.journal_id:
            raise UserError(_("Select a receiving cash/bank journal for return-cash settlement lines."))
        if self.type == "return_cash" and not self.journal_id.default_account_id:
            raise UserError(_("The receiving journal must have a default cash/bank account."))
        if self.type == "expense" and not self.account_id:
            raise UserError(_("Select an expense account for expense settlement lines."))
        if self.type == "vendor_bill" and not self.bill_id:
            raise UserError(_("Select a posted vendor bill for vendor-bill settlement lines."))

    def _prepare_move_line_commands(self):
        """Prepare debit and custody credit move-line commands for this line."""
        self.ensure_one()
        company = self.company_id
        company_currency = company.currency_id
        balance = self.currency_id._convert(self.amount, company_currency, company, self.settlement_id.settlement_date)
        custody_account = self.request_id.custody_account_id
        if self.type == "return_cash":
            debit_account = self.journal_id.default_account_id
            debit_partner = False
            debit_name = self.description or _("Returned custody cash")
        elif self.type == "expense":
            debit_account = self.account_id
            debit_partner = False
            debit_name = self.description or _("Custody expense")
        else:
            payable_line = self.bill_id.line_ids.filtered(lambda item: item.account_id.account_type == "liability_payable")[:1]
            debit_account = payable_line.account_id
            debit_partner = self.bill_id.partner_id
            debit_name = self.description or _("Custody payment for %s") % self.bill_id.name
        debit_vals = {
            "name": debit_name,
            "account_id": debit_account.id,
            "partner_id": debit_partner.id if debit_partner else False,
            "debit": balance,
            "credit": 0.0,
            "currency_id": self.currency_id.id,
            "amount_currency": self.amount,
            "analytic_distribution": self.analytic_distribution if self.type == "expense" else False,
        }
        credit_vals = {
            "name": _("Custody Settlement - %s") % self.employee_id.name,
            "account_id": custody_account.id,
            "partner_id": self.partner_id.id,
            "debit": 0.0,
            "credit": balance,
            "currency_id": self.currency_id.id,
            "amount_currency": -self.amount,
        }
        return [
            Command.create(debit_vals),
            Command.create(credit_vals),
        ]
