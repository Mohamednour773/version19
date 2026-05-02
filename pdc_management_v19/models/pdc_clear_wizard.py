from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PDCClearWizard(models.TransientModel):
    """Wizard: mark one or more under-collection checks as cleared.

    Sets clear_date on each check and calls action_clear().
    Shows a running total to confirm the batch amount before confirming.
    """
    _name = 'pdc.clear.wizard'
    _description = 'Clear PDC Checks'

    check_ids = fields.Many2many(
        'pdc.check', string='Checks',
        domain=[('state', '=', 'under_collection')],
        required=True,
    )
    clear_date = fields.Date(
        string='Clear Date',
        required=True,
        default=fields.Date.today,
        help='Date on which the bank confirmed payment of these checks.',
    )
    check_count = fields.Integer(compute='_compute_totals', store=False)
    total_amount = fields.Float(
        compute='_compute_totals', store=False, digits='Account',
        string='Total Amount',
    )
    currency_id = fields.Many2one(
        'res.currency', compute='_compute_totals', store=False,
    )
    multi_currency = fields.Boolean(
        compute='_compute_totals', store=False,
        help='True when the selected checks span more than one currency.',
    )

    @api.depends('check_ids')
    def _compute_totals(self):
        for wiz in self:
            checks = wiz.check_ids
            wiz.check_count = len(checks)
            currencies = checks.mapped('currency_id')
            wiz.multi_currency = len(currencies) > 1
            if len(currencies) == 1:
                wiz.currency_id = currencies[0]
                wiz.total_amount = sum(checks.mapped('amount'))
            else:
                wiz.currency_id = wiz.env.company.currency_id
                wiz.total_amount = 0.0

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_ids = self._context.get('active_ids') or []
        active_model = self._context.get('active_model')
        if active_model == 'pdc.check' and active_ids and 'check_ids' in fields_list:
            res['check_ids'] = [(6, 0, active_ids)]
        return res

    # ── Action ────────────────────────────────────────────────────────────────

    def action_clear(self):
        self.ensure_one()
        if not self.check_ids:
            raise UserError(_('Please select at least one check to clear.'))

        errors = []
        for check in self.check_ids:
            try:
                check.write({'clear_date': self.clear_date})
                check.action_clear()
            except Exception as exc:
                errors.append(_('• %(name)s: %(err)s', name=check.name, err=str(exc)))

        if errors:
            raise UserError(_(
                'Some checks could not be cleared:\n%(errors)s',
                errors='\n'.join(errors),
            ))
        return {'type': 'ir.actions.act_window_close'}


# ── pdc.check extension ───────────────────────────────────────────────────────

class PDCCheckClearAction(models.Model):
    """Adds action_open_clear_wizard() to pdc.check."""
    _inherit = 'pdc.check'

    def action_open_clear_wizard(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Clear Checks'),
            'res_model': 'pdc.clear.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_check_ids': [(6, 0, self.ids)],
                'active_ids': self.ids,
                'active_model': 'pdc.check',
            },
        }
