from odoo import Command

from .common import CustodyTestCommon


class TestCustodyMultiCompany(CustodyTestCommon):
    def test_company_accounts_do_not_leak(self):
        other_company = self.env["res.company"].create({"name": "Other Custody Company"})
        other_account = self._create_account("136920", "Other Custody", "asset_receivable", company=other_company)
        other_company.custody_receivable_account_id = other_account
        other_category = self.env["custody.category"].with_company(other_company).create({
            "name": "Other Office",
            "code": "OTHER-OFF",
            "company_id": other_company.id,
        })
        other_employee = self.env["hr.employee"].with_company(other_company).create({
            "name": "Other Employee",
            "company_id": other_company.id,
            "is_custody_holder": True,
            "custody_category_ids": [Command.set(other_category.ids)],
        })
        self.issue_request(amount=1000.0)
        self.assertEqual(other_employee._get_custody_balance(company=other_company), 0.0)
