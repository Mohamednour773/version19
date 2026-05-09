import json
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.osv import expression
from odoo.tools.safe_eval import safe_eval


class ApprovalReason(models.Model):
    _name = "universal.approval.reason"
    _description = "Approval Reason Library"
    _order = "reason_type, name"

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    reason_type = fields.Selection(
        [
            ("approve", "Approval"),
            ("reject", "Rejection"),
            ("modification", "Modification Request"),
            ("withdraw", "Withdraw"),
            ("override", "Override"),
        ],
        required=True,
    )
    company_id = fields.Many2one("res.company")
    model_id = fields.Many2one("ir.model", ondelete="cascade")


class ApprovalPrecheck(models.Model):
    _name = "universal.approval.precheck"
    _description = "Pre-Approval Validation"
    _order = "sequence, id"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    workflow_id = fields.Many2one("universal.approval.workflow", required=True, ondelete="cascade")
    check_type = fields.Selection(
        [
            ("required_field", "Required Field"),
            ("required_attachment", "Required Attachments"),
            ("domain", "Domain Must Match"),
        ],
        default="required_field",
        required=True,
    )
    field_id = fields.Many2one("ir.model.fields", ondelete="cascade")
    min_attachment_count = fields.Integer(default=1)
    condition_domain = fields.Text(default="[]")
    blocking = fields.Boolean(default=True)
    message = fields.Char(required=True, default="Pre-approval validation failed.")

    def _evaluate(self, record):
        self.ensure_one()
        if not self.active:
            return True
        if self.check_type == "required_field":
            if not self.field_id:
                return True
            return bool(record[self.field_id.name])
        if self.check_type == "required_attachment":
            count = self.env["ir.attachment"].sudo().search_count(
                [
                    ("res_model", "=", record._name),
                    ("res_id", "=", record.id),
                ]
            )
            return count >= self.min_attachment_count
        if self.check_type == "domain":
            domain = safe_eval(self.condition_domain or "[]", {"context": dict(self.env.context)})
            return bool(
                record.sudo().search_count(
                    expression.AND([[("id", "=", record.id)], domain or []])
                )
            )
        return True


class ApprovalQuota(models.Model):
    _name = "universal.approval.quota"
    _description = "Approval Quota and Period Limit"
    _order = "sequence, id"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    user_id = fields.Many2one("res.users", required=True)
    model_ids = fields.Many2many("ir.model")
    company_id = fields.Many2one("res.company")
    period = fields.Selection(
        [("monthly", "Monthly"), ("quarterly", "Quarterly"), ("yearly", "Yearly")],
        default="monthly",
        required=True,
    )
    amount_limit = fields.Monetary(currency_field="currency_id", required=True)
    warning_threshold = fields.Float(default=80.0)
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    escalation_user_id = fields.Many2one("res.users")

    def _period_start(self, date_value):
        if self.period == "yearly":
            return date_value.replace(month=1, day=1)
        if self.period == "quarterly":
            quarter_month = ((date_value.month - 1) // 3) * 3 + 1
            return date_value.replace(month=quarter_month, day=1)
        return date_value.replace(day=1)

    def _consumed_amount(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        start = self._period_start(today)
        domain = [
            ("approver_id", "=", self.user_id.id),
            ("state", "=", "approved"),
            ("decided_date", ">=", fields.Datetime.to_datetime(start)),
        ]
        if self.model_ids:
            domain.append(("request_id.model_id", "in", self.model_ids.ids))
        if self.company_id:
            domain.append(("request_id.company_id", "=", self.company_id.id))
        total = 0.0
        for line in self.env["universal.approval.request.line"].sudo().search(domain):
            amount = line.request_id.amount_total or 0.0
            currency = line.request_id.currency_id
            if currency and currency != self.currency_id:
                amount = currency._convert(
                    amount,
                    self.currency_id,
                    line.request_id.company_id or self.env.company,
                    today,
                )
            total += amount
        return total

    def _check_available(self, request):
        self.ensure_one()
        amount = request.amount_total or 0.0
        if request.currency_id and request.currency_id != self.currency_id:
            amount = request.currency_id._convert(
                amount,
                self.currency_id,
                request.company_id or self.env.company,
                fields.Date.context_today(self),
            )
        return self._consumed_amount() + amount <= self.amount_limit


class ApprovalNotification(models.Model):
    _name = "universal.approval.notification"
    _description = "Approval Notification Queue"
    _order = "create_date desc, id desc"

    name = fields.Char(required=True)
    channel = fields.Selection(
        [
            ("internal", "Odoo"),
            ("email", "Email"),
            ("whatsapp", "WhatsApp"),
            ("telegram", "Telegram"),
            ("sms", "SMS"),
            ("push", "Push"),
            ("slack", "Slack"),
            ("teams", "Teams"),
        ],
        required=True,
        default="internal",
    )
    state = fields.Selection(
        [("pending", "Pending"), ("sent", "Sent"), ("failed", "Failed"), ("cancelled", "Cancelled")],
        default="pending",
        required=True,
    )
    target_user_id = fields.Many2one("res.users")
    request_id = fields.Many2one("universal.approval.request", ondelete="cascade")
    line_id = fields.Many2one("universal.approval.request.line", ondelete="cascade")
    subject = fields.Char(required=True)
    body = fields.Html()
    payload_json = fields.Text(default="{}")
    error_message = fields.Text()
    sent_date = fields.Datetime()

    @api.model
    def _queue(self, channel, user, subject, body, request=False, line=False, payload=None):
        return self.create(
            {
                "name": subject,
                "channel": channel,
                "target_user_id": user.id if user else False,
                "request_id": request.id if request else False,
                "line_id": line.id if line else False,
                "subject": subject,
                "body": body,
                "payload_json": json.dumps(payload or {}, default=str),
            }
        )

    def _send_one(self):
        self.ensure_one()
        try:
            if self.channel == "internal" and self.request_id:
                self.request_id.message_post(
                    body=self.body or self.subject,
                    partner_ids=self.target_user_id.partner_id.ids if self.target_user_id else [],
                    subtype_xmlid="mail.mt_comment",
                )
            elif self.channel == "email":
                if not self.target_user_id.email:
                    raise UserError(_("The target user has no email address."))
                self.env["mail.mail"].sudo().create(
                    {
                        "subject": self.subject,
                        "body_html": self.body or self.subject,
                        "email_to": self.target_user_id.email,
                    }
                ).send()
            else:
                # External connectors pick up queued payloads and mark them as sent.
                return
            self.state = "sent"
            self.sent_date = fields.Datetime.now()
        except Exception as exc:  # pragma: no cover - depends on live mail setup
            self.state = "failed"
            self.error_message = str(exc)

    @api.model
    def _cron_send_pending(self, limit=100):
        notifications = self.search(
            [("state", "=", "pending"), ("channel", "in", ["internal", "email"])],
            limit=limit,
        )
        for notification in notifications:
            notification._send_one()


class ApprovalAnomalyRule(models.Model):
    _name = "universal.approval.anomaly.rule"
    _description = "Approval Anomaly Rule"
    _order = "sequence, id"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    model_id = fields.Many2one("ir.model", required=True, ondelete="cascade")
    amount_field_id = fields.Many2one("ir.model.fields", ondelete="cascade")
    partner_field_id = fields.Many2one("ir.model.fields", ondelete="cascade")
    lookback_days = fields.Integer(default=90)
    percent_threshold = fields.Float(default=300.0)
    min_sample_size = fields.Integer(default=3)
    warning_message = fields.Char(
        default="This document amount is unusually high compared with similar historical requests."
    )

    def _evaluate(self, request, record):
        self.ensure_one()
        if not self.active or self.model_id.model != record._name or not self.amount_field_id:
            return False
        amount = record[self.amount_field_id.name] or 0.0
        if not amount:
            return False
        since = fields.Datetime.now() - timedelta(days=self.lookback_days)
        domain = [
            ("model_id.model", "=", record._name),
            ("state", "in", ["approved", "confirmed"]),
            ("submitted_date", ">=", since),
            ("id", "!=", request.id),
        ]
        if self.partner_field_id and self.partner_field_id.name in record._fields:
            partner = record[self.partner_field_id.name]
            if partner:
                domain.append(("partner_key", "=", "%s,%s" % (partner._name, partner.id)))
        samples = self.env["universal.approval.request"].sudo().search(domain)
        if len(samples) < self.min_sample_size:
            return False
        avg = sum(samples.mapped("amount_total")) / len(samples)
        if avg and amount >= avg * (self.percent_threshold / 100.0):
            return self.warning_message
        return False


class ApprovalTemplate(models.Model):
    _name = "universal.approval.template"
    _description = "Approval Workflow Template"
    _order = "industry, name"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    industry = fields.Selection(
        [
            ("generic", "Generic"),
            ("restaurant", "Restaurants"),
            ("retail", "Retail"),
            ("manufacturing", "Manufacturing"),
            ("services", "Services"),
            ("trading", "Trading"),
        ],
        default="generic",
        required=True,
    )
    model_id = fields.Many2one("ir.model", ondelete="cascade")
    description = fields.Text()
    template_json = fields.Text(default="{}")


