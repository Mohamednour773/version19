# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError


@tagged('post_install', '-at_install', 'petty_cash')
class TestPettyCashCustody(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Test Employee',
            'company_id': cls.company.id,
        })
        cls.manager = cls.env['hr.employee'].create({
            'name': 'Test Manager',
            'company_id': cls.company.id,
        })
        cls.cash_journal = cls.env['account.journal'].create({
            'name': 'PCM Journal',
            'type': 'cash',
            'code': 'PCMJ2',
            'company_id': cls.company.id,
        })
        cls.petty_account = cls.env['account.account'].create({
            'name': 'Petty Cash',
            'code': '101998',
            'account_type': 'asset_current',
            'company_id': cls.company.id,
        })
        cls.custody_account = cls.env['account.account'].create({
            'name': 'Employee Custody',
            'code': '115998',
            'account_type': 'asset_current',
            'company_id': cls.company.id,
        })
        # Set config param
        cls.env['ir.config_parameter'].sudo().set_param(
            'petty_cash.default_custody_account_id', str(cls.custody_account.id)
        )
        cls.fund = cls.env['petty.cash.fund'].create({
            'name': 'Main Fund',
            'name_ar': 'الصندوق الرئيسي',
            'code': 'MF001',
            'company_id': cls.company.id,
            'custodian_id': cls.employee.id,
            'journal_id': cls.cash_journal.id,
            'account_id': cls.petty_account.id,
            'max_balance': 20000.0,
            'min_balance': 2000.0,
        })

    def _create_custody(self, amount=1000.0):
        return self.env['hr.petty.cash'].create({
            'employee_id': self.employee.id,
            'petty_fund_id': self.fund.id,
            'requested_amount': amount,
            'company_id': self.company.id,
            'reason_ar': 'مصاريف إدارية',
        })

    def test_01_custody_sequence(self):
        """Custody gets auto-generated sequence."""
        custody = self._create_custody()
        self.assertNotEqual(custody.name, 'New')
        self.assertTrue(custody.name.startswith('PCM/'))

    def test_02_full_lifecycle_draft_to_paid(self):
        """Test: draft → waiting_approval → approved → paid."""
        custody = self._create_custody(500.0)
        self.assertEqual(custody.state, 'draft')

        custody.action_submit()
        self.assertEqual(custody.state, 'waiting_approval')

        custody.action_approve()
        self.assertEqual(custody.state, 'approved')
        self.assertEqual(custody.approved_amount, 500.0)

        custody.action_pay()
        self.assertEqual(custody.state, 'paid')
        self.assertEqual(custody.paid_amount, 500.0)
        self.assertTrue(custody.move_id)
        self.assertEqual(custody.move_id.state, 'posted')

    def test_03_refuse_and_reset(self):
        """Refused custody can be reset to draft."""
        custody = self._create_custody(200.0)
        custody.action_submit()
        custody.write({'state': 'refused', 'refuse_reason': 'Test refusal'})
        self.assertEqual(custody.state, 'refused')
        custody.action_reset_to_draft()
        self.assertEqual(custody.state, 'draft')

    def test_04_cannot_approve_own_request(self):
        """A user who submitted should not be able to approve (group check)."""
        # This is enforced at group level — here we just test state machine
        custody = self._create_custody(300.0)
        custody.action_submit()
        # Can only approve from waiting_approval
        with self.assertRaises(UserError):
            custody.action_pay()  # Pay without approval should fail

    def test_05_cannot_submit_zero_amount(self):
        """Cannot submit custody with zero amount."""
        custody = self.env['hr.petty.cash'].create({
            'employee_id': self.employee.id,
            'petty_fund_id': self.fund.id,
            'requested_amount': 0.0,
            'company_id': self.company.id,
        })
        with self.assertRaises(UserError):
            custody.action_submit()

    def test_06_return_amount(self):
        """Test full return flow: paid → return wizard → returned state."""
        custody = self._create_custody(400.0)
        custody.action_submit()
        custody.action_approve()
        custody.action_pay()
        self.assertEqual(custody.state, 'paid')

        # Simulate wizard
        wizard = self.env['petty.cash.return.wizard'].create({
            'custody_id': custody.id,
            'return_amount': 400.0,
        })
        wizard.action_confirm_return()
        self.assertEqual(custody.state, 'returned')

    def test_07_custody_close_after_return(self):
        """Can close a returned custody."""
        custody = self._create_custody(250.0)
        custody.action_submit()
        custody.action_approve()
        custody.action_pay()
        wizard = self.env['petty.cash.return.wizard'].create({
            'custody_id': custody.id,
            'return_amount': 250.0,
        })
        wizard.action_confirm_return()
        custody.action_close()
        self.assertEqual(custody.state, 'closed')
