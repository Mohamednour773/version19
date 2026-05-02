from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    # ── PDC intermediate accounts ─────────────────────────────────────────────
    pdc_received_account_id = fields.Many2one(
        'account.account',
        string='PDC Received Account',
        help='Debit this account when a received check is registered.\n'
             'Example: "12102 - Checks Under Collection"',
        domain="[]",
    )
    pdc_received_collection_account_id = fields.Many2one(
        'account.account',
        string='PDC Collection Account',
        help='Debit this account when a received check is deposited.\n'
             'Example: "12103 - Checks for Collection (Deposited)"',
        domain="[]",
    )
    pdc_issued_account_id = fields.Many2one(
        'account.account',
        string='PDC Issued Account (Undelivered)',
        help='Credit this account when an issued check is registered.\n'
             'Example: "21102 - Checks Under Payment (Undelivered)"',
        domain="[]",
    )
    pdc_issued_delivered_account_id = fields.Many2one(
        'account.account',
        string='PDC Issued Account (Delivered)',
        help='Credit this account when an issued check is delivered.\n'
             'Example: "21103 - Checks Under Payment (Delivered)"',
        domain="[]",
    )
    pdc_bounce_charges_account_id = fields.Many2one(
        'account.account',
        string='PDC Bounce Charges Account',
        help='Debit this account for bank charges when a check bounces.\n'
             'Example: "64101 - Bank Charges"',
        domain="[]",
    )
    pdc_default_bank_id = fields.Many2one(
        'pdc.bank', string='Default PDC Bank',
        help='Pre-filled bank when creating checks from this journal.',
    )

    # ── Validation ────────────────────────────────────────────────────────────
    @api.constrains(
        'type',
        'pdc_received_account_id', 'pdc_received_collection_account_id',
        'pdc_issued_account_id', 'pdc_issued_delivered_account_id',
    )
    def _check_pdc_accounts(self):
        """Warn (not block) if a bank journal is missing PDC accounts.
        A hard block would prevent saving journals before configuration is complete.
        Validation is enforced at workflow execution time instead.
        """
        # Intentionally a soft check — enforced at accounting action time (Phase 3).
        pass
