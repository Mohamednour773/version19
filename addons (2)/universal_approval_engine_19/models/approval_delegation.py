from odoo import api, fields, models
from odoo.osv import expression
from odoo.tools.safe_eval import safe_eval


class ApprovalDelegation(models.Model):
    _name = "universal.approval.delegation"
    _description = "Approval Delegation"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_from desc, sequence, id"

    name = fields.Char(required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True, tracking=True)
    delegation_type = fields.Selection(
        [
            ("permanent", "Permanent"),
            ("temporary", "Temporary"),
            ("partial", "Partial"),
            ("hr_leave", "HR Leave"),
        ],
        default="temporary",
        required=True,
        tracking=True,
    )
    delegator_id = fields.Many2one("res.users", required=True, tracking=True)
    delegate_id = fields.Many2one("res.users", required=True, tracking=True)
    model_ids = fields.Many2many("ir.model", string="Allowed Models")
    company_ids = fields.Many2many("res.company", string="Allowed Companies")
    date_from = fields.Datetime()
    date_to = fields.Datetime()
    max_amount = fields.Monetary(currency_field="currency_id")
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    condition_domain = fields.Text(default="[]")
    require_original_notification = fields.Boolean(default=True)
    note = fields.Text()

    def _safe_domain(self):
        self.ensure_one()
        if not self.condition_domain:
            return []
        return safe_eval(self.condition_domain, {"context": dict(self.env.context)}) or []

    def _matches(self, user, record, amount=0.0, currency=False, company=False):
        self.ensure_one()
        now = fields.Datetime.now()
        if not self.active or self.delegator_id != user:
            return False
        if self.date_from and self.date_from > now:
            return False
        if self.date_to and self.date_to < now:
            return False
        if self.model_ids and record._name not in self.model_ids.mapped("model"):
            return False
        if self.company_ids and company and company not in self.company_ids:
            return False
        if self.max_amount:
            compare_amount = amount or 0.0
            if currency and currency != self.currency_id:
                compare_amount = currency._convert(
                    amount,
                    self.currency_id,
                    company or self.env.company,
                    fields.Date.context_today(self),
                )
            if compare_amount > self.max_amount:
                return False
        domain = self._safe_domain()
        if domain:
            return bool(
                record.sudo().search_count(
                    expression.AND([[("id", "=", record.id)], domain])
                )
            )
        return True

    @api.model
    def _get_delegate(self, user, record, amount=0.0, currency=False, company=False):
        delegations = self.search(
            [
                ("active", "=", True),
                ("delegator_id", "=", user.id),
            ]
        )
        for delegation in delegations:
            if delegation._matches(user, record, amount=amount, currency=currency, company=company):
                return delegation
        return self.browse()

