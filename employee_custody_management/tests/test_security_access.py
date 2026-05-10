from odoo import Command
from odoo.exceptions import AccessError, UserError

from .common import CustodyTestCommon


class TestCustodySecurityAccess(CustodyTestCommon):
    def test_user_cannot_approve(self):
        user = self.env["res.users"].create({
            "name": "Custody User",
            "login": "custody_user_test",
            "email": "custody_user_test@example.com",
            "company_id": self.company.id,
            "company_ids": [Command.set(self.company.ids)],
            "group_ids": [Command.set([self.env.ref("employee_custody_management.group_custody_user").id])],
        })
        request = self.create_request(amount=1000.0)
        request.user_id = user
        request = request.with_user(user)
        request.action_submit()
        with self.assertRaises(UserError):
            request.action_approve()

    def test_user_cannot_see_other_requests(self):
        request = self.create_request(amount=1000.0)
        user = self.env["res.users"].create({
            "name": "Other Custody User",
            "login": "other_custody_user_test",
            "email": "other_custody_user_test@example.com",
            "company_id": self.company.id,
            "company_ids": [Command.set(self.company.ids)],
            "group_ids": [Command.set([self.env.ref("employee_custody_management.group_custody_user").id])],
        })
        with self.assertRaises(AccessError):
            request.with_user(user).check_access("read")
