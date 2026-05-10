from odoo import _, api, fields, models
from odoo.exceptions import UserError


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    is_custody_holder = fields.Boolean(
        string="Custody Holder",
        default=False,
        tracking=True,
        help="Enable this employee to receive and settle company custody/petty cash.",
    )
    custody_category_ids = fields.Many2many(
        comodel_name="custody.category",
        relation="hr_employee_custody_category_rel",
        column1="employee_id",
        column2="category_id",
        string="Allowed Custody Categories",
        check_company=True,
    )
    custody_balance = fields.Monetary(
        compute="_compute_custody_metrics",
        currency_field="currency_id",
        string="Custody Balance",
    )
    custody_balance_company_currency = fields.Monetary(
        compute="_compute_custody_metrics",
        currency_field="currency_id",
        string="Custody Balance (Company Currency)",
    )
    open_custody_request_count = fields.Integer(compute="_compute_custody_metrics")
    total_custody_issued = fields.Monetary(
        compute="_compute_custody_metrics",
        currency_field="currency_id",
    )
    total_custody_settled = fields.Monetary(
        compute="_compute_custody_metrics",
        currency_field="currency_id",
    )

    def _ensure_custody_partner(self):
        """Create or flag the employee work contact as the custody ledger partner."""
        Partner = self.env["res.partner"].sudo()
        for employee in self:
            if not employee.work_contact_id:
                employee.work_contact_id = Partner.create({
                    "name": employee.name,
                    "email": employee.work_email,
                    "phone": employee.work_phone,
                    "company_id": employee.company_id.id,
                    "is_custody_holder": True,
                })
            elif not employee.work_contact_id.is_custody_holder:
                employee.work_contact_id.sudo().write({"is_custody_holder": True})

    def _get_custody_balance(self, company=None, date=None, currency=None):
        """Return the employee's custody residual balance converted to the requested currency."""
        self.ensure_one()
        company = company or self.company_id or self.env.company
        currency = currency or company.currency_id
        date = date or fields.Date.context_today(self)
        account = company.custody_receivable_account_id
        if not account or not self.work_contact_id:
            return 0.0
        lines = self.env["account.move.line"].sudo().search([
            ("company_id", "=", company.id),
            ("parent_state", "=", "posted"),
            ("account_id", "=", account.id),
            ("partner_id", "=", self.work_contact_id.id),
            ("reconciled", "=", False),
        ])
        company_balance = sum(lines.mapped("amount_residual"))
        return company.currency_id._convert(company_balance, currency, company, date)

    @api.depends("work_contact_id", "company_id", "is_custody_holder")
    def _compute_custody_metrics(self):
        """Compute live custody balances and lifetime counters for employee dashboards."""
        Request = self.env["custody.request"].sudo()
        for employee in self:
            company = employee.company_id or self.env.company
            employee.custody_balance_company_currency = employee._get_custody_balance(company=company)
            employee.custody_balance = employee.custody_balance_company_currency
            requests = Request.search([
                ("employee_id", "=", employee.id),
                ("company_id", "=", company.id),
                ("state", "!=", "cancelled"),
            ])
            employee.open_custody_request_count = len(requests.filtered(lambda request: request.state in (
                "issued",
                "partially_settled",
            )))
            employee.total_custody_issued = sum(
                request.currency_id._convert(request.amount, company.currency_id, company, request.request_date)
                for request in requests.filtered(lambda request: request.state not in ("draft", "submitted", "cancelled"))
            )
            employee.total_custody_settled = sum(
                request.currency_id._convert(request.settled_amount, company.currency_id, company, fields.Date.today())
                for request in requests
            )

    def write(self, vals):
        """Synchronize custody holder changes with partner setup and balance safety checks."""
        disabling = vals.get("is_custody_holder") is False
        if disabling:
            for employee in self:
                balance = employee._get_custody_balance(company=employee.company_id)
                if not employee.company_id.currency_id.is_zero(balance):
                    raise UserError(_(
                        "You cannot disable custody tracking for %(employee)s while an open balance of %(amount).2f "
                        "remains. Settle the custody first.",
                        employee=employee.name,
                        amount=balance,
                    ))
        result = super().write(vals)
        if vals.get("is_custody_holder"):
            self._ensure_custody_partner()
        return result

    @api.model_create_multi
    def create(self, vals_list):
        """Ensure custody partners are created when employees are created as holders."""
        employees = super().create(vals_list)
        employees.filtered("is_custody_holder")._ensure_custody_partner()
        return employees

    def action_view_custody_requests(self):
        """Open custody requests for this employee."""
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "employee_custody_management.action_custody_request"
        )
        action["domain"] = [("employee_id", "=", self.id)]
        action["context"] = {
            "default_employee_id": self.id,
            "search_default_open": 1,
        }
        return action

    def action_view_custody_ledger(self):
        """Open posted custody receivable journal items for this employee."""
        self.ensure_one()
        account = self.company_id.custody_receivable_account_id
        if not account:
            raise UserError(_("Configure the Custody Receivable account in Accounting Settings first."))
        return {
            "name": _("Custody Ledger - %s") % self.name,
            "type": "ir.actions.act_window",
            "res_model": "account.move.line",
            "view_mode": "list,form",
            "domain": [
                ("company_id", "=", self.company_id.id),
                ("partner_id", "=", self.work_contact_id.id),
                ("account_id", "=", account.id),
                ("parent_state", "=", "posted"),
            ],
            "context": {"group_by": "date"},
        }

    def action_open_custody_settlement_wizard(self):
        """Open the quick settlement wizard for the selected employee."""
        self.ensure_one()
        return {
            "name": _("Settle Custody"),
            "type": "ir.actions.act_window",
            "res_model": "custody.settlement.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_employee_id": self.id,
                "active_model": self._name,
                "active_id": self.id,
            },
        }

    def _get_custody_statement_lines(self, date_from=False, date_to=False):
        """Return movement rows used by the QWeb custody statement."""
        self.ensure_one()
        account = self.company_id.custody_receivable_account_id
        domain = [
            ("company_id", "=", self.company_id.id),
            ("partner_id", "=", self.work_contact_id.id),
            ("account_id", "=", account.id if account else 0),
            ("parent_state", "=", "posted"),
        ]
        if date_from:
            domain.append(("date", ">=", date_from))
        if date_to:
            domain.append(("date", "<=", date_to))
        lines = self.env["account.move.line"].sudo().search(domain, order="date, id")
        running = 0.0
        result = []
        for line in lines:
            running += line.balance
            result.append({
                "date": line.date,
                "reference": line.move_id.name or line.move_id.ref,
                "description": line.name,
                "debit": line.debit,
                "credit": line.credit,
                "balance": running,
                "currency": line.company_currency_id,
            })
        return result
