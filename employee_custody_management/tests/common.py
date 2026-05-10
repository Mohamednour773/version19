from odoo import Command, fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class CustodyTestCommon(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.currency = cls.company.currency_id
        cls.receivable_account = cls._create_account("136910", "Employee Custody Receivable", "asset_receivable")
        cls.payable_account = cls._create_account("211910", "Trade Payables Test", "liability_payable")
        cls.expense_account = cls._create_account("611910", "Custody Expenses Test", "expense")
        cls.cash_account = cls._create_account("101910", "Custody Cash Test", "asset_cash")
        cls.company.write({
            "custody_receivable_account_id": cls.receivable_account.id,
            "custody_first_time_limit": 10000.0,
            "custody_require_settlement_before_new": True,
        })
        cls.funding_journal = cls.env["account.journal"].create({
            "name": "Test Funding Cash",
            "code": "TFC",
            "type": "cash",
            "company_id": cls.company.id,
            "default_account_id": cls.cash_account.id,
        })
        cls.custody_journal = cls.env["account.journal"].create({
            "name": "Test Custody Journal",
            "code": "TCJ",
            "type": "cash",
            "company_id": cls.company.id,
            "default_account_id": cls.cash_account.id,
        })
        cls.custody_journal.is_custody_journal = True
        cls.company.custody_default_journal_id = cls.custody_journal
        for journal in cls.funding_journal | cls.custody_journal:
            method_lines = journal.inbound_payment_method_line_ids | journal.outbound_payment_method_line_ids
            method_lines.filtered(lambda line: not line.payment_account_id).payment_account_id = cls.cash_account
        cls.category = cls.env["custody.category"].create({
            "name": "Office Supplies",
            "code": "TEST-OFF",
            "company_id": cls.company.id,
            "disbursement_limit": 20000.0,
        })
        cls.employee = cls.env["hr.employee"].create({
            "name": "Ahmed Test",
            "company_id": cls.company.id,
            "is_custody_holder": True,
            "custody_category_ids": [Command.set(cls.category.ids)],
        })
        cls.vendor = cls.env["res.partner"].create({"name": "Test Vendor"})

    @classmethod
    def _create_account(cls, code, name, account_type, company=None):
        company = company or cls.env.company
        return cls.env["account.account"].create({
            "code": code,
            "name": name,
            "account_type": account_type,
            "reconcile": account_type in ("asset_receivable", "liability_payable"),
            "company_ids": [Command.set(company.ids)],
        })

    def create_request(self, amount=5000.0, employee=None):
        request = self.env["custody.request"].create({
            "employee_id": (employee or self.employee).id,
            "category_id": self.category.id,
            "request_date": fields.Date.today(),
            "expected_settlement_date": fields.Date.add(fields.Date.today(), days=10),
            "amount": amount,
            "currency_id": self.currency.id,
            "journal_id": self.funding_journal.id,
            "custody_account_id": self.receivable_account.id,
            "description": "Test custody request",
            "company_id": self.company.id,
        })
        return request

    def issue_request(self, amount=5000.0, employee=None):
        request = self.create_request(amount=amount, employee=employee)
        request.action_submit()
        request.action_approve()
        request.action_issue()
        return request

    def create_vendor_bill(self, amount=1500.0):
        bill = self.env["account.move"].create({
            "move_type": "in_invoice",
            "partner_id": self.vendor.id,
            "invoice_date": fields.Date.today(),
            "company_id": self.company.id,
            "invoice_line_ids": [Command.create({
                "name": "Custody vendor expense",
                "quantity": 1.0,
                "price_unit": amount,
                "account_id": self.expense_account.id,
            })],
        })
        bill.action_post()
        return bill

    def pay_bill_from_custody(self, bill, employee=None, request=None, amount=1500.0):
        payable_line = bill.line_ids.filtered(lambda line: line.account_id.account_type == "liability_payable")[:1]
        payment = self.env["account.payment"].create({
            "date": fields.Date.today(),
            "amount": amount,
            "payment_type": "outbound",
            "partner_type": "supplier",
            "memo": bill.name,
            "journal_id": self.custody_journal.id,
            "company_id": self.company.id,
            "currency_id": self.currency.id,
            "partner_id": self.vendor.id,
            "destination_account_id": payable_line.account_id.id,
            "payment_method_line_id": self.custody_journal._get_available_payment_method_lines("outbound")[:1].id,
            "custody_employee_id": (employee or self.employee).id,
            "custody_request_id": request.id if request else False,
        })
        payment.action_post()
        (payment.move_id.line_ids + payable_line).filtered(lambda line: line.account_id == payable_line.account_id).reconcile()
        return payment
