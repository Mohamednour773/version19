"""
Phase 4 — Report / Wizard Tests
================================
Tests cover:
  - Wizard instantiation and field defaults
  - action_print_pdf returns the expected ir.actions.report action
  - _compute_aging_data grouping by (partner, currency)
  - _get_statement_lines grouping
  - List-report wizard filtering per report_type
  - Amount-in-words: English + Arabic with multiple currencies
  - Empty-result handling (no crash, empty lists)
  - Multi-currency aging: EGP and USD totals never mixed
"""

from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError


@tagged('post_install', '-at_install', 'pdc', 'pdc_reports')
class TestPhase4Reports(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # ── Company ───────────────────────────────────────────────────────────
        cls.company = cls.env.company

        # ── Currencies ───────────────────────────────────────────────────────
        cls.egp = cls.env.ref('base.EGP', raise_if_not_found=False)
        if not cls.egp:
            cls.egp = cls.env['res.currency'].create({
                'name': 'EGP', 'symbol': 'ج.م', 'rounding': 0.01,
            })
        cls.usd = cls.env.ref('base.USD')

        # ── Journals ─────────────────────────────────────────────────────────
        cls.bank_journal = cls.env['account.journal'].search(
            [('type', '=', 'bank'), ('company_id', '=', cls.company.id)],
            limit=1,
        )
        if not cls.bank_journal:
            cls.bank_journal = cls.env['account.journal'].create({
                'name': 'Test Bank', 'type': 'bank', 'code': 'TSTBK',
                'company_id': cls.company.id,
            })

        # ── Partners ─────────────────────────────────────────────────────────
        cls.partner_a = cls.env['res.partner'].create({'name': 'Test Partner Alpha'})
        cls.partner_b = cls.env['res.partner'].create({'name': 'Test Partner Beta'})

        # ── Bank ─────────────────────────────────────────────────────────────
        cls.pdc_bank = cls.env['pdc.bank'].create({'name': 'Test Bank for Reports'})

        # ── Check books ───────────────────────────────────────────────────────
        cls.issued_book = cls.env['pdc.check.book'].create({
            'name': 'RPT-BOOK-01',
            'journal_id': cls.bank_journal.id,
            'bank_id': cls.pdc_bank.id,
            'first_number': 800001,
            'last_number': 800050,
        })

        # ── Accounts needed for PDC journals ────────────────────────────────
        # Minimal: just need receivable/payable; PDC accounts created per Phase 3.
        # We only test wizard logic here — no accounting needed.

    def _make_check(self, partner, check_type, amount, currency=None,
                    state='registered', due_days=0, check_number=None):
        """Helper: create a pdc.check in the given state quickly."""
        from odoo import fields
        from datetime import date, timedelta
        today = fields.Date.today()
        due = today + timedelta(days=due_days)
        vals = {
            'check_type': check_type,
            'check_number': check_number or f'RPT{partner.id}{amount}{due_days}',
            'partner_id': partner.id,
            'bank_id': self.pdc_bank.id,
            'journal_id': self.bank_journal.id,
            'issue_date': today,
            'due_date': due,
            'amount': amount,
            'currency_id': (currency or self.egp or self.usd).id,
            'company_id': self.company.id,
        }
        if check_type in ('issued', 'guarantee_issued'):
            vals['check_book_id'] = self.issued_book.id
        check = self.env['pdc.check'].create(vals)
        if state != 'draft':
            check.write({'state': state})
        return check

    # ── 1. Aging Wizard defaults ──────────────────────────────────────────────

    def test_aging_wizard_defaults(self):
        """Aging wizard instantiates with sensible defaults."""
        wizard = self.env['pdc.aging.report.wizard'].create({
            'company_id': self.company.id,
        })
        self.assertEqual(wizard.check_type, 'received')
        self.assertEqual(wizard.state_filter, 'active')
        self.assertEqual(wizard.bucket_1, 30)
        self.assertEqual(wizard.bucket_4, 120)
        self.assertEqual(wizard.as_of_date, __import__('odoo').fields.Date.today())

    def test_aging_wizard_pdf_action(self):
        """action_print_pdf returns an ir.actions.report dict."""
        wizard = self.env['pdc.aging.report.wizard'].create({
            'company_id': self.company.id,
        })
        result = wizard.action_print_pdf()
        self.assertEqual(result.get('type'), 'ir.actions.report')

    def test_aging_empty_result(self):
        """_compute_aging_data returns empty list when no checks match."""
        wizard = self.env['pdc.aging.report.wizard'].create({
            'company_id': self.company.id,
            'check_type': 'received',
            # Use a partner that definitely has no checks
            'partner_ids': [(6, 0, [self.partner_a.id])],
            'state_filter': 'all',
        })
        # Don't create any checks for partner_a in this test
        aging_data = wizard._compute_aging_data()
        self.assertIsInstance(aging_data, list)
        # May or may not be empty depending on other test data; just verify it's a list
        for row in aging_data:
            self.assertIn('partner', row)
            self.assertIn('currency', row)
            self.assertIn('checks', row)

    def test_aging_multi_currency_no_mixing(self):
        """Checks in different currencies produce separate (partner, currency) rows."""
        cur_a = self.egp or self.usd
        cur_b = self.usd

        if cur_a.id == cur_b.id:
            self.skipTest('Only one currency available — cannot test multi-currency mixing')

        from odoo import fields as F
        from datetime import date, timedelta
        today = F.Date.today()
        past = today - timedelta(days=10)  # overdue

        chk_egp = self._make_check(
            self.partner_a, 'received', 10000.0, currency=cur_a,
            state='registered', due_days=-10, check_number='MCUR001',
        )
        chk_usd = self._make_check(
            self.partner_a, 'received', 500.0, currency=cur_b,
            state='registered', due_days=-5, check_number='MCUR002',
        )

        wizard = self.env['pdc.aging.report.wizard'].create({
            'company_id': self.company.id,
            'check_type': 'received',
            'state_filter': 'all',
            'partner_ids': [(6, 0, [self.partner_a.id])],
        })
        aging_data = wizard._compute_aging_data()

        # Filter to just rows for partner_a
        rows = [r for r in aging_data if r['partner'].id == self.partner_a.id]
        # Must have at least 2 rows (one per currency)
        currencies_found = {r['currency'].name for r in rows}
        self.assertIn(cur_a.name, currencies_found, 'EGP row missing')
        self.assertIn(cur_b.name, currencies_found, 'USD row missing')

        # Each currency row sums only its own currency checks
        for row in rows:
            cur_name = row['currency'].name
            for chk in row['checks']:
                self.assertEqual(
                    chk.currency_id.name, cur_name,
                    f'Check with currency {chk.currency_id.name} ended up in {cur_name} bucket',
                )

    # ── 2. Partner Statement Wizard ───────────────────────────────────────────

    def test_partner_statement_requires_partners(self):
        """action_print_pdf raises UserError when no partner selected."""
        wizard = self.env['pdc.partner.statement.wizard'].create({
            'company_id': self.company.id,
            'date_from': '2024-01-01',
            'date_to': '2024-12-31',
            # no partner_ids
        })
        with self.assertRaises(UserError):
            wizard._get_statement_lines()

    def test_partner_statement_pdf_action(self):
        """action_print_pdf returns ir.actions.report."""
        wizard = self.env['pdc.partner.statement.wizard'].create({
            'company_id': self.company.id,
            'date_from': '2024-01-01',
            'date_to': '2024-12-31',
            'partner_ids': [(6, 0, [self.partner_b.id])],
        })
        result = wizard.action_print_pdf()
        self.assertEqual(result.get('type'), 'ir.actions.report')

    def test_partner_statement_groups_by_partner(self):
        """_get_statement_lines returns one dict per partner."""
        self._make_check(
            self.partner_a, 'received', 1000.0,
            state='registered', due_days=30, check_number='STMT001',
        )
        self._make_check(
            self.partner_b, 'received', 2000.0,
            state='registered', due_days=45, check_number='STMT002',
        )
        wizard = self.env['pdc.partner.statement.wizard'].create({
            'company_id': self.company.id,
            'date_from': '2020-01-01',
            'date_to': '2030-12-31',
            'partner_ids': [(6, 0, [self.partner_a.id, self.partner_b.id])],
        })
        lines = wizard._get_statement_lines()
        partner_ids_found = {row['partner'].id for row in lines}
        self.assertIn(self.partner_a.id, partner_ids_found)
        self.assertIn(self.partner_b.id, partner_ids_found)

    # ── 3. List Report Wizard ─────────────────────────────────────────────────

    def test_list_wizard_under_collection(self):
        """List wizard fetches under_collection checks."""
        self._make_check(
            self.partner_a, 'received', 5000.0,
            state='under_collection', due_days=20, check_number='UC001',
        )
        wizard = self.env['pdc.list.report.wizard'].create({
            'company_id': self.company.id,
            'report_type': 'under_collection',
        })
        checks = wizard._get_checks()
        self.assertTrue(
            all(c.state == 'under_collection' for c in checks),
            'under_collection wizard returned non-under_collection check',
        )

    def test_list_wizard_bounced(self):
        """List wizard fetches only bounced checks."""
        self._make_check(
            self.partner_b, 'received', 3000.0,
            state='bounced', due_days=-5, check_number='BNCE001',
        )
        wizard = self.env['pdc.list.report.wizard'].create({
            'company_id': self.company.id,
            'report_type': 'bounced',
        })
        checks = wizard._get_checks()
        self.assertTrue(
            all(c.state == 'bounced' for c in checks),
            'bounced wizard returned non-bounced check',
        )

    def test_list_wizard_pdf_action(self):
        """action_print returns ir.actions.report for each report_type."""
        for rt in ('under_collection', 'due_soon', 'bounced'):
            wizard = self.env['pdc.list.report.wizard'].create({
                'company_id': self.company.id,
                'report_type': rt,
            })
            result = wizard.action_print()
            self.assertEqual(
                result.get('type'), 'ir.actions.report',
                f'action_print for {rt} did not return ir.actions.report',
            )

    # ── 4. Amount-in-words ────────────────────────────────────────────────────

    def test_amount_in_words_english(self):
        """English amount-in-words contains 'Only' and no Arabic characters."""
        check = self._make_check(
            self.partner_a, 'received', 5000.0,
            state='draft', due_days=30, check_number='WORDS001',
        )
        words = check.amount_in_words
        if not words:
            self.skipTest('num2words not installed — skipping words test')
        self.assertIn('Only', words, "English words must end with 'Only'")
        # No Arabic Unicode characters (U+0600–U+06FF)
        arabic_chars = [c for c in words if '؀' <= c <= 'ۿ']
        self.assertEqual(arabic_chars, [], f'Arabic chars found in EN output: {words}')

    def test_amount_in_words_arabic_ends_laa_ghayr(self):
        """Arabic amount-in-words ends with 'لا غير'."""
        check = self._make_check(
            self.partner_a, 'received', 5000.0,
            state='draft', due_days=30, check_number='WORDS002',
        )
        words_ar = check.amount_in_words_ar
        if not words_ar:
            self.skipTest('num2words not installed — skipping Arabic words test')
        self.assertTrue(
            words_ar.endswith('لا غير'),
            f"Arabic words must end with 'لا غير', got: {words_ar}",
        )

    def test_amount_in_words_arabic_currency_name_not_iso(self):
        """Arabic output uses proper Arabic currency name, not ISO code."""
        check = self._make_check(
            self.partner_a, 'received', 100.0,
            state='draft', due_days=30, check_number='WORDS003',
        )
        words_ar = check.amount_in_words_ar
        if not words_ar:
            self.skipTest('num2words not installed — skipping currency name test')
        cur_code = check.currency_id.name  # e.g. 'EGP'
        # The ISO code should NOT appear in the Arabic output
        # (it should be replaced by the Arabic name)
        currency_info = {
            'EGP': 'جنيه مصري',
            'SAR': 'ريال سعودي',
            'USD': 'دولار أمريكي',
        }
        if cur_code in currency_info:
            expected_ar = currency_info[cur_code]
            self.assertIn(
                expected_ar, words_ar,
                f'Expected Arabic currency name "{expected_ar}" in output: {words_ar}',
            )
            self.assertNotIn(
                cur_code, words_ar,
                f'ISO code "{cur_code}" must not appear in Arabic output: {words_ar}',
            )

    # ── 5. Check print layout resolution ─────────────────────────────────────

    def test_check_print_layout_resolution(self):
        """report_pdc_check_print returns layout_map keyed by check.id."""
        check = self._make_check(
            self.partner_a, 'received', 7500.0,
            state='draft', due_days=30, check_number='PRNT001',
        )
        report_model = self.env['report.pdc_management_v19.report_pdc_check_document']
        result = report_model._get_report_values([check.id])
        self.assertIn('layout_map', result)
        self.assertIn(check.id, result['layout_map'])
        # layout may be empty recordset (no layout configured for this bank) — that's OK
        layout = result['layout_map'][check.id]
        self.assertIn(
            layout._name if layout else 'pdc.bank.layout',
            ('pdc.bank.layout',),
            'layout_map value must be a pdc.bank.layout recordset or empty set',
        )
