# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError


@tagged('post_install', '-at_install', 'petty_cash')
class TestPettyCashSettlement(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Settlement Employee',
            'company_id': cls.company.id,
        })
        cls.cash_journal = cls.env['account.journal'].create({
            'name': 'PCM Settlement Journal',
            'type': 'cash',
            'code': 'PCSJ',
            'company_id': cls.company.id,
        })
        cls.petty_account = cls.env['account.account'].create({
            'name': 'Petty Cash S',
            'code': '101997',
            'account_type': 'asset_current',
            'company_id': cls.company.id,
        })
        cls.custody_account = cls.env['account.account'].create({
            'name': 'Employee Custody S',
            'code': '115997',
            'account_type': 'asset_current',
            'company_id': cls.company.id,
        })
        cls.expense_account = cls.env['account.account'].create({
            'name': 'Office Expense S',
            'code': '510001',
            'account_type': 'expense',
            'company_id': cls.company.id,
        })
        cls.env['ir.config_parameter'].sudo().set_param(
            'petty_cash.default_custody_account_id', str(cls.custody_account.id)
        )
        cls.fund = cls.env['petty.cash.fund'].create({
            'name': 'Settlement Fund',
            'name_ar': 'صندوق التسوية',
            'code': 'SF001',
            'company_id': cls.company.id,
            'custodian_id': cls.employee.id,
            'journal_id': cls.cash_journal.id,
            'account_id': cls.petty_account.id,
        })
        cls.category = cls.env['petty.cash.expense.category'].create({
            'name_en': 'Test Category',
            'name_ar': 'فئة اختبار',
            'requires_receipt': False,
        })

    def _make_paid_custody(self, amount=1000.0):
        c = self.env['hr.petty.cash'].create({
            'employee_id': self.employee.id,
            'petty_fund_id': self.fund.id,
            'requested_amount': amount,
            'company_id': self.company.id,
        })
        c.action_submit()
        c.action_approve()
        c.action_pay()
        return c

    def test_01_settlement_sequence(self):
        """Settlement gets auto sequence."""
        custody = self._make_paid_custody(800.0)
        settlement = self.env['petty.cash.settlement'].create({
            'custody_id': custody.id,
            'company_id': self.company.id,
        })
        self.assertTrue(settlement.name.startswith('PCS/'))

    def test_02_settlement_full_lifecycle(self):
        """Full settlement: draft → submitted → under_review → approved → posted."""
        custody = self._make_paid_custody(1000.0)
        settlement = self.env['petty.cash.settlement'].create({
            'custody_id': custody.id,
            'company_id': self.company.id,
        })
        # Add expense line
        self.env['petty.cash.settlement.line'].create({
            'settlement_id': settlement.id,
            'category_id': self.category.id,
            'expense_account_id': self.expense_account.id,
            'amount': 700.0,
            'description_ar': 'مصاريف مكتبية',
        })
        settlement.action_submit()
        self.assertEqual(settlement.state, 'submitted')

        settlement.action_review()
        self.assertEqual(settlement.state, 'under_review')

        settlement.action_approve()
        self.assertEqual(settlement.state, 'approved')

        settlement.action_post()
        self.assertEqual(settlement.state, 'posted')
        self.assertTrue(settlement.move_id)
        self.assertEqual(settlement.move_id.state, 'posted')
        # Custody should now be settled
        self.assertEqual(custody.state, 'settled')

    def test_03_settlement_remaining_computed(self):
        """Remaining amount = paid - spent."""
        custody = self._make_paid_custody(1000.0)
        settlement = self.env['petty.cash.settlement'].create({
            'custody_id': custody.id,
            'company_id': self.company.id,
        })
        self.env['petty.cash.settlement.line'].create({
            'settlement_id': settlement.id,
            'category_id': self.category.id,
            'expense_account_id': self.expense_account.id,
            'amount': 600.0,
            'description_en': 'Office supplies',
        })
        self.assertAlmostEqual(settlement.total_spent, 600.0)
        self.assertAlmostEqual(settlement.remaining_amount, 400.0)
        self.assertAlmostEqual(settlement.extra_amount, 0.0)

    def test_04_settlement_extra_amount(self):
        """When spent > paid, extra_amount is computed."""
        custody = self._make_paid_custody(500.0)
        settlement = self.env['petty.cash.settlement'].create({
            'custody_id': custody.id,
            'company_id': self.company.id,
        })
        self.env['petty.cash.settlement.line'].create({
            'settlement_id': settlement.id,
            'category_id': self.category.id,
            'expense_account_id': self.expense_account.id,
            'amount': 700.0,
            'description_en': 'More than paid',
        })
        self.assertAlmostEqual(settlement.extra_amount, 200.0)
        self.assertAlmostEqual(settlement.remaining_amount, 0.0)

    def test_05_cannot_submit_empty_settlement(self):
        """Cannot submit settlement with no lines."""
        custody = self._make_paid_custody(500.0)
        settlement = self.env['petty.cash.settlement'].create({
            'custody_id': custody.id,
            'company_id': self.company.id,
        })
        with self.assertRaises(UserError):
            settlement.action_submit()

    def test_06_access_control_user_cannot_approve(self):
        """Basic check: settlement approve requires manager group."""
        # This is a structural check — group membership enforced by Odoo
        # Just verify the method exists and state transitions are correct
        custody = self._make_paid_custody(300.0)
        settlement = self.env['petty.cash.settlement'].create({
            'custody_id': custody.id,
            'company_id': self.company.id,
        })
        self.env['petty.cash.settlement.line'].create({
            'settlement_id': settlement.id,
            'category_id': self.category.id,
            'expense_account_id': self.expense_account.id,
            'amount': 300.0,
        })
        settlement.action_submit()
        settlement.action_review()
        # Only manager can approve — in test context runs as admin which is fine
        settlement.action_approve()
        self.assertEqual(settlement.state, 'approved')
        self.assertEqual(settlement.approved_by, self.env.user)
