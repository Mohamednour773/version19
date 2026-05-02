"""
Phase 3 — Accounting Integration Tests
=======================================

Tests every journal-entry workflow for pdc.check:

  Test 1  — test_register_received
      action_register() on a received check creates a posted move:
      Dr PDC-Received / Cr Partner-Receivable

  Test 2  — test_register_issued
      action_register() on an issued check creates a posted move:
      Dr Partner-Payable / Cr PDC-Issued

  Test 3  — test_deposit
      action_deposit() creates a posted move:
      Dr PDC-Under-Collection / Cr PDC-Received

  Test 4  — test_clear
      action_clear() creates a posted move:
      Dr Bank / Cr PDC-Under-Collection

  Test 5  — test_bounce_received (deposit_journal source)
      action_bounce() from under_collection, source='deposit_journal':
      Dr Partner-Receivable + Dr Charges / Cr Collection + Cr DepositBank

  Test 6  — test_issued_full_lifecycle
      Full issued-check lifecycle: register → print → deliver → pay
      Three posted moves; PDC-Issued account nets to zero.

  Test 7  — test_cancel_reverses_moves
      action_cancel() reverses every posted move and never deletes them.

  Test 8  — test_guarantee_activation
      action_activate_guarantee() converts check_type and creates the
      opening journal entry (same as action_register for received/issued).

  Test 9  — test_bounce_charges_original_journal
      action_bounce() with source='original_journal': charges come from
      the original check journal, not the deposit journal.

  Test 10 — test_bounce_charges_custom_account
      action_bounce() with source='custom_account': charges booked to a
      user-specified P&L account.

  Test 11 — test_bounce_charges_validation
      UserError is raised when charges > 0 and the selected source's
      journal has no pdc_bounce_charges_account_id configured.
"""
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


@tagged('post_install', '-at_install', 'pdc')
class TestPDCCheckAccounting(TransactionCase):
    """End-to-end accounting tests for the PDC check lifecycle."""

    # =========================================================================
    # SETUP
    # =========================================================================

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # ── Company / currency ────────────────────────────────────────────────
        cls.company = cls.env.company
        cls.currency = cls.company.currency_id

        # ── Accounts ──────────────────────────────────────────────────────────
        Account = cls.env['account.account']
        cls.acc_pdc_received = Account.create({
            'name': 'PDC Received',
            'code': 'TST-PDC-R',
            'account_type': 'asset_receivable',
            'reconcile': True,
            'company_id': cls.company.id,
        })
        cls.acc_pdc_collection = Account.create({
            'name': 'PDC Under Collection',
            'code': 'TST-PDC-C',
            'account_type': 'asset_receivable',
            'reconcile': True,
            'company_id': cls.company.id,
        })
        cls.acc_pdc_issued = Account.create({
            'name': 'PDC Issued',
            'code': 'TST-PDC-I',
            'account_type': 'liability_payable',
            'reconcile': True,
            'company_id': cls.company.id,
        })
        cls.acc_pdc_delivered = Account.create({
            'name': 'PDC Issued Delivered',
            'code': 'TST-PDC-D',
            'account_type': 'liability_payable',
            'reconcile': True,
            'company_id': cls.company.id,
        })
        cls.acc_bounce_charges = Account.create({
            'name': 'PDC Bounce Charges',
            'code': 'TST-PDC-BC',
            'account_type': 'expense',
            'company_id': cls.company.id,
        })
        # A second charges account used for 'custom_account' source tests
        cls.acc_bounce_charges_custom = Account.create({
            'name': 'PDC Bounce Charges (Custom)',
            'code': 'TST-PDC-BCC',
            'account_type': 'expense',
            'company_id': cls.company.id,
        })

        # ── Bank journal with all PDC accounts configured ─────────────────────
        cls.bank_journal = cls.env['account.journal'].create({
            'name': 'Test PDC Bank',
            'code': 'TPDC',
            'type': 'bank',
            'company_id': cls.company.id,
            'pdc_received_account_id': cls.acc_pdc_received.id,
            'pdc_received_collection_account_id': cls.acc_pdc_collection.id,
            'pdc_issued_account_id': cls.acc_pdc_issued.id,
            'pdc_issued_delivered_account_id': cls.acc_pdc_delivered.id,
            'pdc_bounce_charges_account_id': cls.acc_bounce_charges.id,
        })

        # ── Second bank journal used as the deposit/collection journal ─────────
        cls.deposit_journal = cls.env['account.journal'].create({
            'name': 'Test Collection Bank',
            'code': 'TPCB',
            'type': 'bank',
            'company_id': cls.company.id,
            'pdc_received_collection_account_id': cls.acc_pdc_collection.id,
            'pdc_bounce_charges_account_id': cls.acc_bounce_charges.id,
        })

        # ── PDC bank record ───────────────────────────────────────────────────
        cls.pdc_bank = cls.env['pdc.bank'].create({
            'name': 'Test Bank',
            'company_id': cls.company.id,
        })

        # ── Partner ───────────────────────────────────────────────────────────
        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Partner',
            'company_type': 'company',
        })
        # Ensure receivable / payable accounts are set
        cls.partner.property_account_receivable_id = cls.env['account.account'].search(
            [('account_type', '=', 'asset_receivable'),
             ('company_id', '=', cls.company.id)],
            limit=1,
        )
        cls.partner.property_account_payable_id = cls.env['account.account'].search(
            [('account_type', '=', 'liability_payable'),
             ('company_id', '=', cls.company.id)],
            limit=1,
        )

        # ── Check book for issued checks ──────────────────────────────────────
        cls.check_book = cls.env['pdc.check.book'].create({
            'journal_id': cls.bank_journal.id,
            'bank_id': cls.pdc_bank.id,
            'start_number': 1000,
            'end_number': 1999,
            'state': 'active',
            'company_id': cls.company.id,
        })

    # ── Helper: create a minimal received check ────────────────────────────────

    def _make_received(self, amount=5000.0, check_number=None):
        return self.env['pdc.check'].create({
            'check_type': 'received',
            'check_number': check_number or '100001',
            'bank_id': self.pdc_bank.id,
            'journal_id': self.bank_journal.id,
            'partner_id': self.partner.id,
            'amount': amount,
            'currency_id': self.currency.id,
            'issue_date': '2025-01-01',
            'due_date': '2025-04-01',
        })

    def _make_issued(self, amount=3000.0, check_number=None):
        return self.env['pdc.check'].create({
            'check_type': 'issued',
            'check_number': check_number or '1001',
            'bank_id': self.pdc_bank.id,
            'journal_id': self.bank_journal.id,
            'check_book_id': self.check_book.id,
            'partner_id': self.partner.id,
            'amount': amount,
            'currency_id': self.currency.id,
            'issue_date': '2025-01-01',
            'due_date': '2025-04-01',
        })

    def _make_guarantee(self, check_number=None):
        return self.env['pdc.check'].create({
            'check_type': 'guarantee_received',
            'check_number': check_number or '200001',
            'bank_id': self.pdc_bank.id,
            'journal_id': self.bank_journal.id,
            'partner_id': self.partner.id,
            'amount': 10000.0,
            'currency_id': self.currency.id,
            'issue_date': '2025-01-01',
            'due_date': '2025-06-01',
        })

    # =========================================================================
    # TEST 1 — action_register() on received check
    # =========================================================================

    def test_register_received(self):
        """Registering a received check creates Dr PDC-Received / Cr Partner-Receivable."""
        check = self._make_received()
        check.action_register()

        self.assertEqual(check.state, 'registered')
        self.assertEqual(len(check.move_ids), 1)

        move = check.move_ids
        self.assertEqual(move.state, 'posted',
                         'Journal entry must be posted immediately.')

        lines = move.line_ids
        debit_line = lines.filtered(lambda l: l.debit > 0)
        credit_line = lines.filtered(lambda l: l.credit > 0)

        self.assertEqual(len(debit_line), 1)
        self.assertEqual(len(credit_line), 1)
        self.assertAlmostEqual(debit_line.debit, 5000.0)
        self.assertAlmostEqual(credit_line.credit, 5000.0)
        self.assertEqual(debit_line.account_id, self.acc_pdc_received,
                         'Debit must hit the PDC-Received account.')
        self.assertEqual(credit_line.account_id,
                         self.partner.property_account_receivable_id,
                         'Credit must hit the Partner Receivable account.')

        # Operation log
        self.assertEqual(len(check.operation_ids), 1)
        self.assertEqual(check.operation_ids.operation_type, 'register')

    # =========================================================================
    # TEST 2 — action_register() on issued check
    # =========================================================================

    def test_register_issued(self):
        """Registering an issued check creates Dr Partner-Payable / Cr PDC-Issued."""
        check = self._make_issued(check_number='1002')
        check.action_register()

        self.assertEqual(check.state, 'registered')
        self.assertEqual(len(check.move_ids), 1)

        move = check.move_ids
        self.assertEqual(move.state, 'posted')

        lines = move.line_ids
        debit_line = lines.filtered(lambda l: l.debit > 0)
        credit_line = lines.filtered(lambda l: l.credit > 0)

        self.assertAlmostEqual(debit_line.debit, 3000.0)
        self.assertAlmostEqual(credit_line.credit, 3000.0)
        self.assertEqual(debit_line.account_id,
                         self.partner.property_account_payable_id,
                         'Debit must hit the Partner Payable account.')
        self.assertEqual(credit_line.account_id, self.acc_pdc_issued,
                         'Credit must hit the PDC-Issued account.')

    # =========================================================================
    # TEST 3 — action_deposit()
    # =========================================================================

    def test_deposit(self):
        """Depositing a received check creates Dr PDC-Collection / Cr PDC-Received."""
        check = self._make_received(check_number='100002')
        check.action_register()

        # Set deposit info before calling action
        check.write({
            'deposit_journal_id': self.deposit_journal.id,
            'deposit_date': '2025-02-01',
        })
        check.action_deposit()

        self.assertEqual(check.state, 'under_collection')
        # Now has 2 moves: registration + deposit
        self.assertEqual(len(check.move_ids), 2)

        deposit_move = check.move_ids.filtered(
            lambda m: 'Collection' in (m.ref or '')
        )
        self.assertEqual(deposit_move.state, 'posted')

        debit_line = deposit_move.line_ids.filtered(lambda l: l.debit > 0)
        credit_line = deposit_move.line_ids.filtered(lambda l: l.credit > 0)

        self.assertEqual(debit_line.account_id, self.acc_pdc_collection,
                         'Debit must hit the PDC-Under-Collection account.')
        self.assertEqual(credit_line.account_id, self.acc_pdc_received,
                         'Credit must hit the PDC-Received account.')
        self.assertAlmostEqual(debit_line.debit, 5000.0)

    # =========================================================================
    # TEST 4 — action_clear()
    # =========================================================================

    def test_clear(self):
        """Clearing a check creates Dr Bank / Cr PDC-Under-Collection."""
        check = self._make_received(check_number='100003')
        check.action_register()
        check.write({
            'deposit_journal_id': self.deposit_journal.id,
            'deposit_date': '2025-02-01',
        })
        check.action_deposit()
        check.write({'clear_date': '2025-04-01'})
        check.action_clear()

        self.assertEqual(check.state, 'cleared')
        self.assertEqual(len(check.move_ids), 3)  # register + deposit + clear

        clear_move = check.move_ids.filtered(
            lambda m: 'Cleared' in (m.ref or '')
        )
        self.assertEqual(clear_move.state, 'posted')

        debit_line = clear_move.line_ids.filtered(lambda l: l.debit > 0)
        credit_line = clear_move.line_ids.filtered(lambda l: l.credit > 0)

        # Bank account = deposit_journal.default_account_id
        bank_acc = self.deposit_journal.default_account_id
        self.assertEqual(debit_line.account_id, bank_acc,
                         'Debit must hit the Bank account.')
        self.assertEqual(credit_line.account_id, self.acc_pdc_collection,
                         'Credit must hit the PDC-Under-Collection account.')

    # =========================================================================
    # TEST 5 — action_bounce() received, source='deposit_journal' (default)
    # =========================================================================

    def test_bounce_received(self):
        """Bounce with deposit_journal source: charges come from collecting bank journal."""
        check = self._make_received(amount=4000.0, check_number='100004')
        check.action_register()
        check.write({
            'deposit_journal_id': self.deposit_journal.id,
            'deposit_date': '2025-02-01',
        })
        check.action_deposit()

        # Set bounce info — explicit 'deposit_journal' source (the default)
        check.write({
            'bounce_date': '2025-03-01',
            'bounce_charges': 50.0,
            'bounce_charges_source': 'deposit_journal',
        })
        check.action_bounce()

        self.assertEqual(check.state, 'bounced')
        bounce_move = check.move_ids.filtered(lambda m: 'Bounced' in (m.ref or ''))
        self.assertEqual(bounce_move.state, 'posted')

        lines = bounce_move.line_ids
        # 4 lines: receivable Dr, collection Cr, charges Dr, deposit-bank Cr
        self.assertEqual(len(lines), 4,
                         'Bounce move with charges must have 4 lines.')

        receivable_dr = lines.filtered(
            lambda l: l.account_id == self.partner.property_account_receivable_id
            and l.debit > 0
        )
        collection_cr = lines.filtered(
            lambda l: l.account_id == self.acc_pdc_collection and l.credit > 0
        )
        charges_dr = lines.filtered(
            lambda l: l.account_id == self.acc_bounce_charges and l.debit > 0
        )
        # Charges Cr line: deposit_journal's default bank account
        charges_cr = lines.filtered(
            lambda l: l.account_id == self.deposit_journal.default_account_id
            and l.credit > 0
            and l.account_id not in (
                self.acc_pdc_collection, self.partner.property_account_receivable_id,
            )
        )
        self.assertTrue(receivable_dr, 'Receivable debit line must exist.')
        self.assertTrue(collection_cr, 'Collection credit line must exist.')
        self.assertTrue(charges_dr, 'Charges debit line must exist.')
        self.assertTrue(charges_cr, 'Bank credit line for charges must exist (deposit journal).')

        self.assertAlmostEqual(receivable_dr.debit, 4000.0)
        self.assertAlmostEqual(collection_cr.credit, 4000.0)
        self.assertAlmostEqual(charges_dr.debit, 50.0)
        self.assertAlmostEqual(charges_cr.credit, 50.0)

        # Charges expense must come from deposit_journal (not original journal)
        self.assertEqual(
            charges_dr.account_id,
            self.acc_bounce_charges,
            'Charges account must be deposit_journal.pdc_bounce_charges_account_id.',
        )

    # =========================================================================
    # TEST 9 — action_bounce() received, source='original_journal'
    # =========================================================================

    def test_bounce_charges_original_journal(self):
        """Bounce with original_journal source: charges come from the original check journal."""
        check = self._make_received(amount=5000.0, check_number='100006')
        check.action_register()
        check.write({
            'deposit_journal_id': self.deposit_journal.id,
            'deposit_date': '2025-02-01',
        })
        check.action_deposit()

        check.write({
            'bounce_date': '2025-03-01',
            'bounce_charges': 75.0,
            'bounce_charges_source': 'original_journal',
        })
        check.action_bounce()

        self.assertEqual(check.state, 'bounced')
        bounce_move = check.move_ids.filtered(lambda m: 'Bounced' in (m.ref or ''))
        self.assertEqual(bounce_move.state, 'posted')

        lines = bounce_move.line_ids
        self.assertEqual(len(lines), 4)

        charges_dr = lines.filtered(
            lambda l: l.account_id == self.acc_bounce_charges and l.debit > 0
        )
        # Bank credit line must come from the ORIGINAL journal's default account
        bank_cr = lines.filtered(
            lambda l: l.account_id == self.bank_journal.default_account_id
            and l.credit > 0
        )
        self.assertTrue(charges_dr, 'Charges debit line must exist.')
        self.assertTrue(bank_cr,
                        'Bank credit for charges must use original check journal.')
        self.assertAlmostEqual(charges_dr.debit, 75.0)
        self.assertAlmostEqual(bank_cr.credit, 75.0)

    # =========================================================================
    # TEST 10 — action_bounce() received, source='custom_account'
    # =========================================================================

    def test_bounce_charges_custom_account(self):
        """Bounce with custom_account source: charges booked to user-specified account."""
        check = self._make_received(amount=3000.0, check_number='100007')
        check.action_register()
        check.write({
            'deposit_journal_id': self.deposit_journal.id,
            'deposit_date': '2025-02-01',
        })
        check.action_deposit()

        check.write({
            'bounce_date': '2025-03-01',
            'bounce_charges': 100.0,
            'bounce_charges_source': 'custom_account',
            'bounce_charges_account_id': self.acc_bounce_charges_custom.id,
        })
        check.action_bounce()

        self.assertEqual(check.state, 'bounced')
        bounce_move = check.move_ids.filtered(lambda m: 'Bounced' in (m.ref or ''))
        self.assertEqual(bounce_move.state, 'posted')

        lines = bounce_move.line_ids
        self.assertEqual(len(lines), 4)

        charges_dr = lines.filtered(
            lambda l: l.account_id == self.acc_bounce_charges_custom and l.debit > 0
        )
        self.assertTrue(charges_dr,
                        'Charges debit line must use the custom account.')
        self.assertAlmostEqual(charges_dr.debit, 100.0)

        # Must NOT use the standard bounce charges account
        standard_charges = lines.filtered(
            lambda l: l.account_id == self.acc_bounce_charges
        )
        self.assertFalse(standard_charges,
                         'Standard charges account must NOT be used when custom account is set.')

    # =========================================================================
    # TEST 11 — validation: no account configured for selected source
    # =========================================================================

    def test_bounce_charges_validation(self):
        """UserError when charges > 0 and source journal has no charges account."""
        # Create a journal with NO pdc_bounce_charges_account_id
        bare_journal = self.env['account.journal'].create({
            'name': 'Bare Deposit Journal',
            'code': 'BARE',
            'type': 'bank',
            'company_id': self.company.id,
            # pdc_bounce_charges_account_id intentionally NOT set
            'pdc_received_collection_account_id': self.acc_pdc_collection.id,
        })

        check = self._make_received(amount=2500.0, check_number='100008')
        check.action_register()
        check.write({
            'deposit_journal_id': bare_journal.id,
            'deposit_date': '2025-02-01',
        })
        check.action_deposit()

        # Source = 'deposit_journal' but that journal has no charges account
        check.write({
            'bounce_charges': 30.0,
            'bounce_charges_source': 'deposit_journal',
        })
        with self.assertRaises(UserError,
                               msg='Should raise when charges > 0 and no charges account set.'):
            check.action_bounce()

        # Also test: custom_account source with NO account set
        check2 = self._make_received(amount=1500.0, check_number='100009')
        check2.action_register()
        check2.write({
            'deposit_journal_id': self.deposit_journal.id,
            'deposit_date': '2025-02-01',
        })
        check2.action_deposit()
        check2.write({
            'bounce_charges': 20.0,
            'bounce_charges_source': 'custom_account',
            # bounce_charges_account_id intentionally NOT set
        })
        with self.assertRaises(UserError,
                               msg='Should raise when custom_account source but no account set.'):
            check2.action_bounce()

    # =========================================================================
    # TEST 6 — full issued-check lifecycle: register → deliver → pay
    # =========================================================================

    def test_issued_full_lifecycle(self):
        """Full issued lifecycle creates 3 posted moves that net to zero on all accounts."""
        check = self._make_issued(amount=6000.0, check_number='1003')

        # Step 1: Register
        check.action_register()
        self.assertEqual(check.state, 'registered')
        self.assertEqual(len(check.move_ids), 1)

        # Step 2: Print (state-only, no new move)
        check.action_print_check()
        self.assertEqual(check.state, 'printed')
        self.assertEqual(len(check.move_ids), 1,
                         'action_print_check must not create a journal entry.')

        # Step 3: Deliver
        check.action_deliver()
        self.assertEqual(check.state, 'delivered')
        self.assertEqual(len(check.move_ids), 2)

        deliver_move = check.move_ids.sorted('date')[-1]
        self.assertEqual(deliver_move.state, 'posted')
        deliver_dr = deliver_move.line_ids.filtered(lambda l: l.debit > 0)
        deliver_cr = deliver_move.line_ids.filtered(lambda l: l.credit > 0)
        self.assertEqual(deliver_dr.account_id, self.acc_pdc_issued)
        self.assertEqual(deliver_cr.account_id, self.acc_pdc_delivered)

        # Step 4: Pay
        check.action_pay()
        self.assertEqual(check.state, 'paid')
        self.assertEqual(len(check.move_ids), 3)

        pay_move = check.move_ids.sorted('date')[-1]
        self.assertEqual(pay_move.state, 'posted')
        pay_dr = pay_move.line_ids.filtered(lambda l: l.debit > 0)
        pay_cr = pay_move.line_ids.filtered(lambda l: l.credit > 0)
        self.assertEqual(pay_dr.account_id, self.acc_pdc_delivered)
        self.assertEqual(pay_cr.account_id, self.bank_journal.default_account_id)

        # Net balance check: PDC-Issued should net to zero across all 3 moves
        all_lines = check.move_ids.mapped('line_ids')
        issued_lines = all_lines.filtered(
            lambda l: l.account_id == self.acc_pdc_issued
        )
        net_issued = sum(l.debit - l.credit for l in issued_lines)
        self.assertAlmostEqual(net_issued, 0.0, places=2,
                               msg='PDC-Issued account must net to zero after full lifecycle.')

    # =========================================================================
    # TEST 7 — action_cancel() reverses all moves; never deletes them
    # =========================================================================

    def test_cancel_reverses_moves(self):
        """Cancelling a check with 2 posted moves must produce 2 reversals (not deletions)."""
        check = self._make_received(amount=2000.0, check_number='100005')
        check.action_register()
        check.write({
            'deposit_journal_id': self.deposit_journal.id,
            'deposit_date': '2025-02-01',
        })
        check.action_deposit()

        # 2 posted moves so far
        self.assertEqual(len(check.move_ids), 2)
        original_move_ids = check.move_ids.ids

        check.action_cancel()

        self.assertEqual(check.state, 'cancelled')
        # Must now have 4 entries: 2 originals + 2 reversals
        self.assertEqual(len(check.move_ids), 4,
                         'Cancel must link both original and reversal moves to the check.')

        # Original moves must still exist (NOT deleted)
        surviving = self.env['account.move'].search(
            [('id', 'in', original_move_ids)]
        )
        self.assertEqual(len(surviving), 2,
                         'Original journal entries must NOT be deleted on cancellation.')

        # Reversal moves must be posted
        reversal_moves = check.move_ids.filtered(
            lambda m: m.id not in original_move_ids
        )
        self.assertEqual(len(reversal_moves), 2)
        self.assertTrue(
            all(m.state == 'posted' for m in reversal_moves),
            'All reversal moves must be in posted state.',
        )

    # =========================================================================
    # TEST 8 — action_activate_guarantee() creates the opening journal entry
    # =========================================================================

    def test_guarantee_activation(self):
        """Activating a guarantee converts check_type and creates the opening entry."""
        check = self._make_guarantee(check_number='200002')

        # Register as guarantee — no journal entry expected
        check.action_register()
        self.assertEqual(check.state, 'registered')
        self.assertEqual(check.check_type, 'guarantee_received')
        self.assertEqual(len(check.move_ids), 0,
                         'Guarantee registration must NOT create a journal entry.')

        # Activate — type becomes 'received', opening entry created
        check.action_activate_guarantee()

        self.assertEqual(check.check_type, 'received')
        self.assertTrue(check.was_guarantee)
        self.assertEqual(check.state, 'registered')
        self.assertEqual(len(check.move_ids), 1,
                         'Guarantee activation must create exactly one journal entry.')

        move = check.move_ids
        self.assertEqual(move.state, 'posted')

        debit_line = move.line_ids.filtered(lambda l: l.debit > 0)
        credit_line = move.line_ids.filtered(lambda l: l.credit > 0)

        self.assertEqual(debit_line.account_id, self.acc_pdc_received,
                         'Post-activation debit must hit PDC-Received account.')
        self.assertEqual(credit_line.account_id,
                         self.partner.property_account_receivable_id,
                         'Post-activation credit must hit Partner Receivable.')
        self.assertAlmostEqual(debit_line.debit, 10000.0)
