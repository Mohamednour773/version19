from markupsafe import Markup

from odoo import _, http
from odoo.exceptions import UserError
from odoo.http import request


class ApprovalEngineController(http.Controller):
    @http.route(
        "/approval/action/<string:token>/<string:decision>",
        type="http",
        auth="public",
        csrf=False,
        methods=["GET", "POST"],
    )
    def approval_magic_action(self, token, decision, **kwargs):
        line = request.env["universal.approval.request.line"].sudo().search(
            [("decision_token", "=", token)],
            limit=1,
        )
        if not line:
            return request.make_response(self._page(_("Invalid approval link.")))
        try:
            comment = kwargs.get("comment")
            line.action_decide_from_token(decision, comment=comment)
            message = _("Decision saved successfully.")
        except Exception as exc:
            message = str(exc)
        return request.make_response(self._page(message))

    @http.route(
        "/approval/webhook/decision",
        type="json",
        auth="public",
        csrf=False,
        methods=["POST"],
    )
    def approval_webhook_decision(self, **payload):
        token = payload.get("token")
        decision = payload.get("decision")
        comment = payload.get("comment")
        line = request.env["universal.approval.request.line"].sudo().search(
            [("decision_token", "=", token)],
            limit=1,
        )
        if not line:
            return {"ok": False, "error": "invalid_token"}
        try:
            line.action_decide_from_token(decision, comment=comment)
        except UserError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "request": line.request_id.name}

    @http.route("/approval/mobile/inbox", type="http", auth="user", csrf=False)
    def approval_mobile_inbox(self, **kwargs):
        lines = request.env["universal.approval.request.line"].search(
            [
                ("approver_id", "=", request.env.user.id),
                ("state", "=", "pending"),
            ],
            limit=50,
        )
        rows = []
        for line in lines:
            rows.append(
                "<li><b>%s</b><br/>%s<br/><a href='%s'>Approve</a> | <a href='%s'>Reject</a></li>"
                % (
                    line.request_id.name,
                    line.request_id.res_name,
                    line._magic_url("approve"),
                    line._magic_url("reject"),
                )
            )
        return request.make_response(
            self._page(
                Markup("<h1>Pending Approvals</h1><ul>%s</ul>" % "".join(rows))
            )
        )

    def _page(self, message):
        return Markup(
            """
            <!doctype html>
            <html>
                <head>
                    <meta name="viewport" content="width=device-width, initial-scale=1"/>
                    <title>Approval</title>
                    <style>
                        body { font-family: Arial, sans-serif; margin: 32px; color: #222; }
                        main { max-width: 620px; margin: auto; }
                        a { color: #0b5cad; }
                        li { margin: 0 0 18px; }
                    </style>
                </head>
                <body><main>%s</main></body>
            </html>
            """
            % message
        )


