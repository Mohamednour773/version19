from .common import CustodyTestCommon


class TestCustodyPaymentIntegration(CustodyTestCommon):
    def test_vendor_bill_payment_from_custody(self):
        request = self.issue_request(amount=5000.0)
        bill = self.create_vendor_bill(amount=1500.0)
        payment = self.pay_bill_from_custody(bill, request=request, amount=1500.0)
        lines = payment.move_id.line_ids
        ap_line = lines.filtered(lambda line: line.account_id.account_type == "liability_payable")
        custody_line = lines.filtered(lambda line: line.account_id == self.receivable_account)
        self.assertEqual(len(ap_line), 1)
        self.assertEqual(len(custody_line), 1)
        self.assertEqual(ap_line.partner_id, self.vendor)
        self.assertEqual(custody_line.partner_id, self.employee.work_contact_id)
        self.assertAlmostEqual(ap_line.debit, 1500.0)
        self.assertAlmostEqual(custody_line.credit, 1500.0)
        self.assertIn(bill.payment_state, ("paid", "in_payment"))
        self.assertAlmostEqual(self.employee._get_custody_balance(company=self.company), 3500.0)
        ledger = self.env["account.move.line"].search([
            ("account_id", "=", self.receivable_account.id),
            ("partner_id", "=", self.employee.work_contact_id.id),
            ("parent_state", "=", "posted"),
        ])
        self.assertEqual(len(ledger), 2)
        self.assertEqual(request.state, "partially_settled")
