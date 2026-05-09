from odoo import _, fields, models
from odoo.exceptions import UserError


class ApprovalDecisionWizard(models.TransientModel):
    _name = "universal.approval.decision.wizard"
    _description = "Approval Decision Wizard"

    request_id = fields.Many2one("universal.approval.request", required=True)
    line_id = fields.Many2one("universal.approval.request.line")
    decision = fields.Selection(
        [
            ("approve", "Approve"),
            ("reject", "Reject"),
            ("modification", "Request Modification"),
            ("withdraw", "Withdraw"),
            ("forward", "Forward"),
        ],
        required=True,
    )
    reason_id = fields.Many2one("universal.approval.reason")
    comment = fields.Text()
    forward_user_id = fields.Many2one("res.users")
    attachment_ids = fields.Many2many("ir.attachment", string="Attachments")

    def action_apply(self):
        self.ensure_one()
        if self.decision == "approve":
            self.request_id.action_approve_current_user(comment=self.comment, reason=self.reason_id)
        elif self.decision == "reject":
            self.request_id.action_reject_current_user(comment=self.comment, reason=self.reason_id)
        elif self.decision == "modification":
            self.request_id.action_request_modification_current_user(comment=self.comment, reason=self.reason_id)
        elif self.decision == "withdraw":
            self.request_id.action_withdraw(comment=self.comment, reason=self.reason_id)
        elif self.decision == "forward":
            self.request_id.action_forward_current_user(
                self.forward_user_id,
                comment=self.comment,
                reason=self.reason_id,
            )
        else:
            raise UserError(_("Unsupported decision."))
        if self.attachment_ids:
            comment = self.env["universal.approval.comment"].search(
                [("request_id", "=", self.request_id.id)],
                order="id desc",
                limit=1,
            )
            if comment:
                comment.attachment_ids = [(6, 0, self.attachment_ids.ids)]
        return {"type": "ir.actions.act_window_close"}


