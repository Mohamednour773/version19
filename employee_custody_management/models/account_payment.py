from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    is_custody_payment = fields.Boolean(
        compute="_compute_is_custody_payment",
        store=True,
        string="Custody Payment",
    )
    custody_employee_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Custody Holder",
        domain="[('is_custody_holder', '=', True)]",
        copy=False,
        tracking=True,
        check_company=True,
    )
    custody_partner_id = fields.Many2one(
        comodel_name="res.partner",
        related="custody_employee_id.work_contact_id",
        store=True,
        readonly=True,
    )
    custody_request_id = fields.Many2one(
        comodel_name="custody.request",
        string="Custody Request",
        copy=False,
        check_company=True,
        domain="[('state', 'in', ('issued', 'partially_settled'))]",
    )
    custody_balance_before = fields.Monetary(
        compute="_compute_custody_balances",
        currency_field="currency_id",
        string="Custody Balance Before",
    )
    custody_balance_after = fields.Monetary(
        compute="_compute_custody_balances",
        currency_field="currency_id",
        string="Custody Balance After",
    )

    @api.depends("journal_id.is_custody_journal")
    def _compute_is_custody_payment(self):
        """Flag payments created through a custody journal."""
        for payment in self:
            payment.is_custody_payment = bool(payment.journal_id.is_custody_journal)

    @api.depends("custody_employee_id", "amount", "currency_id", "date", "company_id")
    def _compute_custody_balances(self):
        """Compute before/after custody balance preview in payment currency."""
        for payment in self:
            if not payment.custody_employee_id:
                payment.custody_balance_before = 0.0
                payment.custody_balance_after = 0.0
                continue
            balance = payment.custody_employee_id._get_custody_balance(
                company=payment.company_id,
                date=payment.date,
                currency=payment.currency_id,
            )
            payment.custody_balance_before = balance
            payment.custody_balance_after = balance - payment.amount

    @api.onchange("custody_employee_id", "amount", "currency_id", "date")
    def _onchange_custody_employee_id(self):
        """Suggest the oldest sufficient open custody request for the holder."""
        for payment in self:
            if payment.is_custody_payment and payment.custody_employee_id:
                payment.custody_request_id = payment._find_suitable_custody_request()

    @api.constrains("is_custody_payment", "custody_employee_id", "custody_request_id")
    def _check_custody_payment_fields(self):
        """Validate persisted custody payment links outside draft state."""
        for payment in self.filtered(lambda item: item.is_custody_payment and item.state not in (False, "draft")):
            if not payment.custody_employee_id:
                raise ValidationError(_("Select the employee holding the custody before confirming the payment."))
            if payment.custody_request_id and payment.custody_request_id.employee_id != payment.custody_employee_id:
                raise ValidationError(_("The linked custody request belongs to a different employee."))

    def _find_suitable_custody_request(self):
        """Find the oldest open request with enough remaining amount for this payment."""
        self.ensure_one()
        if not self.custody_employee_id:
            return self.env["custody.request"]
        requests = self.env["custody.request"].search([
            ("employee_id", "=", self.custody_employee_id.id),
            ("company_id", "=", self.company_id.id),
            ("state", "in", ("issued", "partially_settled")),
        ], order="request_date, id")
        for request in requests:
            remaining = request.currency_id._convert(
                request.remaining_amount,
                self.currency_id,
                self.company_id,
                self.date,
            )
            if self.currency_id.compare_amounts(remaining, self.amount) >= 0:
                return request
        return requests[:1]

    def _validate_custody_payment(self):
        """Validate custody payment requirements before posting."""
        self.ensure_one()
        if not self.is_custody_payment:
            return
        if self.payment_type != "outbound" or self.partner_type != "supplier":
            raise UserError(_("Custody journals can only be used for outbound vendor payments."))
        if not self.company_id.custody_receivable_account_id:
            raise UserError(_("Configure the Custody Receivable account in Accounting Settings."))
        if not self.custody_employee_id:
            raise UserError(_("Select the custody-holding employee before confirming this payment."))
        self.custody_employee_id._ensure_custody_partner()
        if self.partner_id == self.custody_partner_id:
            raise UserError(_(
                "The payment vendor cannot be the same partner as the custody holder. Select the vendor bill partner "
                "as Customer/Vendor and the employee only in Custody Holder."
            ))
        if not self.custody_request_id:
            self.custody_request_id = self._find_suitable_custody_request()
        balance = self.custody_employee_id._get_custody_balance(
            company=self.company_id,
            date=self.date,
            currency=self.currency_id,
        )
        if self.currency_id.compare_amounts(balance, self.amount) < 0:
            raise UserError(_(
                "%(employee)s does not have enough custody balance. Available: %(balance).2f; payment: %(amount).2f.",
                employee=self.custody_employee_id.name,
                balance=balance,
                amount=self.amount,
            ))

    def _get_valid_liquidity_accounts(self):
        """Treat the custody receivable account as the liquidity line for custody payments."""
        self.ensure_one()
        accounts = super()._get_valid_liquidity_accounts()
        if self.is_custody_payment and self.company_id.custody_receivable_account_id:
            accounts |= self.company_id.custody_receivable_account_id
        return accounts

    def _prepare_move_line_default_vals(self, write_off_line_vals=None, force_balance=None):
        """Rewrite custody payment liquidity lines to the employee custody receivable partner ledger."""
        self.ensure_one()
        line_vals_list = super()._prepare_move_line_default_vals(
            write_off_line_vals=write_off_line_vals,
            force_balance=force_balance,
        )
        if not self.is_custody_payment or not self.custody_employee_id:
            return line_vals_list
        custody_account = self.company_id.custody_receivable_account_id
        if not custody_account:
            raise UserError(_("Configure the Custody Receivable account in Accounting Settings."))
        liquidity_vals = line_vals_list[0] if line_vals_list else False
        if liquidity_vals:
            liquidity_vals.update({
                "account_id": custody_account.id,
                "partner_id": self.custody_partner_id.id,
                "name": _("Custody Payment - %(employee)s - %(reference)s") % {
                    "employee": self.custody_employee_id.name,
                    "reference": self.memo or self.name or "",
                },
            })
        return line_vals_list

    def action_post(self):
        """Validate custody balances and refresh linked requests after posting."""
        for payment in self:
            payment._validate_custody_payment()
        result = super().action_post()
        self.mapped("custody_request_id")._refresh_state_from_settlement()
        return result

    def action_cancel(self):
        """Refresh linked custody requests when custody payments are cancelled."""
        requests = self.mapped("custody_request_id")
        result = super().action_cancel()
        requests._refresh_state_from_settlement()
        return result


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    is_custody_payment = fields.Boolean(
        compute="_compute_custody_register_values",
        string="Custody Payment",
    )
    custody_employee_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Custody Holder",
        domain="[('is_custody_holder', '=', True)]",
        check_company=True,
    )
    custody_partner_id = fields.Many2one(
        comodel_name="res.partner",
        related="custody_employee_id.work_contact_id",
        readonly=True,
    )
    custody_request_id = fields.Many2one(
        comodel_name="custody.request",
        string="Custody Request",
        domain="[('state', 'in', ('issued', 'partially_settled'))]",
        check_company=True,
    )
    custody_balance_before = fields.Monetary(
        compute="_compute_custody_register_values",
        currency_field="currency_id",
        string="Custody Balance Before",
    )
    custody_balance_after = fields.Monetary(
        compute="_compute_custody_register_values",
        currency_field="currency_id",
        string="Custody Balance After",
    )

    @api.depends("journal_id.is_custody_journal", "custody_employee_id", "amount", "currency_id", "payment_date")
    def _compute_custody_register_values(self):
        """Compute custody visibility and balance preview on the register payment wizard."""
        for wizard in self:
            wizard.is_custody_payment = bool(wizard.journal_id.is_custody_journal)
            if wizard.is_custody_payment and wizard.custody_employee_id:
                balance = wizard.custody_employee_id._get_custody_balance(
                    company=wizard.company_id,
                    date=wizard.payment_date,
                    currency=wizard.currency_id,
                )
                wizard.custody_balance_before = balance
                wizard.custody_balance_after = balance - wizard.amount
            else:
                wizard.custody_balance_before = 0.0
                wizard.custody_balance_after = 0.0

    @api.onchange("journal_id", "custody_employee_id", "amount", "currency_id", "payment_date")
    def _onchange_custody_values(self):
        """Suggest an open custody request when the custody holder changes."""
        for wizard in self:
            if wizard.is_custody_payment and wizard.custody_employee_id:
                wizard.custody_request_id = wizard._find_suitable_custody_request()
            else:
                wizard.custody_request_id = False

    def _find_suitable_custody_request(self):
        """Find an open custody request that can cover this wizard amount."""
        self.ensure_one()
        requests = self.env["custody.request"].search([
            ("employee_id", "=", self.custody_employee_id.id),
            ("company_id", "=", self.company_id.id),
            ("state", "in", ("issued", "partially_settled")),
        ], order="request_date, id")
        for request in requests:
            remaining = request.currency_id._convert(
                request.remaining_amount,
                self.currency_id,
                self.company_id,
                self.payment_date,
            )
            if self.currency_id.compare_amounts(remaining, self.amount) >= 0:
                return request
        return requests[:1]

    def _validate_custody_register(self):
        """Validate custody data before creating account.payment records."""
        self.ensure_one()
        if not self.is_custody_payment:
            return
        if self.payment_type != "outbound" or self.partner_type != "supplier":
            raise UserError(_("Custody journals can only be used for outbound vendor bill payments."))
        if not self.custody_employee_id:
            raise UserError(_("Select the custody holder before creating the payment."))
        self.custody_employee_id._ensure_custody_partner()
        if self.partner_id == self.custody_partner_id:
            raise UserError(_("Select the vendor as the payment partner and the employee as the custody holder."))
        balance = self.custody_employee_id._get_custody_balance(
            company=self.company_id,
            date=self.payment_date,
            currency=self.currency_id,
        )
        if self.currency_id.compare_amounts(balance, self.amount) < 0:
            raise UserError(_(
                "%(employee)s does not have enough custody balance. Available: %(balance).2f; payment: %(amount).2f.",
                employee=self.custody_employee_id.name,
                balance=balance,
                amount=self.amount,
            ))
        if not self.custody_request_id:
            self.custody_request_id = self._find_suitable_custody_request()

    def _inject_custody_payment_vals(self, payment_vals):
        """Add custody fields to payment creation values from the register wizard."""
        self.ensure_one()
        if self.is_custody_payment:
            payment_vals.update({
                "custody_employee_id": self.custody_employee_id.id,
                "custody_request_id": self.custody_request_id.id,
            })
        return payment_vals

    def _create_payment_vals_from_wizard(self, batch_result):
        """Pass custody fields when the editable register payment wizard creates a payment."""
        self._validate_custody_register()
        return self._inject_custody_payment_vals(super()._create_payment_vals_from_wizard(batch_result))

    def _create_payment_vals_from_batch(self, batch_result):
        """Pass custody fields when batch register payment creates payments."""
        self._validate_custody_register()
        return self._inject_custody_payment_vals(super()._create_payment_vals_from_batch(batch_result))
