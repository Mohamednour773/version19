from odoo import Command, fields

from .common import CustodyTestCommon


class TestCustodySettlement(CustodyTestCommon):
    def test_settle_remaining_balance(self):
        request = self.issue_request(amount=5000.0)
        bill = self.create_vendor_bill(amount=1500.0)
        self.pay_bill_from_custody(bill, request=request, amount=1500.0)
        settlement = self.env["custody.settlement"].create({
            "request_id": request.id,
            "settlement_date": fields.Date.today(),
            "line_ids": [
                Command.create({
                    "type": "expense",
                    "description": "Unbilled cash spend",
                    "account_id": self.expense_account.id,
                    "amount": 2000.0,
                }),
                Command.create({
                    "type": "return_cash",
                    "description": "Cash returned",
                    "journal_id": self.funding_journal.id,
                    "amount": 1500.0,
                }),
            ],
        })
        settlement.action_post()
        self.assertEqual(settlement.state, "posted")
        self.assertEqual(request.state, "settled")
        self.assertAlmostEqual(self.employee._get_custody_balance(company=self.company), 0.0)
