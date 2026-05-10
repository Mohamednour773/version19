from odoo.exceptions import UserError

from .common import CustodyTestCommon


class TestCustodyRequestWorkflow(CustodyTestCommon):
    def test_full_happy_path_issues_payment(self):
        request = self.issue_request()
        self.assertEqual(request.state, "issued")
        self.assertTrue(request.payment_id)
        custody_line = request.payment_id.move_id.line_ids.filtered(lambda line: line.account_id == self.receivable_account)
        self.assertEqual(custody_line.partner_id, self.employee.work_contact_id)
        self.assertAlmostEqual(custody_line.debit, 5000.0)

    def test_first_time_over_limit_is_rejected(self):
        request = self.create_request(amount=15000.0)
        request.action_submit()
        with self.assertRaises(UserError):
            request.action_approve()

    def test_double_issuance_is_rejected(self):
        self.issue_request()
        second = self.create_request(amount=1000.0)
        second.action_submit()
        with self.assertRaises(UserError):
            second.action_approve()

    def test_cancel_after_issue(self):
        request = self.issue_request()
        request.action_cancel()
        self.assertEqual(request.state, "cancelled")
        self.assertEqual(request.payment_id.state, "canceled")
