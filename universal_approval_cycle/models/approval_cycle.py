# -*- coding: utf-8 -*-
"""
Approval Cycle Definition Model
Defines the approval workflow configuration for a specific Odoo model.
"""

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ApprovalCycle(models.Model):
    """
    Stores the definition of an approval cycle linked to any Odoo model.
    One model can have multiple cycles (e.g. for different record types).
    """
    _name = 'approval.cycle'
    _description = 'Approval Cycle Definition'
    _order = 'name'

    name = fields.Char(
        string='Cycle Name',
        required=True,
        translate=True,
        help='Descriptive name for this approval cycle',
    )
    active = fields.Boolean(
        string='Active',
        default=True,
    )
    model_id = fields.Many2one(
        comodel_name='ir.model',
        string='Target Model',
        required=True,
        ondelete='cascade',
        help='The Odoo model on which this approval cycle will be applied',
    )
    model_name = fields.Char(
        related='model_id.model',
        string='Model Technical Name',
        store=True,
        readonly=True,
    )
    stage_ids = fields.One2many(
        comodel_name='approval.stage',
        inverse_name='cycle_id',
        string='Approval Stages',
        copy=True,
    )
    stage_count = fields.Integer(
        string='Number of Stages',
        compute='_compute_stage_count',
    )
    description = fields.Text(
        string='Description',
        translate=True,
    )
    # Auto-trigger configuration
    auto_trigger = fields.Boolean(
        string='Auto-trigger on Create',
        default=False,
        help='Automatically start the approval cycle when a new record is created',
    )
    trigger_domain = fields.Char(
        string='Trigger Condition (Domain)',
        default='[]',
        help='Domain filter to determine which records trigger the approval cycle automatically. '
             'Leave as [] to apply to all records.',
    )
    # Completion behavior
    approve_field_id = fields.Many2one(
        comodel_name='ir.model.fields',
        string='Field to Update on Approval',
        domain="[('model_id', '=', model_id), ('ttype', 'in', ['selection', 'boolean', 'char'])]",
        help='Optional: field on the target model to update when approval is complete',
    )
    approve_field_value = fields.Char(
        string='Value on Full Approval',
        help='Value to write to the field when the cycle is fully approved',
    )
    reject_field_value = fields.Char(
        string='Value on Rejection',
        help='Value to write to the field when the cycle is rejected',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
    )

    # -------------------------------------------------------------------------
    # Computed
    # -------------------------------------------------------------------------

    @api.depends('stage_ids')
    def _compute_stage_count(self):
        for rec in self:
            rec.stage_count = len(rec.stage_ids)

    # -------------------------------------------------------------------------
    # Constraints
    # -------------------------------------------------------------------------

    @api.constrains('trigger_domain')
    def _check_trigger_domain(self):
        for rec in self:
            try:
                domain = eval(rec.trigger_domain or '[]')
                if not isinstance(domain, list):
                    raise ValidationError(_('Trigger condition must be a valid domain list.'))
            except Exception:
                raise ValidationError(_('Trigger condition must be a valid Odoo domain, e.g. []'))

    @api.constrains('stage_ids')
    def _check_stages(self):
        for rec in self:
            if rec.stage_ids:
                sequences = rec.stage_ids.mapped('sequence')
                if len(sequences) != len(set(sequences)):
                    raise ValidationError(_('Stage sequence numbers must be unique within a cycle.'))

    # -------------------------------------------------------------------------
    # Business Methods
    # -------------------------------------------------------------------------

    def action_view_stages(self):
        """Open the stages for this cycle."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Approval Stages'),
            'res_model': 'approval.stage',
            'view_mode': 'list,form',
            'domain': [('cycle_id', '=', self.id)],
            'context': {'default_cycle_id': self.id},
        }

    def get_first_stage(self):
        """Return the first (lowest sequence) stage of the cycle."""
        self.ensure_one()
        return self.stage_ids.sorted('sequence')[:1]

    def get_ordered_stages(self):
        """Return stages sorted by sequence."""
        self.ensure_one()
        return self.stage_ids.sorted('sequence')
