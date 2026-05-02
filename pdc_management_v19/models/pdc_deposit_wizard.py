from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PDCDepositWizard(models.TransientModel):
    """Wizard: deposit one or more registered received checks for collection.

    Sets the deposit journal and date on each check, then calls action_deposit().
    Supports batch with per-record error accumulation so a single failing check
    does not silently abort the rest.
    """
    _name = 'pdc.deposit.wizard'
    _description = 'Deposit PDC Checks for Collection'

    check_ids = fields.Many2many(
        'pdc.check', string='Checks',
        domain=[('check_type', '=', 'received'), ('state', '=', 'registered')],
        required=True,
    )
    deposit_journal_id = fields.Many2one(
        'account.journal', string='Deposit Bank',
        domain=[('type', '=', 'bank')],
        required=True,
        help='Bank journal through which these checks are submitted for collection.',
    )
    deposit_date = fields.Date(
        string='Deposit Date',
        required=True,
        default=fields.Date.today,
        help='Date the checks are physically deposited at the collecting bank.',
    )
    check_count = fields.Integer(compute='_compute_check_count', store=False)
    skipped_count = fields.Integer(
        compute='_compute_skipped_count', store=False,
        help='Number of selected checks that are not in the eligible state for deposit.',
    )

    @api.depends('check_ids')
    def _compute_check_count(self):
        for wiz in self:
            wiz.check_count = len(wiz.check_ids)

    @api.depends('check_ids')
    def _compute_skipped_count(self):
        for wiz in self:
            wiz.skipped_count = sum(
                1 for c in wiz.check_ids
                if c.state != 'registered' or c.check_type != 'received'
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

    def action_deposit(self):
        self.ensure_one()
        if not self.check_ids:
            raise UserError(_('Please select at least one check to deposit.'))

        errors = []
        for check in self.check_ids:
            try:
                check.write({
                    'deposit_journal_id': self.deposit_journal_id.id,
                    'deposit_date': self.deposit_date,
                })
                check.action_deposit()
            except Exception as exc:
                errors.append(_('• %(name)s: %(err)s', name=check.name, err=str(exc)))

        if errors:
            raise UserError(_(
                'Some checks could not be deposited:\n%(errors)s',
                errors='\n'.join(errors),
            ))
        return {'type': 'ir.actions.act_window_close'}


# ── pdc.check extension ───────────────────────────────────────────────────────

class PDCCheckDepositAction(models.Model):
    """Adds action_open_deposit_wizard() to pdc.check."""
    _inherit = 'pdc.check'

    def action_open_deposit_wizard(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Deposit Checks'),
            'res_model': 'pdc.deposit.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_check_ids': [(6, 0, self.ids)],
                'active_ids': self.ids,
                'active_model': 'pdc.check',
            },
        }
