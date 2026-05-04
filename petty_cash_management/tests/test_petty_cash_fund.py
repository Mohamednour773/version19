# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'petty_cash')
class TestPettyCashFund(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Test Custodian',
            'company_id': cls.company.id,
        })
        # Create a cash journal
        cls.cash_journal = cls.env['account.journal'].create({
            'name': 'Test Petty Cash Journal',
            'type': 'cash',
            'code': 'TPCJ',
            'company_id': cls.company.id,
        })
        # Create accounts
        account_type = cls.env.ref('account.data_account_type_current_assets', raise_if_not_found=False)
        cls.petty_account = cls.env['account.account'].create({
            'name': 'Petty Cash Test',
            'code': '101999',
            'account_type': 'asset_current',
            'company_id': cls.company.id,
        })

    def _create_fund(self, name='Test Fund', code='TF001'):
        return self.env['petty.cash.fund'].create({
            'name': name,
            'name_ar': 'صندوق اختبار',
            'code': code,
            'company_id': self.company.id,
            'custodian_id': self.employee.id,
            'journal_id': self.cash_journal.id,
            'account_id': self.petty_account.id,
            'max_balance': 10000.0,
            'min_balance': 1000.0,
        })

    def test_01_fund_creation(self):
        """Fund is created with correct defaults."""
        fund = self._create_fund()
        self.assertEqual(fund.state, 'active')
        self.assertEqual(fund.company_id, self.company)
        self.assertEqual(fund.custodian_id, self.employee)

    def test_02_fund_code_uniqueness(self):
        """Two funds with same code in same company should fail."""
        from odoo.exceptions import ValidationError
        self._create_fund(name='Fund A', code='UNIQUE001')
        with self.assertRaises(Exception):
            self._create_fund(name='Fund B', code='UNIQUE001')

    def test_03_fund_suspend_reactivate(self):
        """Fund can be suspended and reactivated."""
        fund = self._create_fund(code='TF003')
        fund.action_suspend()
        self.assertEqual(fund.state, 'suspended')
        fund.action_reactivate()
        self.assertEqual(fund.state, 'active')

    def test_04_fund_close_with_no_active_custodies(self):
        """Fund with no active custodies can be closed."""
        fund = self._create_fund(code='TF004')
        fund.action_close()
        self.assertEqual(fund.state, 'closed')

    def test_05_fund_close_blocked_with_active_custodies(self):
        """Fund cannot be closed if active custodies exist."""
        from odoo.exceptions import UserError
        fund = self._create_fund(code='TF005')
        # Create an active custody
        custody_account = self.env['account.account'].create({
            'name': 'Employee Custody Test',
            'code': '115999',
            'account_type': 'asset_current',
            'company_id': self.company.id,
        })
        self.env['ir.config_parameter'].sudo().set_param(
            'petty_cash.default_custody_account_id', str(custody_account.id)
        )
        self.env['hr.petty.cash'].create({
            'employee_id': self.employee.id,
            'petty_fund_id': fund.id,
            'requested_amount': 500.0,
            'company_id': self.company.id,
            'state': 'paid',
            'paid_amount': 500.0,
        })
        with self.assertRaises(UserError):
            fund.action_close()
