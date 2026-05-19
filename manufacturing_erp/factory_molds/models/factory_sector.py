# -*- coding: utf-8 -*-
from odoo import models, fields, api


class FactorySector(models.Model):
    _inherit = 'factory.sector'

    mold_ids = fields.Many2many(
        'factory.mold',
        'mold_sector_rel',
        'sector_id',
        'mold_id',
        string='Molds | القوالب',
    )
    mold_count = fields.Integer(compute='_compute_mold_stats', string='Mold Count | عدد القوالب')
    total_mold_cost = fields.Monetary(
        compute='_compute_mold_stats',
        string='Total Mold Cost | إجمالي تكلفة القوالب',
        currency_field='currency_id',
        help='Sum of (cost_per_unit × produced_qty) for all molds used | مجموع (تكلفة الوحدة × الكمية المنتجة) لكل القوالب',
    )

    @api.depends('mold_ids', 'produced_quantity')
    def _compute_mold_stats(self):
        for rec in self:
            rec.mold_count = len(rec.mold_ids)
            # Cost = sum of cost_per_unit of all linked molds × produced qty
            total = sum(rec.mold_ids.mapped('cost_per_unit')) * rec.produced_quantity
            rec.total_mold_cost = total

    def action_view_molds(self):
        self.ensure_one()
        return {
            'name': 'Molds | القوالب',
            'type': 'ir.actions.act_window',
            'res_model': 'factory.mold',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.mold_ids.ids)],
        }
