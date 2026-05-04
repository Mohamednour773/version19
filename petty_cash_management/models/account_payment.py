# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    petty_fund_id = fields.Many2one(
        'petty.cash.fund',
        string='Petty Cash Fund',
        tracking=True,
        domain="[('state', '=', 'active'), ('company_id', '=', company_id)]",
        help='If this payment is made from a petty cash fund, link it here.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.petty_fund_id:
                record.petty_fund_id._check_balance_warning(record.amount)
        return records

    def action_post(self):
        for payment in self:
            if payment.petty_fund_id and payment.petty_fund_id.state != 'active':
                raise UserError(_(
                    'Cannot post payment: Petty Cash Fund "%s" is not active.',
                    payment.petty_fund_id.name,
                ))
        return super().action_post()
