from odoo import api, fields, models
from odoo.osv import expression
from odoo.tools.safe_eval import safe_eval


class ApprovalMatrix(models.Model):
    _name = "universal.approval.matrix"
    _description = "Approval Matrix Rule"
    _order = "sequence, id"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    workflow_id = fields.Many2one("universal.approval.workflow", ondelete="cascade")
    model_id = fields.Many2one("ir.model", required=True, ondelete="cascade")
    model_name = fields.Char(related="model_id.model", store=True)
    company_id = fields.Many2one("res.company")
    approver_id = fields.Many2one("res.users", required=True)
    group_id = fields.Many2one("res.groups")
    min_amount = fields.Monetary(currency_field="currency_id")
    max_amount = fields.Monetary(currency_field="currency_id")
    unlimited_amount = fields.Boolean(default=True)
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    branch_key = fields.Char(
        help="Optional branch/company/site code. Integration modules can fill it from the document."
    )
    analytic_key = fields.Char(
        help="Optional analytic/cost-center key. Kept generic to avoid forcing accounting dependencies."
    )
    condition_domain = fields.Text(
        default="[]",
        help="Odoo domain evaluated on the target document, for example [('partner_id.supplier_rank','>',0)].",
    )
    date_from = fields.Date()
    date_to = fields.Date()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("workflow_id") and not vals.get("model_id"):
                workflow = self.env["universal.approval.workflow"].browse(vals["workflow_id"])
                vals["model_id"] = workflow.model_id.id
        return super().create(vals_list)

    @api.onchange("workflow_id")
    def _onchange_workflow_id(self):
        for rule in self:
            if rule.workflow_id and not rule.model_id:
                rule.model_id = rule.workflow_id.model_id

    def _safe_domain(self):
        self.ensure_one()
        if not self.condition_domain:
            return []
        domain = safe_eval(self.condition_domain, {"context": dict(self.env.context)})
        return domain or []

    def _matches_record(self, record, amount=0.0, currency=None, company=None):
        self.ensure_one()
        if not self.active or self.model_name != record._name:
            return False
        today = fields.Date.context_today(self)
        if self.date_from and self.date_from > today:
            return False
        if self.date_to and self.date_to < today:
            return False
        if self.company_id and company and self.company_id != company:
            return False
        amount = amount or 0.0
        matrix_amount = amount
        if currency and currency != self.currency_id:
            matrix_amount = currency._convert(
                amount,
                self.currency_id,
                company or self.env.company,
                today,
            )
        if matrix_amount < (self.min_amount or 0.0):
            return False
        if not self.unlimited_amount and self.max_amount and matrix_amount > self.max_amount:
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
    def _find_approvers(self, record, workflow=False, amount=0.0, currency=False, company=False):
        rules = self.search(
            [
                ("active", "=", True),
                ("model_id.model", "=", record._name),
            ]
        )
        if workflow:
            rules = rules.filtered(lambda rule: not rule.workflow_id or rule.workflow_id == workflow)
        users = self.env["res.users"]
        for rule in rules:
            if rule._matches_record(record, amount=amount, currency=currency, company=company):
                users |= rule.approver_id
        return users

