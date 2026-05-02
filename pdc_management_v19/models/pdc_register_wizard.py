from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PDCRegisterWizard(models.TransientModel):
    """Wizard: register one or more draft PDC checks.

    Supports batch registration and optional linking to open invoices.
    Accessible via the "Register" button on pdc.check form / list, or
    from the Actions menu in list view.
    """
    _name = 'pdc.register.wizard'
    _description = 'Register PDC Checks'

    check_ids = fields.Many2many(
        'pdc.check', string='Checks',
        domain=[('state', '=', 'draft')],
        required=True,
    )
    invoice_ids = fields.Many2many(
        'account.move', string='Link Invoices',
        domain=[
            ('move_type', 'in', ['out_invoice', 'in_invoice', 'out_refund', 'in_refund']),
            ('payment_state', '!=', 'paid'),
        ],
        help='Optionally link one or more open invoices to all selected checks.',
    )
    notes = fields.Text(
        string='Notes',
        help='Optional notes posted to the chatter of each registered check.',
    )
    check_count = fields.Integer(
        compute='_compute_check_count', store=False,
    )

    @api.depends('check_ids')
    def _compute_check_count(self):
        for wiz in self:
            wiz.check_count = len(wiz.check_ids)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_ids = self._context.get('active_ids') or []
        active_model = self._context.get('active_model')
        if active_model == 'pdc.check' and active_ids and 'check_ids' in fields_list:
            res['check_ids'] = [(6, 0, active_ids)]
        return res

    # ── Action ────────────────────────────────────────────────────────────────

    def action_register(self):
        self.ensure_one()
        if not self.check_ids:
            raise UserError(_('Please select at least one check to register.'))

        errors = []
        registered = self.env['pdc.check']
        for check in self.check_ids:
            try:
                check.action_register()
                registered |= check
            except Exception as exc:
                errors.append(_('• %(name)s: %(err)s', name=check.name, err=str(exc)))

        # Link invoices to successfully registered checks
        if self.invoice_ids and registered:
            registered.write({
                'invoice_ids': [(4, inv.id) for inv in self.invoice_ids],
            })

        # Post registration notes to chatter
        if self.notes and registered:
            for check in registered:
                check.message_post(body=_('Registration note: %s', self.notes))

        if errors:
            raise UserError(_(
                '%(n)d check(s) registered. The following had errors:\n%(errors)s',
                n=len(registered),
                errors='\n'.join(errors),
            ))
        return {'type': 'ir.actions.act_window_close'}


# ── pdc.check extension ───────────────────────────────────────────────────────

class PDCCheckRegisterAction(models.Model):
    """Adds action_open_register_wizard() to pdc.check."""
    _inherit = 'pdc.check'

    def action_open_register_wizard(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Register Checks'),
            'res_model': 'pdc.register.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_check_ids': [(6, 0, self.ids)],
                'active_ids': self.ids,
                'active_model': 'pdc.check',
            },
        }
