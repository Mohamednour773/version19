from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PosConfig(models.Model):
    _inherit = "pos.config"

    airport_currency_mode = fields.Boolean(
        string="Airport Multi-Currency Mode",
        help=(
            "Allow foreign-currency POS pricelists and record the actual tender currency "
            "while keeping POS accounting amounts in the POS currency."
        ),
    )
    airport_auto_payment_currency = fields.Boolean(
        string="Use Pricelist Currency for Payments",
        default=True,
        help=(
            "When the payment method has no fixed airport currency, new payment lines use "
            "the current order/pricelist currency."
        ),
    )
    airport_show_base_equivalent = fields.Boolean(
        string="Show AED Equivalent on Receipt",
        help="Print the POS/base currency equivalent as a secondary receipt line.",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_list = super()._load_pos_data_fields(config)
        if not fields_list:
            return fields_list
        return fields_list + [
            "airport_currency_mode",
            "airport_auto_payment_currency",
            "airport_show_base_equivalent",
        ]

    @api.constrains(
        "pricelist_id",
        "use_pricelist",
        "available_pricelist_ids",
        "journal_id",
        "invoice_journal_id",
        "payment_method_ids",
        "airport_currency_mode",
    )
    def _check_currencies(self):
        for config in self:
            if (
                config.use_pricelist
                and config.pricelist_id
                and config.pricelist_id not in config.available_pricelist_ids
            ):
                raise ValidationError(
                    _("The default pricelist must be included in the available pricelists.")
                )

            for payment_method in config.payment_method_ids:
                journal = payment_method.journal_id
                if not journal or not journal.currency_id or journal.currency_id == config.currency_id:
                    continue
                if not (
                    config.airport_currency_mode
                    and payment_method.airport_currency_id
                    and payment_method.airport_currency_id == journal.currency_id
                ):
                    raise ValidationError(
                        _(
                            "All payment methods must be in the same currency as the Sales Journal "
                            "or the company currency if that is not set. In airport mode, a foreign "
                            "payment method is allowed only when its Airport Currency matches its journal currency."
                        )
                    )

            if config.use_pricelist:
                foreign_pricelists = config.available_pricelist_ids.filtered(
                    lambda pricelist: pricelist.currency_id != config.currency_id
                )
                if foreign_pricelists and not config.airport_currency_mode:
                    raise ValidationError(
                        _(
                            "All available pricelists must be in the same currency as the company or "
                            "as the Sales Journal set on this point of sale if you use the Accounting application."
                        )
                    )

            if (
                config.invoice_journal_id.currency_id
                and config.invoice_journal_id.currency_id != config.currency_id
            ):
                raise ValidationError(
                    _(
                        "The invoice journal must be in the same currency as the Sales Journal or "
                        "the company currency if that is not set."
                    )
                )
