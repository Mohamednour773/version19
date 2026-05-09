import json
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class ApprovalRequest(models.Model):
    _name = "universal.approval.request"
    _description = "Approval Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "priority desc, due_date, submitted_date desc, id desc"

    name = fields.Char(default="/", copy=False, readonly=True)
    workflow_id = fields.Many2one("universal.approval.workflow", required=True, tracking=True)
    model_id = fields.Many2one(related="workflow_id.model_id", store=True)
    res_model = fields.Char(required=True, index=True)
    res_id = fields.Integer(required=True, index=True)
    res_name = fields.Char(readonly=True)
    owner_id = fields.Many2one("res.users", required=True, tracking=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)
    amount_total = fields.Monetary(currency_field="currency_id", tracking=True)
    currency_id = fields.Many2one("res.currency", default=lambda self: self.env.company.currency_id)
    partner_key = fields.Char(index=True)
    priority = fields.Selection(
        [("low", "Low"), ("normal", "Normal"), ("urgent", "Urgent")],
        default="normal",
        required=True,
        tracking=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("pending", "Pending Approval"),
            ("approved", "Approved"),
            ("confirmed", "Confirmed"),
            ("rejected", "Rejected"),
            ("returned", "Returned for Modification"),
            ("cancelled", "Cancelled"),
            ("withdrawn", "Withdrawn"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    current_stage_id = fields.Many2one("universal.approval.workflow.stage", readonly=True)
    current_sequence = fields.Integer(readonly=True)
    submitted_date = fields.Datetime(readonly=True)
    approved_date = fields.Datetime(readonly=True)
    rejected_date = fields.Datetime(readonly=True)
    due_date = fields.Datetime(readonly=True)
    line_ids = fields.One2many("universal.approval.request.line", "request_id", string="Approval Lines")
    comment_ids = fields.One2many("universal.approval.comment", "request_id", string="Approval Discussion")
    audit_log_ids = fields.One2many("universal.approval.audit.log", "request_id", string="Audit Trail")
    snapshot_json = fields.Text(readonly=True)
    latest_snapshot_json = fields.Text(readonly=True)
    document_changed = fields.Boolean(compute="_compute_document_changed")
    pending_line_count = fields.Integer(compute="_compute_request_stats")
    can_current_user_approve = fields.Boolean(compute="_compute_request_stats")
    smart_suggestion = fields.Char(compute="_compute_smart_suggestion")
    anomaly_warning = fields.Text(readonly=True)
    document_url = fields.Char(compute="_compute_document_url")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code("universal.approval.request") or "/"
        return super().create(vals_list)

    def _resolve_record(self):
        self.ensure_one()
        if not self.res_model or not self.res_id:
            return self.env[self.res_model]
        return self.env[self.res_model].browse(self.res_id).exists()

    def _compute_document_url(self):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "")
        for request in self:
            if request.res_model and request.res_id and base_url:
                request.document_url = "%s/web#id=%s&model=%s&view_type=form" % (
                    base_url,
                    request.res_id,
                    request.res_model,
                )
            else:
                request.document_url = False

    def _compute_request_stats(self):
        user = self.env.user
        for request in self:
            pending = request.line_ids.filtered(lambda line: line.state == "pending")
            request.pending_line_count = len(pending)
            request.can_current_user_approve = bool(
                pending.filtered(lambda line: line.approver_id == user)
            ) or (
                request.workflow_id.allow_override
                and user.has_group("universal_approval_engine_19.group_approval_manager")
                and bool(pending)
            )

    def _compute_document_changed(self):
        for request in self:
            request.document_changed = bool(
                request.snapshot_json
                and request._current_snapshot_json()
                and request.snapshot_json != request._current_snapshot_json()
            )

    def _compute_smart_suggestion(self):
        for request in self:
            similar = self.search(
                [
                    ("id", "!=", request.id),
                    ("res_model", "=", request.res_model),
                    ("state", "in", ["approved", "confirmed"]),
                    ("amount_total", ">=", request.amount_total * 0.9 if request.amount_total else 0),
                    ("amount_total", "<=", request.amount_total * 1.1 if request.amount_total else 0),
                ],
                limit=1,
            )
            if similar:
                request.smart_suggestion = _("Similar request %s was approved before.") % similar.name
            else:
                request.smart_suggestion = False

    @api.model
    def action_submit_records(self, records):
        created = self.browse()
        for record in records:
            workflow = self.env["universal.approval.workflow"].sudo()._get_workflow_for_record(record)
            if not workflow:
                raise UserError(_("No active approval workflow matches %s.") % record.display_name)
            existing = self.sudo().search(
                [
                    ("res_model", "=", record._name),
                    ("res_id", "=", record.id),
                    ("state", "in", ["pending", "returned"]),
                ],
                limit=1,
            )
            if existing:
                raise UserError(_("An approval request is already open for %s.") % record.display_name)
            created |= self._create_from_record(workflow, record)
        if len(created) == 1:
            return {
                "type": "ir.actions.act_window",
                "res_model": "universal.approval.request",
                "res_id": created.id,
                "view_mode": "form",
            }
        action = self.env.ref("universal_approval_engine_19.action_approval_request").read()[0]
        action["domain"] = [("id", "in", created.ids)]
        return action

    @api.model
    def _create_from_record(self, workflow, record):
        workflow._check_prechecks(record)
        metrics = workflow._get_record_metrics(record)
        values = {
            "workflow_id": workflow.id,
            "res_model": record._name,
            "res_id": record.id,
            "res_name": record.display_name,
            "owner_id": metrics["owner"].id,
            "company_id": metrics["company"].id if metrics["company"] else False,
            "amount_total": metrics["amount"],
            "currency_id": metrics["currency"].id if metrics["currency"] else False,
            "partner_key": workflow._get_partner_key(record),
            "priority": metrics["priority"],
            "state": "pending",
            "submitted_date": fields.Datetime.now(),
        }
        values["snapshot_json"] = self._snapshot_record(record, workflow)
        request = self.create(values)
        request._generate_approval_lines(record)
        if not request.line_ids:
            raise UserError(_("No approvers were resolved for workflow %s.") % workflow.name)
        workflow._write_record_state(record, workflow.pending_state_value)
        request._start_next_sequence()
        request._log_event("submitted", _("Approval request submitted."))
        request._evaluate_anomalies(record)
        return request

    @api.model
    def _snapshot_record(self, record, workflow):
        fields_to_track = workflow.tracked_field_ids.filtered(lambda field: field.name in record._fields)
        if not fields_to_track:
            fields_to_track = (
                workflow.amount_field_id
                | workflow.currency_field_id
                | workflow.owner_field_id
                | workflow.partner_field_id
                | workflow.state_field_id
            ).filtered(lambda field: field and field.name in record._fields)
        data = {}
        for field in fields_to_track:
            value = record[field.name]
            if hasattr(value, "ids"):
                data[field.name] = value.ids
            else:
                data[field.name] = value
        return json.dumps(data, sort_keys=True, default=str)

    def _current_snapshot_json(self):
        self.ensure_one()
        record = self._resolve_record()
        if not record:
            return False
        return self._snapshot_record(record, self.workflow_id)

    def _generate_approval_lines(self, record):
        self.ensure_one()
        metrics = self.workflow_id._get_record_metrics(record)
        line_values = []
        for stage in self.workflow_id.stage_ids.sorted("sequence"):
            if not stage._applies_to(record):
                continue
            approvers = stage._resolve_approvers(record, request=self)
            if not approvers:
                continue
            if stage.routing_type == "hierarchy" or stage.approver_mode == "hierarchy":
                sequence = stage.sequence
                for approver in approvers:
                    line_values.append(self._line_values(stage, approver, sequence, metrics, state="future"))
                    sequence += 1
            else:
                for approver in approvers:
                    line_values.append(self._line_values(stage, approver, stage.sequence, metrics, state="future"))
        if line_values:
            self.env["universal.approval.request.line"].sudo().create(line_values)

    def _line_values(self, stage, approver, sequence, metrics, state="future"):
        delegation = self.env["universal.approval.delegation"].sudo()._get_delegate(
            approver,
            self.env[self.res_model].browse(self.res_id),
            amount=metrics["amount"],
            currency=metrics["currency"],
            company=metrics["company"],
        )
        effective_approver = delegation.delegate_id if delegation else approver
        return {
            "request_id": self.id,
            "stage_id": stage.id,
            "sequence": sequence,
            "original_approver_id": approver.id,
            "approver_id": effective_approver.id,
            "delegation_id": delegation.id if delegation else False,
            "state": state,
        }

    def _start_next_sequence(self):
        for request in self:
            future_lines = request.line_ids.filtered(lambda line: line.state == "future")
            if not future_lines:
                request._finish_approved()
                continue
            sequence = min(future_lines.mapped("sequence"))
            lines = future_lines.filtered(lambda line: line.sequence == sequence)
            now = fields.Datetime.now()
            for line in lines:
                hours = line.stage_id._sla_hours_for_priority(request.priority)
                line.write(
                    {
                        "state": "pending",
                        "pending_date": now,
                        "due_date": now + timedelta(hours=hours or 24.0),
                    }
                )
                line._notify_new_approval()
            request.write(
                {
                    "current_sequence": sequence,
                    "current_stage_id": lines[:1].stage_id.id,
                    "due_date": min(lines.mapped("due_date")) if lines.mapped("due_date") else False,
                }
            )
            request._log_event(
                "stage_started",
                _("Stage %s started.") % (lines[:1].stage_id.name if lines else ""),
            )

    def _get_actionable_line(self):
        self.ensure_one()
        line = self.line_ids.filtered(
            lambda approval_line: approval_line.state == "pending"
            and approval_line.approver_id == self.env.user
        )[:1]
        if line:
            return line
        if self.workflow_id.allow_override and self.env.user.has_group(
            "universal_approval_engine_19.group_approval_manager"
        ):
            return self.line_ids.filtered(lambda approval_line: approval_line.state == "pending")[:1]
        raise AccessError(_("You are not an active approver for this request."))

    def action_open_approve_wizard(self):
        self.ensure_one()
        return self._open_decision_wizard("approve")

    def action_open_reject_wizard(self):
        self.ensure_one()
        return self._open_decision_wizard("reject")

    def action_open_modification_wizard(self):
        self.ensure_one()
        return self._open_decision_wizard("modification")

    def action_open_forward_wizard(self):
        self.ensure_one()
        return self._open_decision_wizard("forward")

    def action_open_withdraw_wizard(self):
        self.ensure_one()
        return self._open_decision_wizard("withdraw")

    def _open_decision_wizard(self, decision):
        line = self._get_actionable_line() if decision in ("approve", "reject", "modification", "forward") else False
        return {
            "type": "ir.actions.act_window",
            "name": _("Approval Decision"),
            "res_model": "universal.approval.decision.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_request_id": self.id,
                "default_line_id": line.id if line else False,
                "default_decision": decision,
            },
        }

    def action_approve_current_user(self, comment=False, reason=False):
        for request in self:
            line = request._get_actionable_line()
            request._approve_line(line, comment=comment, reason=reason)
        return True

    def _approve_line(self, line, comment=False, reason=False):
        self.ensure_one()
        if self.state != "pending":
            raise UserError(_("Only pending requests can be approved."))
        self._check_stage_mandatory_fields(line.stage_id)
        if line.stage_id.require_comment_on_approval and not comment:
            raise UserError(_("An approval comment is required for this stage."))
        if self.workflow_id.reapproval_policy != "none" and self.document_changed:
            self.latest_snapshot_json = self._current_snapshot_json()
            raise UserError(
                _("The document changed after submission. Please re-submit it for approval.")
            )
        self._check_quota(line.approver_id)
        line.write(
            {
                "state": "approved",
                "decision": "approve",
                "decided_date": fields.Datetime.now(),
                "decision_user_id": self.env.user.id,
                "comment": comment,
                "reason_id": reason.id if reason else False,
            }
        )
        if comment or reason:
            self._add_comment(line, "approve", comment, reason)
        self._log_event("approved", _("Approved by %s.") % self.env.user.display_name, line=line)
        self._evaluate_sequence(line.sequence)

    def action_reject_current_user(self, comment=False, reason=False):
        for request in self:
            line = request._get_actionable_line()
            request._reject_line(line, comment=comment, reason=reason)
        return True

    def _reject_line(self, line, comment=False, reason=False):
        self.ensure_one()
        if self.workflow_id.require_reject_comment and not comment:
            raise UserError(_("A rejection comment is required."))
        if line.stage_id.require_comment_on_rejection and not comment:
            raise UserError(_("A rejection comment is required for this stage."))
        line.write(
            {
                "state": "rejected",
                "decision": "reject",
                "decided_date": fields.Datetime.now(),
                "decision_user_id": self.env.user.id,
                "comment": comment,
                "reason_id": reason.id if reason else False,
            }
        )
        self._add_comment(line, "reject", comment, reason)
        self._log_event("rejected", _("Rejected by %s.") % self.env.user.display_name, line=line)
        if self.workflow_id.rejection_behavior == "continue":
            self._evaluate_sequence(line.sequence)
        else:
            self._finish_rejected()

    def action_request_modification_current_user(self, comment=False, reason=False):
        for request in self:
            line = request._get_actionable_line()
            request._request_modification(line, comment=comment, reason=reason)
        return True

    def action_forward_current_user(self, forward_user, comment=False, reason=False):
        for request in self:
            line = request._get_actionable_line()
            request._forward_line(line, forward_user, comment=comment, reason=reason)
        return True

    def _forward_line(self, line, forward_user, comment=False, reason=False):
        self.ensure_one()
        if not line.stage_id.allow_forwarding:
            raise UserError(_("Forwarding is not allowed for this stage."))
        if not forward_user:
            raise UserError(_("Please select a user to forward the approval to."))
        if not comment:
            raise UserError(_("A forwarding reason is required."))
        line.write(
            {
                "state": "forwarded",
                "decision_user_id": self.env.user.id,
                "comment": comment,
                "reason_id": reason.id if reason else False,
                "decided_date": fields.Datetime.now(),
            }
        )
        new_line = self.env["universal.approval.request.line"].sudo().create(
            {
                "request_id": self.id,
                "stage_id": line.stage_id.id,
                "sequence": line.sequence,
                "approver_id": forward_user.id,
                "original_approver_id": line.original_approver_id.id or line.approver_id.id,
                "state": "pending",
                "pending_date": fields.Datetime.now(),
                "due_date": line.due_date,
            }
        )
        new_line._notify_new_approval()
        self._add_comment(line, "comment", comment, reason)
        self._log_event(
            "forwarded",
            _("Approval forwarded from %(old)s to %(new)s.")
            % {"old": line.approver_id.display_name, "new": forward_user.display_name},
            line=line,
        )

    def _request_modification(self, line, comment=False, reason=False):
        self.ensure_one()
        if not comment:
            raise UserError(_("Please describe the required modification."))
        line.write(
            {
                "state": "returned",
                "decision": "modification",
                "decided_date": fields.Datetime.now(),
                "decision_user_id": self.env.user.id,
                "comment": comment,
                "reason_id": reason.id if reason else False,
            }
        )
        pending = self.line_ids.filtered(lambda pending_line: pending_line.state == "pending")
        (pending - line).write({"state": "cancelled"})
        self.write({"state": "returned", "rejected_date": fields.Datetime.now()})
        self.workflow_id._write_record_state(self._resolve_record(), self.workflow_id.returned_state_value)
        self._add_comment(line, "modification", comment, reason)
        self._log_event(
            "modification_requested",
            _("Modification requested by %s.") % self.env.user.display_name,
            line=line,
        )
        self._notify_owner(_("Modification requested"), comment)

    def _evaluate_sequence(self, sequence):
        self.ensure_one()
        lines = self.line_ids.filtered(lambda line: line.sequence == sequence)
        active_lines = lines.filtered(lambda line: line.state not in ("future", "cancelled", "skipped", "forwarded"))
        stage = active_lines[:1].stage_id
        if not active_lines:
            self._start_next_sequence()
            return
        approved_count = len(active_lines.filtered(lambda line: line.state == "approved"))
        rejected_count = len(active_lines.filtered(lambda line: line.state == "rejected"))
        pending_count = len(active_lines.filtered(lambda line: line.state == "pending"))
        total = len(active_lines)
        required = total
        if stage.approval_policy == "any":
            required = 1
        elif stage.approval_policy == "majority":
            required = max(stage.min_approvals or 1, (total // 2) + 1)
        if approved_count >= required:
            active_lines.filtered(lambda line: line.state == "pending").write({"state": "skipped"})
            self._start_next_sequence()
            return
        if rejected_count:
            if self.workflow_id.rejection_behavior == "stop":
                self._finish_rejected()
                return
            if self.workflow_id.rejection_behavior == "continue" and not pending_count:
                self._finish_rejected()
                return
            if stage.approval_policy == "majority" and rejected_count > (total - required):
                self._finish_rejected()

    def _finish_approved(self):
        for request in self:
            if request.state in ("approved", "confirmed"):
                continue
            record = request._resolve_record()
            workflow = request.workflow_id
            values = {
                "state": "approved",
                "approved_date": fields.Datetime.now(),
                "current_stage_id": False,
                "current_sequence": 0,
            }
            request.write(values)
            workflow._write_record_state(record, workflow.approved_state_value)
            request._log_event("request_approved", _("Approval cycle completed."))
            request._notify_owner(_("Approval completed"), _("Your document was approved."))
            if workflow.auto_confirm_after_approval and workflow.confirm_method:
                method = getattr(record.sudo(), workflow.confirm_method, False)
                if method:
                    method()
                    workflow._write_record_state(record, workflow.confirmed_state_value)
                    request.write({"state": "confirmed"})
                    request._log_event("auto_confirmed", _("Document auto-confirmed after approval."))

    def _finish_rejected(self):
        for request in self:
            record = request._resolve_record()
            workflow = request.workflow_id
            pending = request.line_ids.filtered(lambda line: line.state in ("pending", "future"))
            pending.write({"state": "cancelled"})
            target_state = "rejected"
            record_state = workflow.rejected_state_value
            if workflow.post_rejection_policy == "cancel":
                target_state = "cancelled"
                record_state = workflow.cancelled_state_value
            elif workflow.post_rejection_policy in ("draft", "modifier"):
                target_state = "returned"
                record_state = workflow.returned_state_value or workflow.draft_state_value
            request.write({"state": target_state, "rejected_date": fields.Datetime.now()})
            workflow._write_record_state(record, record_state)
            request._log_event("request_rejected", _("Approval cycle rejected."))
            request._notify_owner(_("Approval rejected"), _("Your document was rejected."))

    def _check_stage_mandatory_fields(self, stage):
        self.ensure_one()
        record = self._resolve_record()
        missing = []
        for field in stage.mandatory_field_ids:
            if field.name in record._fields and not record[field.name]:
                missing.append(field.field_description or field.name)
        if missing:
            raise UserError(_("Please fill these fields before approval: %s") % ", ".join(missing))

    def _check_quota(self, approver):
        quotas = self.env["universal.approval.quota"].sudo().search(
            [("active", "=", True), ("user_id", "=", approver.id)]
        )
        for quota in quotas:
            if quota.company_id and quota.company_id != self.company_id:
                continue
            if quota.model_ids and self.model_id not in quota.model_ids:
                continue
            if not quota._check_available(self):
                raise UserError(
                    _("Approval quota exceeded for %s. Additional approval is required.")
                    % approver.display_name
                )

    def _evaluate_anomalies(self, record):
        warnings = []
        for rule in self.env["universal.approval.anomaly.rule"].sudo().search(
            [("active", "=", True), ("model_id.model", "=", record._name)]
        ):
            warning = rule._evaluate(self, record)
            if warning:
                warnings.append(warning)
        if warnings:
            self.write({"anomaly_warning": "\n".join(warnings)})
            self._log_event("anomaly_warning", "\n".join(warnings))

    def _add_comment(self, line, decision, comment=False, reason=False):
        self.env["universal.approval.comment"].create(
            {
                "request_id": self.id,
                "line_id": line.id if line else False,
                "author_id": self.env.user.id,
                "decision": decision,
                "reason_id": reason.id if reason else False,
                "body": comment or (reason.name if reason else ""),
            }
        )

    def _notify_owner(self, subject, body):
        self.env["universal.approval.notification"].sudo()._queue(
            "internal",
            self.owner_id,
            subject,
            body,
            request=self,
            payload={"event": "owner_notification"},
        )

    def _log_event(self, event, message, line=False, payload=None):
        self.env["universal.approval.audit.log"].sudo().create(
            {
                "request_id": self.id,
                "line_id": line.id if line else False,
                "event": event,
                "user_id": self.env.user.id,
                "message": message,
                "payload_json": json.dumps(payload or {}, default=str),
            }
        )

    def _raise_locked_document_error(self):
        self.ensure_one()
        raise UserError(
            _("This document is locked by approval request %s.") % self.name
        )

    def action_withdraw(self, comment=False, reason=False):
        for request in self:
            if not request.workflow_id.allow_withdraw:
                raise UserError(_("Withdraw is not allowed for this workflow."))
            if request.owner_id != self.env.user and not self.env.user.has_group(
                "universal_approval_engine_19.group_approval_manager"
            ):
                raise AccessError(_("Only the requester or approval managers can withdraw this request."))
            if request.workflow_id.require_withdraw_reason and not comment:
                raise UserError(_("A withdraw reason is required."))
            request.line_ids.filtered(lambda line: line.state in ("pending", "future")).write(
                {"state": "cancelled"}
            )
            request.write({"state": "withdrawn"})
            request.workflow_id._write_record_state(
                request._resolve_record(), request.workflow_id.draft_state_value
            )
            request._add_comment(False, "withdraw", comment, reason)
            request._log_event("withdrawn", comment or _("Approval request withdrawn."))

    def action_reset_to_draft(self):
        for request in self:
            if not self.env.user.has_group("universal_approval_engine_19.group_approval_manager"):
                raise AccessError(_("Only approval managers can reset approval requests."))
            request.line_ids.sudo().unlink()
            record = request._resolve_record()
            request.write(
                {
                    "state": "draft",
                    "current_stage_id": False,
                    "current_sequence": 0,
                    "snapshot_json": request._snapshot_record(record, request.workflow_id),
                }
            )
            request.workflow_id._write_record_state(record, request.workflow_id.draft_state_value)

    def action_resubmit(self):
        for request in self:
            if request.state not in ("draft", "returned", "rejected", "cancelled", "withdrawn"):
                raise UserError(_("Only draft, returned, rejected, cancelled, or withdrawn requests can be resubmitted."))
            record = request._resolve_record()
            request.line_ids.sudo().unlink()
            request.write(
                {
                    "state": "pending",
                    "submitted_date": fields.Datetime.now(),
                    "snapshot_json": request._snapshot_record(record, request.workflow_id),
                    "rejected_date": False,
                    "approved_date": False,
                }
            )
            request._generate_approval_lines(record)
            if not request.line_ids:
                raise UserError(_("No approvers were resolved for workflow %s.") % request.workflow_id.name)
            request.workflow_id._write_record_state(record, request.workflow_id.pending_state_value)
            request._start_next_sequence()
            request._log_event("resubmitted", _("Approval request resubmitted."))

    @api.model
    def _cron_process_sla(self):
        pending_lines = self.env["universal.approval.request.line"].sudo().search(
            [("state", "=", "pending"), ("request_id.state", "=", "pending")]
        )
        for line in pending_lines:
            line._process_sla()


class ApprovalRequestLine(models.Model):
    _name = "universal.approval.request.line"
    _description = "Approval Request Line"
    _order = "request_id, sequence, id"

    request_id = fields.Many2one("universal.approval.request", required=True, ondelete="cascade")
    line_count = fields.Integer(default=1, readonly=True)
    workflow_id = fields.Many2one(related="request_id.workflow_id", store=True)
    stage_id = fields.Many2one("universal.approval.workflow.stage", required=True)
    sequence = fields.Integer(default=10, index=True)
    state = fields.Selection(
        [
            ("future", "Not Reached"),
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("returned", "Returned"),
            ("skipped", "Skipped"),
            ("forwarded", "Forwarded"),
            ("escalated", "Escalated"),
            ("cancelled", "Cancelled"),
        ],
        default="future",
        required=True,
        index=True,
    )
    approver_id = fields.Many2one("res.users", required=True)
    original_approver_id = fields.Many2one("res.users")
    decision_user_id = fields.Many2one("res.users")
    delegation_id = fields.Many2one("universal.approval.delegation")
    escalation_rule_id = fields.Many2one("universal.approval.escalation.rule")
    escalation_level = fields.Integer(default=0)
    pending_date = fields.Datetime()
    due_date = fields.Datetime()
    decided_date = fields.Datetime()
    decision = fields.Selection(
        [
            ("approve", "Approve"),
            ("reject", "Reject"),
            ("modification", "Request Modification"),
            ("override", "Override"),
        ]
    )
    reason_id = fields.Many2one("universal.approval.reason")
    comment = fields.Text()
    decision_token = fields.Char(copy=False, index=True)
    token_expiration = fields.Datetime(copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        now = fields.Datetime.now()
        for vals in vals_list:
            vals.setdefault("decision_token", secrets.token_urlsafe(32))
            vals.setdefault("token_expiration", now + timedelta(days=30))
        return super().create(vals_list)

    def action_approve(self):
        for line in self:
            line.request_id._approve_line(line)
        return True

    def action_reject(self):
        for line in self:
            line.request_id._reject_line(line)
        return True

    def _notify_new_approval(self):
        self.ensure_one()
        subject = _("Approval required: %s") % self.request_id.res_name
        body = _(
            "<p>You have a pending approval request.</p>"
            "<p><b>Document:</b> %(doc)s<br/><b>Amount:</b> %(amount)s</p>"
            "<p><a href='%(approve)s'>Approve</a> | <a href='%(reject)s'>Reject</a></p>"
        ) % {
            "doc": self.request_id.res_name,
            "amount": self.request_id.amount_total,
            "approve": self._magic_url("approve"),
            "reject": self._magic_url("reject"),
        }
        Notification = self.env["universal.approval.notification"].sudo()
        channels = self.env["universal.approval.notification.channel"].sudo()._channels_for_user(self.approver_id)
        for channel in channels:
            Notification._queue(channel, self.approver_id, subject, body, request=self.request_id, line=self)
        self.request_id._log_event(
            "notification_queued",
            _("Approval notification queued for %s.") % self.approver_id.display_name,
            line=self,
        )

    def _magic_url(self, decision):
        self.ensure_one()
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "")
        return "%s/approval/action/%s/%s" % (base_url, self.decision_token, decision)

    def _process_sla(self):
        self.ensure_one()
        if not self.pending_date:
            return
        now = fields.Datetime.now()
        elapsed = (now - self.pending_date).total_seconds() / 3600.0
        rules = self.workflow_id.escalation_rule_ids.filtered(
            lambda rule: rule.level > self.escalation_level and elapsed >= rule.after_hours
        ).sorted("level")
        for rule in rules:
            self._apply_escalation_rule(rule)

    def _apply_escalation_rule(self, rule):
        self.ensure_one()
        if rule.action == "reminder":
            self._queue_escalation_notice(rule, self.approver_id, _("Approval reminder"))
        elif rule.action in ("notify_manager", "escalate_manager"):
            manager_user = self._manager_user()
            if manager_user:
                if rule.action == "escalate_manager" and rule.allow_escalated_approval:
                    self.write(
                        {
                            "original_approver_id": self.original_approver_id.id or self.approver_id.id,
                            "approver_id": manager_user.id,
                            "escalation_rule_id": rule.id,
                            "escalation_level": rule.level,
                        }
                    )
                self._queue_escalation_notice(rule, manager_user, _("Approval escalated"))
        elif rule.action == "notify_users":
            for user in rule.notify_user_ids:
                self._queue_escalation_notice(rule, user, _("Approval escalation notice"))
        self.escalation_level = max(self.escalation_level, rule.level)
        self.request_id._log_event(
            "escalated",
            _("Escalation level %(level)s applied on %(line)s.")
            % {"level": rule.level, "line": self.approver_id.display_name},
            line=self,
        )

    def _manager_user(self):
        self.ensure_one()
        employee = self.env["hr.employee"].sudo().search([("user_id", "=", self.approver_id.id)], limit=1)
        if employee and employee.parent_id and employee.parent_id.user_id:
            return employee.parent_id.user_id
        return False

    def _queue_escalation_notice(self, rule, user, subject):
        body = _("<p>%s</p><p>Request: %s</p>") % (rule.name, self.request_id.name)
        channel_codes = rule.channel_ids.mapped("channel") or ["internal", "email"]
        for channel in channel_codes:
            self.env["universal.approval.notification"].sudo()._queue(
                channel,
                user,
                subject,
                body,
                request=self.request_id,
                line=self,
                payload={"escalation_rule_id": rule.id},
            )

    def action_decide_from_token(self, decision, comment=False):
        self.ensure_one()
        if not self.decision_token or self.state != "pending":
            raise UserError(_("This approval link is no longer valid."))
        if self.token_expiration and self.token_expiration < fields.Datetime.now():
            raise UserError(_("This approval link has expired."))
        request = self.request_id.with_user(self.approver_id).sudo(False)
        line = self.with_user(self.approver_id).sudo(False)
        if decision == "approve":
            request._approve_line(line, comment=comment or _("Approved from secure link."))
        elif decision == "reject":
            request._reject_line(line, comment=comment or _("Rejected from secure link."))
        else:
            raise UserError(_("Unsupported decision."))


class ApprovalComment(models.Model):
    _name = "universal.approval.comment"
    _description = "Approval Comment and Discussion"
    _order = "create_date, id"

    request_id = fields.Many2one("universal.approval.request", required=True, ondelete="cascade")
    line_id = fields.Many2one("universal.approval.request.line", ondelete="set null")
    author_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user)
    decision = fields.Selection(
        [
            ("approve", "Approval"),
            ("reject", "Rejection"),
            ("modification", "Modification"),
            ("withdraw", "Withdraw"),
            ("comment", "Comment"),
        ],
        default="comment",
        required=True,
    )
    reason_id = fields.Many2one("universal.approval.reason")
    body = fields.Text(required=True)
    attachment_ids = fields.Many2many("ir.attachment", string="Attachments")


class ApprovalAuditLog(models.Model):
    _name = "universal.approval.audit.log"
    _description = "Approval Audit Log"
    _order = "create_date desc, id desc"

    request_id = fields.Many2one("universal.approval.request", required=True, ondelete="cascade")
    line_id = fields.Many2one("universal.approval.request.line", ondelete="set null")
    event = fields.Char(required=True, index=True)
    user_id = fields.Many2one("res.users", default=lambda self: self.env.user)
    message = fields.Text(required=True)
    ip_address = fields.Char()
    device = fields.Char()
    payload_json = fields.Text(default="{}")


