from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountJournal(models.Model):
    _inherit = "account.journal"

    is_custody_journal = fields.Boolean(
        string="Custody Journal",
        default=False,
        copy=False,
        help="Use this journal to pay vendor bills from employee custody balances.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Create journals and ensure custody payment methods have a liquidity account."""
        journals = super().create(vals_list)
        journals._ensure_custody_payment_accounts()
        return journals

    def write(self, vals):
        """Keep custody journal payment methods ready for payment posting."""
        result = super().write(vals)
        if {"is_custody_journal", "default_account_id", "type"} & set(vals):
            self._ensure_custody_payment_accounts()
        return result

    def _ensure_custody_payment_accounts(self):
        """Assign normal cash/bank liquidity accounts to custody journal payment methods."""
        for journal in self.filtered(lambda item: item.is_custody_journal and item.default_account_id):
            method_lines = journal.inbound_payment_method_line_ids | journal.outbound_payment_method_line_ids
            method_lines.filtered(lambda line: not line.payment_account_id).payment_account_id = journal.default_account_id

    @api.depends("name", "currency_id", "is_custody_journal")
    def _compute_display_name(self):
        """Append a custody suffix to custody payment journals."""
        super()._compute_display_name()
        for journal in self.filtered("is_custody_journal"):
            journal.display_name = _("%s (Custody)") % journal.display_name

    @api.constrains("is_custody_journal", "type", "company_id")
    def _check_custody_journal(self):
        """Validate that custody journals are bank/cash journals with configured custody accounts."""
        for journal in self:
            if not journal.is_custody_journal:
                continue
            if journal.type not in ("cash", "bank"):
                raise ValidationError(_("A custody journal must be a Cash or Bank journal."))
            if not journal.company_id.custody_receivable_account_id:
                raise ValidationError(_(
                    "Configure the Employee Custody Receivable account for %(company)s before enabling a custody "
                    "journal.",
                    company=journal.company_id.display_name,
                ))
