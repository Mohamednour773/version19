import json
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression
from odoo.tools.safe_eval import safe_eval


class ApprovalWorkflow(models.Model):
    _name = "universal.approval.workflow"
    _description = "Universal Approval Workflow"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sequence, name"

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True, tracking=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one("res.company", tracking=True)
    model_id = fields.Many2one("ir.model", required=True, ondelete="cascade", tracking=True)
    model_name = fields.Char(related="model_id.model", store=True)
    mode = fields.Selection(
        [("simple", "Simple"), ("advanced", "Advanced")],
        default="simple",
        required=True,
        tracking=True,
    )
    trigger_domain = fields.Text(
        default="[]",
        help="Domain evaluated on the target document. Empty domain means the workflow applies to all records of this model.",
    )
    routing_type = fields.Selection(
        [
            ("sequential", "Sequential"),
            ("parallel", "Parallel"),
            ("hybrid", "Hybrid"),
            ("hierarchical", "Hierarchical"),
        ],
        default="sequential",
        required=True,
    )
    rejection_behavior = fields.Selection(
        [
            ("stop", "Stop Immediately"),
            ("continue", "Continue for Information"),
            ("majority", "Majority Rule"),
        ],
        default="stop",
        required=True,
    )
    post_rejection_policy = fields.Selection(
        [
            ("cancel", "Cancel Document"),
            ("draft", "Return to Draft"),
            ("stage", "Return to Previous Stage"),
            ("modifier", "Modify and Resubmit to Rejecter"),
        ],
        default="cancel",
        required=True,
    )
    reapproval_policy = fields.Selection(
        [
            ("restart", "Restart Approval"),
            ("current_stage", "Restart from Current Stage"),
            ("none", "No Automatic Re-Approval"),
        ],
        default="restart",
        required=True,
    )
    lock_confirm = fields.Boolean(default=True)
    allow_withdraw = fields.Boolean(default=True)
    allow_override = fields.Boolean(default=True)
    require_reject_comment = fields.Boolean(default=True)
    require_withdraw_reason = fields.Boolean(default=True)

    state_field_id = fields.Many2one("ir.model.fields", string="State Field", ondelete="cascade")
    draft_state_value = fields.Char(default="draft")
    pending_state_value = fields.Char(default="pending_approval")
    approved_state_value = fields.Char(default="approved")
    rejected_state_value = fields.Char(default="rejected")
    cancelled_state_value = fields.Char(default="cancel")
    returned_state_value = fields.Char(default="draft")
    confirmed_state_value = fields.Char(default="confirmed")
    confirm_method = fields.Char(
        help="Optional method to call when the request is fully approved, for example action_confirm."
    )
    auto_confirm_after_approval = fields.Boolean()

    amount_field_id = fields.Many2one("ir.model.fields", string="Amount Field", ondelete="cascade")
    currency_field_id = fields.Many2one("ir.model.fields", string="Currency Field", ondelete="cascade")
    priority_field_id = fields.Many2one("ir.model.fields", string="Priority Field", ondelete="cascade")
    owner_field_id = fields.Many2one("ir.model.fields", string="Requester/User Field", ondelete="cascade")
    partner_field_id = fields.Many2one("ir.model.fields", string="Partner Field", ondelete="cascade")
    tracked_field_ids = fields.Many2many(
        "ir.model.fields",
        "approval_workflow_tracked_field_rel",
        "workflow_id",
        "field_id",
        string="Fields Triggering Re-Approval",
    )

    stage_ids = fields.One2many("universal.approval.workflow.stage", "workflow_id", string="Approval Stages")
    escalation_rule_ids = fields.One2many("universal.approval.escalation.rule", "workflow_id")
    precheck_ids = fields.One2many("universal.approval.precheck", "workflow_id", string="Pre-Approval Checks")
    matrix_ids = fields.One2many("universal.approval.matrix", "workflow_id", string="Approval Matrix")

    version = fields.Integer(default=1)
    effective_from = fields.Date()
    effective_to = fields.Date()
    notes = fields.Html()

    @api.constrains("effective_from", "effective_to")
    def _check_effective_dates(self):
        for workflow in self:
            if workflow.effective_from and workflow.effective_to and workflow.effective_from > workflow.effective_to:
                raise ValidationError(_("Effective From must be before Effective To."))

    def _safe_domain(self):
        self.ensure_one()
        if not self.trigger_domain:
            return []
        return safe_eval(self.trigger_domain, {"context": dict(self.env.context)}) or []

    def _record_matches(self, record):
        self.ensure_one()
        if not self.active or self.model_name != record._name:
            return False
        today = fields.Date.context_today(self)
        if self.effective_from and self.effective_from > today:
            return False
        if self.effective_to and self.effective_to < today:
            return False
        record_company = self._get_record_company(record)
        if self.company_id and record_company and self.company_id != record_company:
            return False
        domain = self._safe_domain()
        if not domain:
            return True
        return bool(
            record.sudo().search_count(
                expression.AND([[("id", "=", record.id)], domain])
            )
        )

    @api.model
    def _get_workflow_for_record(self, record):
        workflows = self.search(
            [
                ("active", "=", True),
                ("model_id.model", "=", record._name),
            ]
        )
        for workflow in workflows:
            if workflow._record_matches(record):
                return workflow
        return self.browse()

    def _get_record_company(self, record):
        self.ensure_one()
        if "company_id" in record._fields and record.company_id:
            return record.company_id
        return self.company_id or self.env.company

    def _get_record_owner(self, record):
        self.ensure_one()
        if self.owner_field_id and self.owner_field_id.name in record._fields:
            value = record[self.owner_field_id.name]
            user = self.env["universal.approval.workflow.stage"]._users_from_value(value)[:1]
            if user:
                return user
        if "user_id" in record._fields and record.user_id:
            return record.user_id
        return record.create_uid or self.env.user

    def _get_record_employee(self, record):
        self.ensure_one()
        if "employee_id" in record._fields and record.employee_id:
            return record.employee_id
        owner = self._get_record_owner(record)
        if "employee_id" in owner._fields and owner.employee_id:
            return owner.employee_id
        return self.env["hr.employee"].sudo().search([("user_id", "=", owner.id)], limit=1)

    def _get_record_metrics(self, record):
        self.ensure_one()
        company = self._get_record_company(record)
        amount = 0.0
        currency = company.currency_id
        priority = "normal"
        if self.amount_field_id and self.amount_field_id.name in record._fields:
            amount = record[self.amount_field_id.name] or 0.0
        else:
            for field_name in ("amount_total", "amount", "price_total", "balance"):
                if field_name in record._fields:
                    amount = record[field_name] or 0.0
                    break
        if self.currency_field_id and self.currency_field_id.name in record._fields:
            currency = record[self.currency_field_id.name] or currency
        elif "currency_id" in record._fields and record.currency_id:
            currency = record.currency_id
        if self.priority_field_id and self.priority_field_id.name in record._fields:
            value = record[self.priority_field_id.name]
            if value in ("urgent", "normal", "low"):
                priority = value
        return {
            "amount": amount,
            "currency": currency,
            "priority": priority,
            "company": company,
            "owner": self._get_record_owner(record),
        }

    def _get_partner_key(self, record):
        self.ensure_one()
        partner = False
        if self.partner_field_id and self.partner_field_id.name in record._fields:
            partner = record[self.partner_field_id.name]
        elif "partner_id" in record._fields:
            partner = record.partner_id
        if partner:
            return "%s,%s" % (partner._name, partner.id)
        return False

    def _check_prechecks(self, record):
        self.ensure_one()
        failures = []
        for check in self.precheck_ids:
            if not check._evaluate(record):
                failures.append(check.message)
        blocking = [message for message in failures if message]
        if blocking:
            raise UserError("\n".join(blocking))
        return True

    def _write_record_state(self, record, value):
        self.ensure_one()
        if self.state_field_id and self.state_field_id.name in record._fields and value:
            record.sudo().with_context(skip_approval_reapproval=True).write(
                {self.state_field_id.name: value}
            )

    def _raise_missing_approval(self, record):
        raise UserError(
            _("Document %(name)s must be approved before confirmation.")
            % {"name": record.display_name}
        )

    def action_create_context_action(self):
        for workflow in self:
            action = self.env["ir.actions.server"].sudo().search(
                [
                    ("model_id", "=", workflow.model_id.id),
                    ("name", "=", "Request Approval"),
                ],
                limit=1,
            )
            values = {
                "name": "Request Approval",
                "model_id": workflow.model_id.id,
                "binding_model_id": workflow.model_id.id,
                "binding_type": "action",
                "state": "code",
                "code": "env['universal.approval.request'].action_submit_records(records)",
            }
            if action:
                action.write(values)
            else:
                self.env["ir.actions.server"].sudo().create(values)
        return True

    def action_bump_version(self):
        for workflow in self:
            workflow.version += 1
        return True


class ApprovalWorkflowStage(models.Model):
    _name = "universal.approval.workflow.stage"
    _description = "Approval Workflow Stage"
    _order = "workflow_id, sequence, id"

    name = fields.Char(required=True)
    workflow_id = fields.Many2one("universal.approval.workflow", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    routing_type = fields.Selection(
        [
            ("sequential", "Sequential"),
            ("parallel", "Parallel"),
            ("hierarchy", "Hierarchy Chain"),
        ],
        default="parallel",
        required=True,
    )
    approval_policy = fields.Selection(
        [
            ("all", "All Must Approve"),
            ("any", "One Approval Is Enough"),
            ("majority", "Majority"),
        ],
        default="all",
        required=True,
    )
    min_approvals = fields.Integer(default=1)
    condition_domain = fields.Text(default="[]")
    approver_mode = fields.Selection(
        [
            ("fixed", "Fixed Users"),
            ("group", "Security Groups"),
            ("field_user", "User Field on Document"),
            ("field_employee", "Employee Field on Document"),
            ("manager", "Requester Manager"),
            ("department_manager", "Department Manager"),
            ("hierarchy", "Employee Hierarchy"),
            ("matrix", "Approval Matrix"),
            ("workload", "Smart Workload"),
        ],
        default="fixed",
        required=True,
    )
    user_ids = fields.Many2many(
        "res.users",
        "approval_stage_user_rel",
        "stage_id",
        "user_id",
        string="Approvers",
    )
    group_ids = fields.Many2many(
        "res.groups",
        "approval_stage_group_rel",
        "stage_id",
        "group_id",
        string="Approver Groups",
    )
    approver_field_id = fields.Many2one("ir.model.fields", ondelete="cascade")
    hierarchy_depth = fields.Integer(default=3)
    sla_hours = fields.Float(default=24.0)
    urgent_sla_hours = fields.Float(default=4.0)
    normal_sla_hours = fields.Float(default=24.0)
    low_sla_hours = fields.Float(default=72.0)
    require_comment_on_approval = fields.Boolean()
    require_comment_on_rejection = fields.Boolean(default=True)
    allow_forwarding = fields.Boolean(default=True)
    mandatory_field_ids = fields.Many2many(
        "ir.model.fields",
        "approval_stage_mandatory_field_rel",
        "stage_id",
        "field_id",
        string="Mandatory Fields Before Approval",
    )
    note = fields.Text()

    def _safe_domain(self):
        self.ensure_one()
        if not self.condition_domain:
            return []
        return safe_eval(self.condition_domain, {"context": dict(self.env.context)}) or []

    def _applies_to(self, record):
        self.ensure_one()
        if not self.active:
            return False
        if self.workflow_id.mode == "simple":
            return True
        domain = self._safe_domain()
        if not domain:
            return True
        return bool(
            record.sudo().search_count(
                expression.AND([[("id", "=", record.id)], domain])
            )
        )

    @api.model
    def _users_from_value(self, value):
        users = self.env["res.users"]
        if not value:
            return users
        if getattr(value, "_name", False) == "res.users":
            return value
        if getattr(value, "_name", False) == "hr.employee":
            return value.mapped("user_id")
        if hasattr(value, "mapped"):
            if "user_id" in value._fields:
                users |= value.mapped("user_id")
            if "employee_id" in value._fields:
                users |= value.mapped("employee_id.user_id")
        return users

    def _resolve_approvers(self, record, request=False):
        self.ensure_one()
        workflow = self.workflow_id
        metrics = workflow._get_record_metrics(record)
        users = self.env["res.users"]
        if self.approver_mode == "fixed":
            users = self.user_ids
        elif self.approver_mode == "group":
            users = self.group_ids.mapped("users")
        elif (
            self.approver_mode in ("field_user", "field_employee")
            and self.approver_field_id
            and self.approver_field_id.name in record._fields
        ):
            users = self._users_from_value(record[self.approver_field_id.name])
        elif self.approver_mode == "manager":
            employee = workflow._get_record_employee(record)
            users = employee.parent_id.user_id if employee and employee.parent_id else users
        elif self.approver_mode == "department_manager":
            employee = workflow._get_record_employee(record)
            users = employee.department_id.manager_id.user_id if employee and employee.department_id else users
        elif self.approver_mode == "hierarchy":
            employee = workflow._get_record_employee(record)
            depth = 0
            while employee and employee.parent_id and depth < self.hierarchy_depth:
                if employee.parent_id.user_id:
                    users |= employee.parent_id.user_id
                employee = employee.parent_id
                depth += 1
        elif self.approver_mode == "matrix":
            users = self.env["universal.approval.matrix"].sudo()._find_approvers(
                record,
                workflow=workflow,
                amount=metrics["amount"],
                currency=metrics["currency"],
                company=metrics["company"],
            )
        elif self.approver_mode == "workload":
            candidates = self.user_ids | self.group_ids.mapped("users")
            if not candidates:
                candidates = self.env["universal.approval.matrix"].sudo()._find_approvers(
                    record,
                    workflow=workflow,
                    amount=metrics["amount"],
                    currency=metrics["currency"],
                    company=metrics["company"],
                )
            users = self._pick_lowest_workload(candidates)
        return users.filtered(lambda user: user.active)

    def _pick_lowest_workload(self, users):
        if not users:
            return users
        Line = self.env["universal.approval.request.line"].sudo()
        counts = {
            user.id: Line.search_count([("approver_id", "=", user.id), ("state", "=", "pending")])
            for user in users
        }
        user_id = min(counts, key=counts.get)
        return users.browse(user_id)

    def _sla_hours_for_priority(self, priority):
        self.ensure_one()
        if priority == "urgent":
            return self.urgent_sla_hours or self.sla_hours
        if priority == "low":
            return self.low_sla_hours or self.sla_hours
        return self.normal_sla_hours or self.sla_hours


class ApprovalEscalationRule(models.Model):
    _name = "universal.approval.escalation.rule"
    _description = "Approval Escalation Rule"
    _order = "workflow_id, level, after_hours, id"

    name = fields.Char(required=True)
    workflow_id = fields.Many2one("universal.approval.workflow", required=True, ondelete="cascade")
    level = fields.Integer(default=1, required=True)
    after_hours = fields.Float(default=24.0, required=True)
    action = fields.Selection(
        [
            ("reminder", "Reminder to Approver"),
            ("notify_manager", "Notify Approver Manager"),
            ("escalate_manager", "Escalate to Approver Manager"),
            ("notify_users", "Notify Specific Users"),
        ],
        default="reminder",
        required=True,
    )
    allow_escalated_approval = fields.Boolean(default=True)
    notify_user_ids = fields.Many2many(
        "res.users",
        "approval_escalation_user_rel",
        "rule_id",
        "user_id",
        string="Notify Users",
    )
    channel_ids = fields.Many2many(
        "universal.approval.notification.channel",
        "approval_escalation_channel_rel",
        "rule_id",
        "channel_id",
        string="Channels",
    )
    note = fields.Text()


class ApprovalNotificationChannel(models.Model):
    _name = "universal.approval.notification.channel"
    _description = "Approval Notification Channel Preference"
    _order = "sequence, id"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
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
    user_id = fields.Many2one("res.users")
    active = fields.Boolean(default=True)
    quiet_hours_from = fields.Float()
    quiet_hours_to = fields.Float()

    @api.model
    def _channels_for_user(self, user):
        preferences = self.search([("active", "=", True)]).filtered(
            lambda preference: not preference.user_id or preference.user_id == user
        )
        if not preferences:
            return ["internal", "email"]
        channels = []
        for preference in preferences:
            if not preference._is_quiet_now():
                channels.append(preference.channel)
        return channels or ["internal"]

    def _is_quiet_now(self):
        self.ensure_one()
        if not self.quiet_hours_from and not self.quiet_hours_to:
            return False
        now_hour = datetime.now().hour + datetime.now().minute / 60.0
        start = self.quiet_hours_from
        end = self.quiet_hours_to
        if start <= end:
            return start <= now_hour < end
        return now_hour >= start or now_hour < end


