from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PDCCancelWizard(models.TransientModel):
    """Wizard: cancel one or more PDC checks.

    Requires a written cancellation reason.  When any of the selected checks is
    in 'under_collection' state an extra confirmation checkbox is shown because
    cancelling that state reverses the deposit journal entry and the physical
    check must be recalled from the bank.
    """
    _name = 'pdc.cancel.wizard'
    _description = 'Cancel PDC Checks'

    check_ids = fields.Many2many(
        'pdc.check', string='Checks',
        required=True,
    )
    cancel_reason = fields.Text(
        string='Cancellation Reason',
        required=True,
        help='Reason for cancellation — posted to the chatter and operations log.',
    )

    # ── Risk-awareness flags ───────────────────────────────────────────────────
    has_under_collection = fields.Boolean(
        compute='_compute_risk_flags', store=False,
        help='True when at least one selected check is in "Under Collection" state.',
    )
    has_posted_entries = fields.Boolean(
        compute='_compute_risk_flags', store=False,
        help='True when at least one selected check has posted journal entries.',
    )
    confirm_under_collection = fields.Boolean(
        string='I confirm I have recalled the physical check(s) from the bank',
        default=False,
        help='Required when cancelling checks that are already deposited for collection. '
             'Cancellation will reverse the deposit journal entry.',
    )

    # ── Summary counters ──────────────────────────────────────────────────────
    check_count = fields.Integer(compute='_compute_risk_flags', store=False)
    entry_count = fields.Integer(compute='_compute_risk_flags', store=False)

    @api.depends('check_ids')
    def _compute_risk_flags(self):
        for wiz in self:
            checks = wiz.check_ids
            wiz.check_count = len(checks)
            wiz.has_under_collection = any(
                c.state == 'under_collection' for c in checks
            )
            wiz.has_posted_entries = any(
                any(m.state == 'posted' for m in c.move_ids) for c in checks
            )
            wiz.entry_count = sum(
                len(c.move_ids.filtered(lambda m: m.state == 'posted'))
                for c in checks
            )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_ids = self._context.get('active_ids') or []
        active_model = self._context.get('active_model')
        if active_model == 'pdc.check' and active_ids and 'check_ids' in fields_list:
            res['check_ids'] = [(6, 0, active_ids)]
        return res

    # ── Action ────────────────────────────────────────────────────────────────

    def action_cancel(self):
        self.ensure_one()
        if not self.check_ids:
            raise UserError(_('Please select at least one check to cancel.'))
        if not (self.cancel_reason or '').strip():
            raise UserError(_('Please provide a cancellation reason.'))
        if self.has_under_collection and not self.confirm_under_collection:
            raise UserError(_(
                'One or more checks are currently "Under Collection".\n'
                'Cancelling will reverse the deposit journal entry.\n'
                'Please confirm you have recalled the physical check(s) '
                'from the bank by ticking the confirmation checkbox.'
            ))

        errors = []
        for check in self.check_ids:
            try:
                # Post reason to chatter BEFORE cancelling (state change happens inside)
                check.message_post(
                    body=_('Cancellation reason: %s', self.cancel_reason)
                )
                check.action_cancel()
            except Exception as exc:
                errors.append(_('• %(name)s: %(err)s', name=check.name, err=str(exc)))

        if errors:
            raise UserError(_(
                'Some checks could not be cancelled:\n%(errors)s',
                errors='\n'.join(errors),
            ))
        return {'type': 'ir.actions.act_window_close'}


# ── pdc.check extension ───────────────────────────────────────────────────────

class PDCCheckCancelAction(models.Model):
    """Adds action_open_cancel_wizard() to pdc.check."""
    _inherit = 'pdc.check'

    def action_open_cancel_wizard(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cancel Checks'),
            'res_model': 'pdc.cancel.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_check_ids': [(6, 0, self.ids)],
                'active_ids': self.ids,
                'active_model': 'pdc.check',
            },
        }
