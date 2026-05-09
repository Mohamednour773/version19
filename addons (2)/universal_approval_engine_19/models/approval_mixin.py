from odoo import api, fields, models


class UniversalApprovalMixin(models.AbstractModel):
    _name = "universal.approval.mixin"
    _description = "Universal Approval Document Mixin"

    approval_request_count = fields.Integer(compute="_compute_approval_request_count")
    approval_state = fields.Selection(
        [
            ("none", "No Approval"),
            ("pending", "Pending Approval"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("returned", "Returned"),
        ],
        compute="_compute_approval_request_count",
    )

    def _compute_approval_request_count(self):
        Request = self.env["universal.approval.request"].sudo()
        for record in self:
            requests = Request.search(
                [("res_model", "=", record._name), ("res_id", "=", record.id)]
            )
            record.approval_request_count = len(requests)
            latest = requests[:1]
            record.approval_state = latest.state if latest else "none"

    def write(self, vals):
        tracked_requests = {}
        if vals and not self.env.context.get("skip_approval_reapproval"):
            Request = self.env["universal.approval.request"].sudo()
            for record in self:
                requests = Request.search(
                    [
                        ("res_model", "=", record._name),
                        ("res_id", "=", record.id),
                        ("state", "in", ["approved", "confirmed"]),
                    ],
                    limit=1,
                )
                if requests:
                    tracked_requests[record.id] = requests
        result = super().write(vals)
        for record in self:
            request = tracked_requests.get(record.id)
            if not request or request.workflow_id.reapproval_policy == "none":
                continue
            tracked_names = set(request.workflow_id.tracked_field_ids.mapped("name"))
            if not tracked_names:
                tracked_names = set(
                    (
                        request.workflow_id.amount_field_id
                        | request.workflow_id.currency_field_id
                        | request.workflow_id.owner_field_id
                        | request.workflow_id.partner_field_id
                    ).mapped("name")
                )
            if not tracked_names or not tracked_names.intersection(vals):
                continue
            request.sudo().write(
                {
                    "state": "returned",
                    "latest_snapshot_json": request._current_snapshot_json(),
                }
            )
            request.sudo()._log_event(
                "document_modified_after_approval",
                "Document was modified after approval and requires re-submission.",
            )
        return result

    def action_request_approval(self):
        return self.env["universal.approval.request"].action_submit_records(self)

    def action_view_approval_requests(self):
        self.ensure_one()
        action = self.env.ref("universal_approval_engine_19.action_approval_request").read()[0]
        action["domain"] = [("res_model", "=", self._name), ("res_id", "=", self.id)]
        action["context"] = {"default_res_model": self._name, "default_res_id": self.id}
        return action

    def _approval_check_before_confirm(self):
        for record in self:
            request = self.env["universal.approval.request"].sudo().search(
                [
                    ("res_model", "=", record._name),
                    ("res_id", "=", record.id),
                    ("state", "in", ["pending", "returned", "rejected"]),
                ],
                limit=1,
            )
            if request:
                request._raise_locked_document_error()
            approved = self.env["universal.approval.request"].sudo().search(
                [
                    ("res_model", "=", record._name),
                    ("res_id", "=", record.id),
                    ("state", "in", ["approved", "confirmed"]),
                ],
                limit=1,
            )
            workflow = self.env["universal.approval.workflow"].sudo()._get_workflow_for_record(record)
            if workflow and workflow.lock_confirm and not approved:
                workflow._raise_missing_approval(record)
        return True

