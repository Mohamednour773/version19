# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError


class ClubSessionTrainerLine(models.Model):
    """
    Supports multiple trainers per session with individual commission rates.
    One trainer is marked as primary; others are assistants or substitutes.
    """
    _name = 'club.session.trainer.line'
    _description = 'Session Trainer Line'
    _order = 'is_primary desc, trainer_id'

    session_id = fields.Many2one(
        'club.session',
        string='Session',
        required=True,
        ondelete='cascade',
        index=True,
    )
    trainer_id = fields.Many2one(
        'club.trainer',
        string='Trainer',
        required=True,
        ondelete='restrict',
    )
    branch_id = fields.Many2one(
        related='session_id.branch_id',
        string='Branch',
        store=True,
    )

    # Role
    is_primary = fields.Boolean(string='Primary Trainer', default=False)
    is_substitute = fields.Boolean(string='Substitute', default=False)
    role_note = fields.Char(string='Role Note', help='e.g. "Replaced Ahmed for this session"')

    # Commission
    commission_pct = fields.Float(
        string='Commission %',
        digits=(5, 2),
        help='Leave 0 to inherit from trainer profile.',
    )
    commission_override = fields.Boolean(
        string='Override Commission',
        default=False,
        help='If checked, use the Commission % above instead of trainer default.',
    )
    effective_commission_pct = fields.Float(
        string='Effective Commission %',
        compute='_compute_effective_commission',
        store=True,
        digits=(5, 2),
    )

    # Attendance share (auto-calculated)
    attended_share = fields.Integer(
        string='Attended (Share)',
        help='Number of attendees attributed to this trainer.',
    )
    revenue_share = fields.Float(
        string='Revenue Share',
        digits=(16, 2),
        help='Revenue portion attributed to this trainer.',
    )
    commission_amount = fields.Float(
        string='Commission Amount',
        compute='_compute_commission_amount',
        store=True,
        digits=(16, 2),
    )

    commission_id = fields.Many2one(
        'club.trainer.commission',
        string='Commission Record',
        copy=False,
    )

    _sql_constraints = [
        ('session_trainer_unique', 'UNIQUE(session_id, trainer_id)',
         'A trainer can only appear once per session.'),
    ]

    @api.depends('commission_override', 'commission_pct', 'trainer_id.commission_pct')
    def _compute_effective_commission(self):
        for line in self:
            if line.commission_override:
                line.effective_commission_pct = line.commission_pct
            else:
                line.effective_commission_pct = line.trainer_id.commission_pct

    @api.depends('revenue_share', 'effective_commission_pct')
    def _compute_commission_amount(self):
        for line in self:
            line.commission_amount = line.revenue_share * line.effective_commission_pct / 100.0

    @api.onchange('trainer_id')
    def _onchange_trainer(self):
        if self.trainer_id and not self.commission_override:
            self.commission_pct = self.trainer_id.commission_pct

    @api.constrains('is_primary', 'session_id')
    def _check_one_primary(self):
        for line in self:
            if line.is_primary:
                others = self.search([
                    ('session_id', '=', line.session_id.id),
                    ('is_primary', '=', True),
                    ('id', '!=', line.id),
                ])
                if others:
                    raise ValidationError(
                        'Only one primary trainer is allowed per session. '
                        f'"{others[0].trainer_id.name}" is already set as primary.'
                    )

    @api.constrains('trainer_id', 'session_id')
    def _check_trainer_availability(self):
        """Prevent double-booking a trainer across sessions at same time."""
        for line in self:
            session = line.session_id
            if not session.date:
                continue
            conflict = self.env['club.session.trainer.line'].search([
                ('id', '!=', line.id),
                ('trainer_id', '=', line.trainer_id.id),
                ('session_id.date', '=', session.date),
                ('session_id.state', 'not in', ('cancelled',)),
                ('session_id.time_start', '<', session.time_end),
                ('session_id.time_end', '>', session.time_start),
            ])
            if conflict:
                raise ValidationError(
                    f'Trainer "{line.trainer_id.name}" is already assigned to '
                    f'session "{conflict[0].session_id.name}" at this time.'
                )

    def action_generate_commission(self):
        """Generate/update commission record for this trainer line."""
        self.ensure_one()
        if not self.revenue_share:
            raise UserError('Revenue share must be set before generating commission.')

        if self.commission_id:
            # Update existing
            self.commission_id.write({
                'session_revenue': self.revenue_share,
                'commission_pct': self.effective_commission_pct,
                'attended_count': self.attended_share,
            })
        else:
            comm = self.env['club.trainer.commission'].create({
                'trainer_id': self.trainer_id.id,
                'session_id': self.session_id.id,
                'date': self.session_id.date,
                'attended_count': self.attended_share,
                'session_revenue': self.revenue_share,
                'commission_pct': self.effective_commission_pct,
            })
            self.commission_id = comm
        return self.commission_id
