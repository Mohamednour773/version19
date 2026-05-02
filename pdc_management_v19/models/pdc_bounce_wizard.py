from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PDCBounceWizard(models.TransientModel):
    """Wizard: record a bounced check (the most complex Phase 5 wizard).

    Supports both received (from under_collection) and issued (from delivered)
    check types in a single batch.  Respects the three-way bounce_charges_source
    selection so accountants can choose which journal/account books the bank charges.
    """
    _name = 'pdc.bounce.wizard'
    _description = 'Record PDC Check Bounce'

    check_ids = fields.Many2many(
        'pdc.check', string='Checks',
        domain=[('state', 'in', ['under_collection', 'delivered'])],
        required=True,
    )
    bounce_date = fields.Date(
        string='Bounce Date',
        required=True,
        default=fields.Date.today,
        help='Date the bank notified the bounce.',
    )
    bounce_reason_id = fields.Many2one(
        'pdc.bounce.reason', string='Bounce Reason',
        help='Select the reason code returned by the bank.',
    )
    bounce_charges = fields.Float(
        string='Bank Charges',
        digits='Account',
        default=0.0,
        help='Bank charges deducted for this bounce, expressed in the check currency.\n'
             'Leave at 0.00 if the bank waived charges.',
    )
    bounce_charges_source = fields.Selection([
        ('deposit_journal', 'Deposit Bank Journal (Recommended)'),
        ('original_journal', 'Original Check Journal'),
        ('custom_account', 'Custom Account'),
    ], string='Charges Source',
        required=True,
        default='deposit_journal',
        help='Determines which journal / account is debited for the bank charges.\n'
             '• Deposit Bank Journal — recommended for received checks '
             '(charges raised by the collecting bank).\n'
             '• Original Check Journal — recommended for issued checks '
             '(charges raised by your own bank).\n'
             '• Custom Account — select a specific P&L expense account directly.',
    )
    bounce_charges_account_id = fields.Many2one(
        'account.account', string='Custom Charges Account',
        domain=[('account_type', '=', 'expense')],
        help='Required only when Charges Source is set to "Custom Account".',
    )
    bounce_notes = fields.Text(
        string='Bounce Notes',
        help='Internal notes about this bounce (steps taken, follow-up planned, etc.).',
    )
    check_auto_block = fields.Boolean(
        string='Auto-block Partner if Threshold Reached',
        default=True,
        help='When checked, each partner whose unsettled-bounce count reaches the '
             'configured threshold will be automatically blocked after recording '
             'this bounce.  Only effective when the company setting '
             '"Auto-block Partners" is enabled.  Uncheck to skip auto-blocking '
             'for this batch (e.g. when recording a historic bounce for a '
             'trusted partner).',
    )

    # ── Computed helpers ──────────────────────────────────────────────────────

    show_charges_account = fields.Boolean(
        compute='_compute_show_charges_account', store=False,
    )
    is_legal_action = fields.Boolean(
        compute='_compute_is_legal_action', store=False,
        string='Requires Legal Action',
    )
    check_count = fields.Integer(compute='_compute_check_count', store=False)

    @api.depends('bounce_charges_source')
    def _compute_show_charges_account(self):
        for wiz in self:
            wiz.show_charges_account = (wiz.bounce_charges_source == 'custom_account')

    @api.depends('bounce_reason_id')
    def _compute_is_legal_action(self):
        for wiz in self:
            wiz.is_legal_action = bool(
                wiz.bounce_reason_id and wiz.bounce_reason_id.is_legal_action
            )

    @api.depends('check_ids')
    def _compute_check_count(self):
        for wiz in self:
            wiz.check_count = len(wiz.check_ids)

    # ── Onchange ──────────────────────────────────────────────────────────────

    @api.onchange('check_ids')
    def _onchange_check_ids(self):
        """Default charges source to match the first check's type."""
        if self.check_ids:
            first = self.check_ids[0]
            if first.check_type in ('issued', 'guarantee_issued'):
                self.bounce_charges_source = 'original_journal'
            else:
                self.bounce_charges_source = 'deposit_journal'

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_ids = self._context.get('active_ids') or []
        active_model = self._context.get('active_model')
        if active_model == 'pdc.check' and active_ids and 'check_ids' in fields_list:
            res['check_ids'] = [(6, 0, active_ids)]
            # Adapt default charges source to the first check's type
            checks = self.env['pdc.check'].browse(active_ids)
            if checks and checks[0].check_type in ('issued', 'guarantee_issued'):
                res['bounce_charges_source'] = 'original_journal'
        # Default check_auto_block to True only when company has auto-block enabled
        if 'check_auto_block' in fields_list:
            res['check_auto_block'] = bool(
                self.env.company.pdc_auto_block_partners
            )
        return res

    # ── Validation ────────────────────────────────────────────────────────────

    def _validate(self):
        self.ensure_one()
        if not self.check_ids:
            raise UserError(_('Please select at least one check to bounce.'))
        if (self.bounce_charges > 0
                and self.bounce_charges_source == 'custom_account'
                and not self.bounce_charges_account_id):
            raise UserError(_(
                'Please specify a "Custom Charges Account" when '
                '"Charges Source" is set to "Custom Account".'
            ))

    # ── Action ────────────────────────────────────────────────────────────────

    def action_bounce(self):
        self.ensure_one()
        self._validate()

        errors = []
        succeeded_checks = self.env['pdc.check']
        for check in self.check_ids:
            try:
                check.write({
                    'bounce_date': self.bounce_date,
                    'bounce_reason_id': (
                        self.bounce_reason_id.id if self.bounce_reason_id else False
                    ),
                    'bounce_charges': self.bounce_charges,
                    'bounce_charges_source': self.bounce_charges_source,
                    'bounce_charges_account_id': (
                        self.bounce_charges_account_id.id
                        if self.bounce_charges_account_id else False
                    ),
                    'bounce_notes': self.bounce_notes or False,
                })
                check.action_bounce()
                succeeded_checks |= check
            except Exception as exc:
                errors.append(_('• %(name)s: %(err)s', name=check.name, err=str(exc)))

        if errors:
            raise UserError(_(
                'Some checks could not be bounced:\n%(errors)s',
                errors='\n'.join(errors),
            ))

        # D1 Option C: run partner auto-block check if user left the checkbox enabled
        if self.check_auto_block and succeeded_checks:
            succeeded_checks.mapped('partner_id')._check_auto_block()

        return {'type': 'ir.actions.act_window_close'}


# ── pdc.check extension ───────────────────────────────────────────────────────

class PDCCheckBounceAction(models.Model):
    """Adds action_open_bounce_wizard() to pdc.check."""
    _inherit = 'pdc.check'

    def action_open_bounce_wizard(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Record Bounce'),
            'res_model': 'pdc.bounce.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_check_ids': [(6, 0, self.ids)],
                'active_ids': self.ids,
                'active_model': 'pdc.check',
            },
        }
