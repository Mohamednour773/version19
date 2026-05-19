# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class FactorySector(models.Model):
    _inherit = 'factory.sector'

    production_ids = fields.One2many('factory.production', 'sector_id', string='Production Orders | أوامر الإنتاج')
    production_count = fields.Integer(compute='_compute_production_count', string='Production Count')

    def _compute_production_count(self):
        for rec in self:
            rec.production_count = len(rec.production_ids)

    @api.depends('production_ids.state', 'production_ids.quantity_produced')
    def _compute_quantities(self):
        """Override to compute produced quantity from production orders."""
        super()._compute_quantities()
        for rec in self:
            done = rec.production_ids.filtered(lambda p: p.state == 'done')
            rec.produced_quantity = sum(done.mapped('quantity_produced'))

    def action_view_productions(self):
        self.ensure_one()
        return {
            'name': _('Production Orders | أوامر الإنتاج'),
            'type': 'ir.actions.act_window',
            'res_model': 'factory.production',
            'view_mode': 'list,form',
            'domain': [('sector_id', '=', self.id)],
            'context': {
                'default_sector_id': self.id,
                'default_project_id': self.project_id.id,
                'default_product_id': self.product_id.id,
            },
        }

    def action_create_production(self):
        self.ensure_one()
        return {
            'name': _('Create Production | إنشاء أمر إنتاج'),
            'type': 'ir.actions.act_window',
            'res_model': 'factory.production',
            'view_mode': 'form',
            'context': {
                'default_sector_id': self.id,
                'default_project_id': self.project_id.id,
                'default_product_id': self.product_id.id,
                'default_mix_id': self.mix_id.id if self.mix_id else False,
                'default_quantity_planned': self.remaining_to_produce,
            },
        }
