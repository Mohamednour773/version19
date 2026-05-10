import logging

from odoo import _, Command, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class CustodyRequest(models.Model):
    _name = "custody.request"
    _description = "Custody Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _check_company_auto = True
    _order = "request_date desc, id desc"

    name = fields.Char(default="/", readonly=True, copy=False, tracking=True)
    request_date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    expected_settlement_date = fields.Date(required=True, tracking=True)
    amount = fields.Monetary(required=True, tracking=True)
    description = fields.Text(required=True, tracking=True)
    analytic_distribution = fields.Json(string="Analytic Distribution")
    analytic_precision = fields.Integer(
        store=False,
        default=lambda self: self.env["decimal.precision"].precision_get("Percentage Analytic"),
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        required=True,
        default=lambda self: self.env.company.currency_id,
        tracking=True,
    )
    custody_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Custody Receivable Account",
        required=True,
        readonly=True,
        domain="[('account_type', '=', 'asset_receivable')]",
        tracking=True,
    )
    settled_amount = fields.Monetary(
        compute="_compute_settlement_amounts",
        store=True,
        compute_sudo=True,
        tracking=True,
    )
    remaining_amount = fields.Monetary(
        compute="_compute_settlement_amounts",
        store=True,
        compute_sudo=True,
    )
    payment_id = fields.Many2one(
        comodel_name="account.payment",
        string="Issuance Payment",
        readonly=True,
        copy=False,
        check_company=True,
    )
    move_id = fields.Many2one(
        comodel_name="account.move",
        related="payment_id.move_id",
        store=True,
        readonly=True,
    )
    custody_payment_ids = fields.One2many(
        comodel_name="account.payment",
        inverse_name="custody_request_id",
        string="Vendor Custody Payments",
        readonly=True,
    )
    custody_payment_count = fields.Integer(compute="_compute_smart_counts")
    linked_vendor_bill_ids = fields.Many2many(
        comodel_name="account.move",
        compute="_compute_smart_counts",
        string="Linked Vendor Bills",
    )
    linked_vendor_bill_count = fields.Integer(compute="_compute_smart_counts")
    settlement_ids = fields.One2many(
        comodel_name="custody.settlement",
        inverse_name="request_id",
        string="Settlements",
        readonly=True,
    )
    settlement_count = fields.Integer(compute="_compute_smart_counts")
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        required=True,
        domain="[('is_custody_holder', '=', True)]",
        tracking=True,
        check_company=True,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        related="employee_id.work_contact_id",
        store=True,
        readonly=True,
    )
    category_id = fields.Many2one(
        comodel_name="custody.category",
        required=True,
        tracking=True,
        check_company=True,
    )
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Funding Journal",
        required=True,
        domain="[('type', 'in', ('cash', 'bank'))]",
        tracking=True,
        check_company=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Requester",
        default=lambda self: self.env.user,
        tracking=True,
    )
    approver_id = fields.Many2one(
        comodel_name="res.users",
        string="Approver",
        readonly=True,
        copy=False,
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("approved", "Approved"),
            ("issued", "Issued"),
            ("partially_settled", "Partially Settled"),
            ("settled", "Settled"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
        tracking=True,
        copy=False,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Assign the custody request sequence and default custody account."""
        for vals in vals_list:
            company = self.env["res.company"].browse(vals.get("company_id")) if vals.get("company_id") else self.env.company
            vals.setdefault("currency_id", company.currency_id.id)
            vals.setdefault("custody_account_id", company.custody_receivable_account_id.id)
            if vals.get("name", "/") == "/":
                vals["name"] = self.env["ir.sequence"].with_company(company).next_by_code("custody.request.seq") or "/"
        return super().create(vals_list)

    @api.onchange("company_id")
    def _onchange_company_id(self):
        if self.company_id:
            self.custody_account_id = self.company_id.custody_receivable_account_id
            self.currency_id = self.company_id.currency_id

    @api.onchange("journal_id")
    def _onchange_journal_id(self):
        if self.journal_id.currency_id:
            self.currency_id = self.journal_id.currency_id

    @api.constrains("amount", "request_date", "expected_settlement_date")
    def _check_request_values(self):
        """Validate positive amounts and sane settlement dates."""
        for request in self:
            if request.amount <= 0:
                raise ValidationError(_("The custody amount must be greater than zero."))
            if request.expected_settlement_date < request.request_date:
                raise ValidationError(_("The expected settlement date must be on or after the request date."))

    @api.depends(
        "amount",
        "currency_id",
        "settlement_ids.state",
        "settlement_ids.total_settled",
        "custody_payment_ids.state",
        "custody_payment_ids.amount",
        "custody_payment_ids.currency_id",
        "custody_payment_ids.is_custody_payment",
    )
    def _compute_settlement_amounts(self):
        """Compute settled and remaining amounts from posted settlements and linked custody payments."""
        for request in self:
            settled = 0.0
            for settlement in request.settlement_ids.filtered(lambda item: item.state == "posted"):
                settled += settlement.currency_id._convert(
                    settlement.total_settled,
                    request.currency_id,
                    request.company_id,
                    settlement.settlement_date,
                )
            for payment in request.custody_payment_ids.filtered(
                lambda item: item.is_custody_payment and item.state not in ("draft", "canceled", "rejected")
            ):
                settled += payment.currency_id._convert(
                    payment.amount,
                    request.currency_id,
                    request.company_id,
                    payment.date,
                )
            request.settled_amount = min(settled, request.amount)
            request.remaining_amount = max(request.amount - request.settled_amount, 0.0)

    def _compute_smart_counts(self):
        """Compute request form smart-button counters."""
        for request in self:
            custody_payments = request.custody_payment_ids.filtered("is_custody_payment")
            bills = custody_payments.mapped("reconciled_bill_ids")
            request.custody_payment_count = len(custody_payments)
            request.linked_vendor_bill_ids = bills
            request.linked_vendor_bill_count = len(bills)
            request.settlement_count = len(request.settlement_ids)

    def action_submit(self):
        """Submit draft requests for approval."""
        for request in self:
            if request.state != "draft":
                continue
            request._validate_ready_for_approval()
            request.state = "submitted"

    def action_approve(self):
        """Approve submitted custody requests after policy validations."""
        if not self.env.su and not self.env.user.has_group("employee_custody_management.group_custody_approver"):
            raise UserError(_("Only custody approvers can approve custody requests."))
        for request in self:
            if request.state != "submitted":
                continue
            request._validate_approval_policy()
            request.write({
                "state": "approved",
                "approver_id": self.env.user.id,
            })

    def action_issue(self):
        """Issue approved custody by creating and posting an outbound payment."""
        for request in self:
            if request.state != "approved":
                continue
            request.employee_id._ensure_custody_partner()
            if not request.company_id.custody_receivable_account_id:
                raise UserError(_("Configure the Custody Receivable account in Accounting Settings before issuing."))
            payment_method_line = request.journal_id._get_available_payment_method_lines("outbound")[:1]
            if not payment_method_line:
                raise UserError(_(
                    "The funding journal %(journal)s has no outbound payment method. Add a manual outbound method "
                    "to the journal first.",
                    journal=request.journal_id.display_name,
                ))
            if not payment_method_line.payment_account_id and request.journal_id.default_account_id:
                payment_method_line.payment_account_id = request.journal_id.default_account_id
            payment = self.env["account.payment"].create({
                "date": request.request_date,
                "amount": request.amount,
                "payment_type": "outbound",
                "partner_type": "supplier",
                "memo": request.name,
                "journal_id": request.journal_id.id,
                "company_id": request.company_id.id,
                "currency_id": request.currency_id.id,
                "partner_id": request.partner_id.id,
                "payment_method_line_id": payment_method_line.id,
                "destination_account_id": request.custody_account_id.id,
            })
            payment.action_post()
            request.write({
                "payment_id": payment.id,
                "state": "issued",
            })

    def action_cancel(self):
        """Cancel a request when no custody reconciliation already exists."""
        for request in self:
            if request.state == "settled":
                raise UserError(_("Settled custody requests cannot be cancelled. Reverse their settlement instead."))
            if request.payment_id and request.payment_id.move_id:
                custody_lines = request.payment_id.move_id.line_ids.filtered(
                    lambda line: line.account_id == request.custody_account_id
                )
                if any(custody_lines.mapped("matched_debit_ids")) or any(custody_lines.mapped("matched_credit_ids")):
                    raise UserError(_(
                        "This custody has reconciled ledger entries. Unreconcile or settle it before cancelling."
                    ))
                request.payment_id.action_cancel()
            request.state = "cancelled"

    def action_reset_to_draft(self):
        """Reset cancelled requests to draft for correction."""
        for request in self:
            if request.state == "cancelled":
                request.state = "draft"

    def _validate_ready_for_approval(self):
        """Validate that all workflow prerequisites are configured."""
        self.ensure_one()
        if not self.employee_id.is_custody_holder:
            raise UserError(_("Select an employee marked as a custody holder."))
        if not self.partner_id:
            self.employee_id._ensure_custody_partner()
        if not self.custody_account_id:
            raise UserError(_("Configure the Custody Receivable account in Accounting Settings."))
        if self.employee_id.custody_category_ids and self.category_id not in self.employee_id.custody_category_ids:
            raise UserError(_(
                "%(employee)s is not allowed to receive custody for category %(category)s.",
                employee=self.employee_id.name,
                category=self.category_id.display_name,
            ))

    def _validate_approval_policy(self):
        """Validate limits, first-time policy, and open custody blocking."""
        self.ensure_one()
        self._validate_ready_for_approval()
        company = self.company_id
        amount_company = self.currency_id._convert(self.amount, company.currency_id, company, self.request_date)
        current_balance = self.employee_id._get_custody_balance(company=company, date=self.request_date)
        if self.category_id.disbursement_limit and current_balance + amount_company > self.category_id.disbursement_limit:
            raise UserError(_(
                "Issuing this custody would exceed the %(category)s limit. Current balance: %(balance).2f; "
                "requested amount: %(amount).2f.",
                category=self.category_id.display_name,
                balance=current_balance,
                amount=amount_company,
            ))
        if company.custody_require_settlement_before_new:
            open_request = self.search([
                ("id", "!=", self.id),
                ("employee_id", "=", self.employee_id.id),
                ("company_id", "=", company.id),
                ("state", "in", ("issued", "partially_settled")),
            ], limit=1)
            if open_request:
                raise UserError(_(
                    "%(employee)s already has open custody %(request)s. Settle it before issuing a new custody.",
                    employee=self.employee_id.name,
                    request=open_request.name,
                ))
        previous_issued = self.search_count([
            ("id", "!=", self.id),
            ("employee_id", "=", self.employee_id.id),
            ("company_id", "=", company.id),
            ("state", "not in", ("draft", "submitted", "cancelled")),
        ])
        if not previous_issued and amount_company > company.custody_first_time_limit:
            raise UserError(_(
                "The first custody for %(employee)s cannot exceed %(limit).2f. Reduce the amount or change the "
                "company custody settings.",
                employee=self.employee_id.name,
                limit=company.custody_first_time_limit,
            ))

    def _refresh_state_from_settlement(self):
        """Refresh issued request state according to linked settled amounts."""
        for request in self:
            if request.state not in ("issued", "partially_settled", "settled"):
                continue
            request.invalidate_recordset(["settled_amount", "remaining_amount"])
            request._compute_settlement_amounts()
            if request.currency_id.is_zero(request.remaining_amount):
                request.state = "settled"
            elif request.settled_amount:
                request.state = "partially_settled"
            else:
                request.state = "issued"

    def action_view_payment(self):
        """Open the custody issuance payment."""
        self.ensure_one()
        return self.payment_id._get_records_action(name=_("Custody Payment"))

    def action_view_move(self):
        """Open the custody issuance journal entry."""
        self.ensure_one()
        return self.move_id._get_records_action(name=_("Custody Journal Entry"))

    def action_view_settlements(self):
        """Open settlements linked to this request."""
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "employee_custody_management.action_custody_settlement"
        )
        action["domain"] = [("request_id", "=", self.id)]
        action["context"] = {
            "default_request_id": self.id,
            "default_employee_id": self.employee_id.id,
        }
        return action

    def action_view_vendor_bills(self):
        """Open vendor bills paid from this custody request."""
        self.ensure_one()
        return self.linked_vendor_bill_ids._get_records_action(name=_("Linked Vendor Bills"))

    def action_view_custody_payments(self):
        """Open vendor payments made from this custody request."""
        self.ensure_one()
        return self.custody_payment_ids.filtered("is_custody_payment")._get_records_action(
            name=_("Custody Vendor Payments")
        )

    def _get_custody_statement_lines(self, date_from=False, date_to=False):
        """Delegate statement lines to the employee linked to this request."""
        self.ensure_one()
        return self.employee_id._get_custody_statement_lines(date_from=date_from, date_to=date_to)

    @api.model
    def _cron_send_overdue_notifications(self):
        """Send overdue custody reminder emails once per day."""
        template = self.env.ref(
            "employee_custody_management.email_template_custody_overdue",
            raise_if_not_found=False,
        )
        if not template:
            _logger.info("Custody overdue email template is not installed.")
            return
        overdue_requests = self.search([
            ("state", "in", ("issued", "partially_settled")),
            ("expected_settlement_date", "<", fields.Date.context_today(self)),
        ])
        for request in overdue_requests:
            template.send_mail(request.id, force_send=False)

    @api.model
    def create_demo_records(self):
        """Create robust demo data for databases with different charts of accounts."""
        company = self.env.company
        Account = self.env["account.account"]
        Journal = self.env["account.journal"]
        if not company.custody_receivable_account_id:
            account = Account.search([
                ("account_type", "=", "asset_receivable"),
                ("company_ids", "in", company.id),
                ("name", "ilike", "Employee Custody"),
            ], limit=1)
            if not account:
                account = Account.create({
                    "name": "Employee Custody Receivable",
                    "code": "136900",
                    "account_type": "asset_receivable",
                    "reconcile": True,
                    "company_ids": [Command.set(company.ids)],
                })
            company.custody_receivable_account_id = account
        custody_journal = Journal.search([
            ("company_id", "=", company.id),
            ("is_custody_journal", "=", True),
            ("type", "in", ("cash", "bank")),
        ], limit=1)
        if not custody_journal:
            custody_journal = Journal.create({
                "name": "Employee Custody Journal",
                "code": "CSTDY",
                "type": "cash",
                "company_id": company.id,
            })
            custody_journal.is_custody_journal = True
        company.custody_default_journal_id = custody_journal
        funding_journal = Journal.search([
            ("company_id", "=", company.id),
            ("type", "in", ("bank", "cash")),
        ], limit=1) or custody_journal
        categories = self.env["custody.category"]
        for code, name in (("OFF", "Office Supplies"), ("TRV", "Travel"), ("OPS", "Operations")):
            categories |= self.env["custody.category"].search([
                ("company_id", "=", company.id),
                ("code", "=", code),
            ], limit=1) or self.env["custody.category"].create({
                "name": name,
                "code": code,
                "company_id": company.id,
                "disbursement_limit": 20000.0,
            })
        employee = self.env["hr.employee"].search([
            ("name", "=", "Ahmed Mostafa"),
            ("company_id", "=", company.id),
        ], limit=1) or self.env["hr.employee"].create({
            "name": "Ahmed Mostafa",
            "company_id": company.id,
            "is_custody_holder": True,
        })
        employee.write({
            "is_custody_holder": True,
            "custody_category_ids": [Command.set(categories.ids)],
        })
        sara = self.env["hr.employee"].search([
            ("name", "=", "Sara Ali"),
            ("company_id", "=", company.id),
        ], limit=1) or self.env["hr.employee"].create({
            "name": "Sara Ali",
            "company_id": company.id,
            "is_custody_holder": True,
        })
        sara.write({
            "is_custody_holder": True,
            "custody_category_ids": [Command.set(categories.ids)],
        })
        if self.search([("employee_id", "=", employee.id), ("amount", "=", 5000.0)], limit=1):
            return
        request = self.create({
            "employee_id": employee.id,
            "category_id": categories[:1].id,
            "request_date": fields.Date.context_today(self),
            "expected_settlement_date": fields.Date.add(fields.Date.context_today(self), days=14),
            "amount": 5000.0,
            "currency_id": company.currency_id.id,
            "journal_id": funding_journal.id,
            "custody_account_id": company.custody_receivable_account_id.id,
            "description": "Demo custody for office supplies.",
            "company_id": company.id,
        })
        request.action_submit()
        request.action_approve()
        request.action_issue()
        vendor = self.env["res.partner"].create({"name": "Demo Office Supplies Vendor"})
        expense_account = self.env["account.account"].search([
            ("account_type", "in", ("expense", "expense_direct_cost")),
            ("company_ids", "in", company.id),
        ], limit=1)
        bill = self.env["account.move"].create({
            "move_type": "in_invoice",
            "partner_id": vendor.id,
            "invoice_date": fields.Date.context_today(self),
            "company_id": company.id,
            "invoice_line_ids": [Command.create({
                "name": "Demo office supplies paid from custody",
                "quantity": 1.0,
                "price_unit": 1500.0,
                "account_id": expense_account.id,
            })],
        })
        bill.action_post()
        payment_method_line = custody_journal._get_available_payment_method_lines("outbound")[:1]
        if payment_method_line and not payment_method_line.payment_account_id and custody_journal.default_account_id:
            payment_method_line.payment_account_id = custody_journal.default_account_id
        payable_line = bill.line_ids.filtered(lambda line: line.account_id.account_type == "liability_payable")[:1]
        payment = self.env["account.payment"].create({
            "date": fields.Date.context_today(self),
            "amount": 1500.0,
            "payment_type": "outbound",
            "partner_type": "supplier",
            "memo": bill.name,
            "journal_id": custody_journal.id,
            "company_id": company.id,
            "currency_id": company.currency_id.id,
            "partner_id": vendor.id,
            "payment_method_line_id": payment_method_line.id,
            "destination_account_id": payable_line.account_id.id,
            "custody_employee_id": employee.id,
            "custody_request_id": request.id,
        })
        payment.action_post()
        (payment.move_id.line_ids + payable_line).filtered(lambda line: line.account_id == payable_line.account_id).reconcile()
        settlement = self.env["custody.settlement"].create({
            "request_id": request.id,
            "settlement_date": fields.Date.context_today(self),
            "line_ids": [
                Command.create({
                    "type": "expense",
                    "description": "Demo unbilled petty cash expense",
                    "account_id": expense_account.id,
                    "amount": 2000.0,
                }),
                Command.create({
                    "type": "return_cash",
                    "description": "Demo returned cash",
                    "journal_id": funding_journal.id,
                    "amount": 1500.0,
                }),
            ],
        })
        settlement.action_post()
