"""
Phase 5 Wizard Tests
====================
Tests for the 6 PDC action wizards and 3 cron methods.

Run with:
    odoo-bin -d <db> --test-enable --stop-after-init -i pdc_management \
        --test-tags pdc,pdc_phase5
"""
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase
from odoo.tests import tagged


@tagged('post_install', '-at_install', 'pdc', 'pdc_phase5')
class TestPhase5Wizards(TransactionCase):
    """Integration tests for Phase 5 wizard models and cron methods."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Company
        cls.company = cls.env.company

        # Currency
        cls.currency_egp = cls.env.ref('base.EGP', raise_if_not_found=False) \
            or cls.env['res.currency'].search([('name', '=', 'EGP')], limit=1)
        if not cls.currency_egp:
            cls.currency_egp = cls.company.currency_id

        # Journals
        cls.journal = cls.env['account.journal'].search(
            [('type', '=', 'bank'), ('company_id', '=', cls.company.id)], limit=1,
        )
        cls.deposit_journal = cls.env['account.journal'].search(
            [('type', '=', 'bank'), ('company_id', '=', cls.company.id)], limit=1,
        )

        # Partner
        cls.partner = cls.env['res.partner'].create({
            'name': 'Phase5 Test Partner',
            'company_type': 'company',
        })

        # PDC Bank
        country_eg = cls.env.ref('base.eg', raise_if_not_found=False)
        cls.pdc_bank = cls.env['pdc.bank'].create({
            'name': 'Phase5 Test Bank',
            'code': 'P5TST',
            'country_id': country_eg.id if country_eg else cls.env['res.country'].search([], limit=1).id,
        })

        # Check book (issued)
        cls.check_book = cls.env['pdc.check.book'].create({
            'journal_id': cls.journal.id,
            'bank_id': cls.pdc_bank.id,
            'start_number': 5001,
            'end_number': 5050,
            'issue_date': '2025-01-01',
            'state': 'active',
            'company_id': cls.company.id,
        })

        # Bounce reason
        cls.bounce_reason = cls.env['pdc.bounce.reason'].search([], limit=1)
        if not cls.bounce_reason:
            cls.bounce_reason = cls.env['pdc.bounce.reason'].create({
                'name': 'Test NSF',
                'code': 'TEST_NSF',
            })

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _make_received_check(self, state='draft', amount=10000.0, due_days=30):
        """Create a received check and advance it to the requested state."""
        from odoo import fields
        check = self.env['pdc.check'].create({
            'check_type': 'received',
            'check_number': f'RCV-{amount:.0f}-{due_days}',
            'bank_id': self.pdc_bank.id,
            'partner_id': self.partner.id,
            'journal_id': self.journal.id,
            'amount': amount,
            'currency_id': self.currency_egp.id,
            'issue_date': fields.Date.today(),
            'due_date': fields.Date.add(fields.Date.today(), days=due_days),
            'company_id': self.company.id,
        })
        if state == 'draft':
            return check
        check.action_register()
        if state == 'registered':
            return check
        check.write({
            'deposit_journal_id': self.deposit_journal.id,
            'deposit_date': fields.Date.today(),
        })
        check.action_deposit()
        return check  # state == 'under_collection'

    def _make_issued_check(self, state='registered'):
        """Create a registered issued check."""
        from odoo import fields
        check = self.env['pdc.check'].create({
            'check_type': 'issued',
            'check_number': '5010',
            'check_book_id': self.check_book.id,
            'bank_id': self.pdc_bank.id,
            'partner_id': self.partner.id,
            'journal_id': self.journal.id,
            'amount': 5000.0,
            'currency_id': self.currency_egp.id,
            'issue_date': fields.Date.today(),
            'due_date': fields.Date.add(fields.Date.today(), days=30),
            'company_id': self.company.id,
        })
        check.action_register()
        return check

    # ═════════════════════════════════════════════════════════════════════════
    # REGISTER WIZARD
    # ═════════════════════════════════════════════════════════════════════════

    def test_register_wizard_registers_draft_check(self):
        """RegisterWizard advances a draft check to registered state."""
        check = self._make_received_check(state='draft')
        wiz = self.env['pdc.register.wizard'].create({
            'check_ids': [(4, check.id)],
        })
        wiz.action_register()
        self.assertEqual(check.state, 'registered')

    def test_register_wizard_empty_raises(self):
        """RegisterWizard raises UserError when no checks selected."""
        wiz = self.env['pdc.register.wizard'].create({
            'check_ids': [(5,)],
        })
        wiz.check_ids = [(5,)]  # explicitly empty
        with self.assertRaises(UserError):
            wiz.action_register()

    def test_register_wizard_default_get_from_context(self):
        """default_get() pre-fills check_ids from active_ids context."""
        check = self._make_received_check(state='draft')
        wiz = self.env['pdc.register.wizard'].with_context(
            active_model='pdc.check',
            active_ids=[check.id],
        ).create({})
        self.assertIn(check, wiz.check_ids)

    def test_register_wizard_opens_from_check(self):
        """action_open_register_wizard() returns an act_window action."""
        check = self._make_received_check(state='draft')
        result = check.action_open_register_wizard()
        self.assertEqual(result['type'], 'ir.actions.act_window')
        self.assertEqual(result['res_model'], 'pdc.register.wizard')

    # ═════════════════════════════════════════════════════════════════════════
    # DEPOSIT WIZARD
    # ═════════════════════════════════════════════════════════════════════════

    def test_deposit_wizard_deposits_registered_check(self):
        """DepositWizard transitions registered → under_collection."""
        check = self._make_received_check(state='registered')
        wiz = self.env['pdc.deposit.wizard'].create({
            'check_ids': [(4, check.id)],
            'deposit_journal_id': self.deposit_journal.id,
        })
        wiz.action_deposit()
        self.assertEqual(check.state, 'under_collection')
        self.assertEqual(check.deposit_journal_id, self.deposit_journal)

    def test_deposit_wizard_skipped_count(self):
        """skipped_count counts non-eligible checks correctly."""
        draft_check = self._make_received_check(state='draft')
        registered_check = self._make_received_check(state='registered', amount=2000.0)
        wiz = self.env['pdc.deposit.wizard'].create({
            'check_ids': [(4, draft_check.id), (4, registered_check.id)],
            'deposit_journal_id': self.deposit_journal.id,
        })
        self.assertEqual(wiz.skipped_count, 1)

    def test_deposit_wizard_opens_from_check(self):
        """action_open_deposit_wizard() returns act_window action."""
        check = self._make_received_check(state='registered')
        result = check.action_open_deposit_wizard()
        self.assertEqual(result['type'], 'ir.actions.act_window')
        self.assertEqual(result['res_model'], 'pdc.deposit.wizard')

    # ═════════════════════════════════════════════════════════════════════════
    # CLEAR WIZARD
    # ═════════════════════════════════════════════════════════════════════════

    def test_clear_wizard_clears_check(self):
        """ClearWizard transitions under_collection → cleared."""
        from odoo import fields
        check = self._make_received_check(state='under_collection')
        wiz = self.env['pdc.clear.wizard'].create({
            'check_ids': [(4, check.id)],
            'clear_date': fields.Date.today(),
        })
        wiz.action_clear()
        self.assertEqual(check.state, 'cleared')

    def test_clear_wizard_totals_single_currency(self):
        """total_amount is computed when all checks share one currency."""
        from odoo import fields
        c1 = self._make_received_check(state='under_collection', amount=1000.0)
        c2 = self._make_received_check(state='under_collection', amount=2000.0, due_days=45)
        wiz = self.env['pdc.clear.wizard'].create({
            'check_ids': [(4, c1.id), (4, c2.id)],
            'clear_date': fields.Date.today(),
        })
        self.assertAlmostEqual(wiz.total_amount, 3000.0, places=2)
        self.assertFalse(wiz.multi_currency)

    def test_clear_wizard_opens_from_check(self):
        """action_open_clear_wizard() returns act_window action."""
        check = self._make_received_check(state='under_collection')
        result = check.action_open_clear_wizard()
        self.assertEqual(result['type'], 'ir.actions.act_window')
        self.assertEqual(result['res_model'], 'pdc.clear.wizard')

    # ═════════════════════════════════════════════════════════════════════════
    # BOUNCE WIZARD
    # ═════════════════════════════════════════════════════════════════════════

    def test_bounce_wizard_bounces_check(self):
        """BounceWizard transitions under_collection → bounced."""
        from odoo import fields
        check = self._make_received_check(state='under_collection')
        wiz = self.env['pdc.bounce.wizard'].create({
            'check_ids': [(4, check.id)],
            'bounce_date': fields.Date.today(),
            'bounce_reason_id': self.bounce_reason.id,
            'bounce_charges': 0.0,
            'bounce_charges_source': 'deposit_journal',
        })
        wiz.action_bounce()
        self.assertEqual(check.state, 'bounced')

    def test_bounce_wizard_custom_account_requires_account(self):
        """BounceWizard raises UserError when custom_account source has no account."""
        from odoo import fields
        check = self._make_received_check(state='under_collection', amount=500.0)
        wiz = self.env['pdc.bounce.wizard'].create({
            'check_ids': [(4, check.id)],
            'bounce_date': fields.Date.today(),
            'bounce_charges': 50.0,
            'bounce_charges_source': 'custom_account',
            # bounce_charges_account_id intentionally omitted
        })
        with self.assertRaises(UserError):
            wiz.action_bounce()

    def test_bounce_wizard_show_charges_account_flag(self):
        """show_charges_account is True only when source is custom_account."""
        wiz = self.env['pdc.bounce.wizard'].create({
            'bounce_charges_source': 'custom_account',
        })
        self.assertTrue(wiz.show_charges_account)
        wiz.write({'bounce_charges_source': 'deposit_journal'})
        self.assertFalse(wiz.show_charges_account)

    def test_bounce_wizard_legal_action_flag(self):
        """is_legal_action reflects the bounce reason flag."""
        legal_reason = self.env['pdc.bounce.reason'].search(
            [('is_legal_action', '=', True)], limit=1,
        )
        if not legal_reason:
            self.skipTest('No legal-action bounce reason found in test DB.')
        wiz = self.env['pdc.bounce.wizard'].create({
            'bounce_reason_id': legal_reason.id,
        })
        self.assertTrue(wiz.is_legal_action)

    def test_bounce_wizard_opens_from_check(self):
        """action_open_bounce_wizard() returns act_window action."""
        check = self._make_received_check(state='under_collection')
        result = check.action_open_bounce_wizard()
        self.assertEqual(result['type'], 'ir.actions.act_window')
        self.assertEqual(result['res_model'], 'pdc.bounce.wizard')

    # ═════════════════════════════════════════════════════════════════════════
    # CANCEL WIZARD
    # ═════════════════════════════════════════════════════════════════════════

    def test_cancel_wizard_cancels_registered_check(self):
        """CancelWizard cancels a registered check."""
        check = self._make_received_check(state='registered')
        wiz = self.env['pdc.cancel.wizard'].create({
            'check_ids': [(4, check.id)],
            'cancel_reason': 'Test cancellation — unit test',
        })
        wiz.action_cancel()
        self.assertEqual(check.state, 'cancelled')

    def test_cancel_wizard_requires_reason(self):
        """CancelWizard raises UserError when cancel_reason is empty."""
        check = self._make_received_check(state='registered')
        wiz = self.env['pdc.cancel.wizard'].create({
            'check_ids': [(4, check.id)],
            'cancel_reason': '   ',  # blank / whitespace
        })
        with self.assertRaises(UserError):
            wiz.action_cancel()

    def test_cancel_wizard_under_collection_requires_confirm(self):
        """CancelWizard blocks cancellation of under_collection without confirm."""
        check = self._make_received_check(state='under_collection')
        wiz = self.env['pdc.cancel.wizard'].create({
            'check_ids': [(4, check.id)],
            'cancel_reason': 'Cancelling under-collection check',
            'confirm_under_collection': False,
        })
        self.assertTrue(wiz.has_under_collection)
        with self.assertRaises(UserError):
            wiz.action_cancel()

    def test_cancel_wizard_under_collection_with_confirm(self):
        """CancelWizard succeeds when confirm_under_collection is checked."""
        check = self._make_received_check(state='under_collection')
        wiz = self.env['pdc.cancel.wizard'].create({
            'check_ids': [(4, check.id)],
            'cancel_reason': 'Cancelling under-collection check',
            'confirm_under_collection': True,
        })
        wiz.action_cancel()
        self.assertEqual(check.state, 'cancelled')

    def test_cancel_wizard_opens_from_check(self):
        """action_open_cancel_wizard() returns act_window action."""
        check = self._make_received_check(state='registered')
        result = check.action_open_cancel_wizard()
        self.assertEqual(result['type'], 'ir.actions.act_window')
        self.assertEqual(result['res_model'], 'pdc.cancel.wizard')

    # ═════════════════════════════════════════════════════════════════════════
    # PRINT CHECK WIZARD
    # ═════════════════════════════════════════════════════════════════════════

    def test_print_wizard_marks_as_printed(self):
        """PrintCheckWizard marks check as printed when mark_as_printed=True."""
        check = self._make_issued_check(state='registered')
        wiz = self.env['pdc.print.check.wizard'].create({
            'check_ids': [(4, check.id)],
            'mark_as_printed': True,
        })
        # action_print() returns the report action — the mark-as-printed side effect
        # is what we test; mock the report to avoid PDF generation in tests.
        report = self.env.ref('pdc_management_v19.action_report_pdc_check')
        with patch.object(type(report), 'report_action', return_value={'type': 'ir.actions.report'}):
            wiz.action_print()
        self.assertEqual(check.state, 'printed')

    def test_print_wizard_no_mark_keeps_state(self):
        """PrintCheckWizard does NOT advance state when mark_as_printed=False."""
        check = self._make_issued_check(state='registered')
        wiz = self.env['pdc.print.check.wizard'].create({
            'check_ids': [(4, check.id)],
            'mark_as_printed': False,
        })
        report = self.env.ref('pdc_management_v19.action_report_pdc_check')
        with patch.object(type(report), 'report_action', return_value={'type': 'ir.actions.report'}):
            wiz.action_print()
        self.assertEqual(check.state, 'registered')

    def test_print_wizard_opens_from_check(self):
        """action_open_print_check_wizard() returns act_window action."""
        check = self._make_issued_check(state='registered')
        result = check.action_open_print_check_wizard()
        self.assertEqual(result['type'], 'ir.actions.act_window')
        self.assertEqual(result['res_model'], 'pdc.print.check.wizard')

    # ═════════════════════════════════════════════════════════════════════════
    # CRON METHODS
    # ═════════════════════════════════════════════════════════════════════════

    def test_cron_due_reminders_runs_without_error(self):
        """_cron_send_due_reminders() executes without raising exceptions."""
        try:
            self.env['pdc.check']._cron_send_due_reminders()
        except Exception as exc:
            self.fail(f'_cron_send_due_reminders() raised: {exc}')

    def test_cron_overdue_detection_runs_without_error(self):
        """_cron_detect_overdue_under_collection() executes without raising exceptions."""
        try:
            self.env['pdc.check']._cron_detect_overdue_under_collection()
        except Exception as exc:
            self.fail(f'_cron_detect_overdue_under_collection() raised: {exc}')

    def test_cron_book_low_stock_runs_without_error(self):
        """_cron_check_book_low_stock() executes without raising exceptions."""
        try:
            self.env['pdc.check.book']._cron_check_book_low_stock()
        except Exception as exc:
            self.fail(f'_cron_check_book_low_stock() raised: {exc}')

    def test_cron_due_reminders_finds_near_due_check(self):
        """_cron_send_due_reminders() finds checks due within threshold and attempts send."""
        from odoo import fields
        # Create a check due in exactly 3 days (first threshold default)
        check = self._make_received_check(state='registered', due_days=3)
        # Patch send_mail to count calls rather than actually sending
        call_count = {'n': 0}

        original_send = None

        def mock_send_mail(record_id, **kwargs):
            call_count['n'] += 1

        template = self.env.ref(
            'pdc_management_v19.mail_template_pdc_due_soon', raise_if_not_found=False,
        )
        if not template:
            self.skipTest('Due-soon template not loaded.')

        with patch.object(type(template), 'send_mail', mock_send_mail):
            self.env['pdc.check']._cron_send_due_reminders()

        self.assertGreaterEqual(
            call_count['n'], 1,
            'Expected at least one reminder to be sent for the near-due check.',
        )

    def test_cron_book_low_stock_detects_low_book(self):
        """_cron_check_book_low_stock() detects an active book below threshold."""
        # Create a book with just 2 leaves and low_stock_threshold=5
        low_book = self.env['pdc.check.book'].create({
            'journal_id': self.journal.id,
            'bank_id': self.pdc_bank.id,
            'start_number': 9001,
            'end_number': 9003,   # 3 checks total
            'low_stock_threshold': 10,  # threshold higher than total → always low
            'issue_date': '2025-01-01',
            'state': 'active',
            'company_id': self.company.id,
        })
        self.assertTrue(low_book.low_stock_alert)

        call_count = {'n': 0}

        def mock_send_mail(record_id, **kwargs):
            call_count['n'] += 1

        template = self.env.ref(
            'pdc_management_v19.mail_template_pdc_book_low', raise_if_not_found=False,
        )
        if not template:
            self.skipTest('Book-low template not loaded.')

        with patch.object(type(template), 'send_mail', mock_send_mail):
            self.env['pdc.check.book']._cron_check_book_low_stock()

        self.assertGreaterEqual(call_count['n'], 1)
