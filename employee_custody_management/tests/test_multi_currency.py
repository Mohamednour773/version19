from odoo import fields

from .common import CustodyTestCommon


class TestCustodyMultiCurrency(CustodyTestCommon):
    def test_foreign_currency_balance_preview(self):
        usd = self.env.ref("base.USD")
        self.env["res.currency.rate"].create({
            "name": fields.Date.today(),
            "currency_id": usd.id,
            "company_id": self.company.id,
            "rate": 0.02,
        })
        request = self.create_request(amount=100.0)
        request.currency_id = usd
        request.action_submit()
        request.action_approve()
        request.action_issue()
        self.assertTrue(request.payment_id.move_id)
        self.assertGreater(self.employee._get_custody_balance(company=self.company), 0.0)
