from odoo import api, fields, models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    pdc_check_id = fields.Many2one(
        'pdc.check', string='PDC Check',
        ondelete='set null', copy=False, index=True,
        help='The PDC check that generated or is linked to this payment.',
    )
    is_pdc = fields.Boolean(
        string='Is PDC Payment',
        compute='_compute_is_pdc', store=True,
        help='True when this payment is linked to a PDC check.',
    )

    @api.depends('pdc_check_id')
    def _compute_is_pdc(self):
        for payment in self:
            payment.is_pdc = bool(payment.pdc_check_id)
