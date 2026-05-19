# -*- coding: utf-8 -*-
from odoo import models, fields, api


class FactorySector(models.Model):
    _inherit = 'factory.sector'

    mix_id = fields.Many2one(
        'factory.mix',
        string='Mix Design | تصميم الخلطة',
        domain="[('state','=','approved'),('product_id','=',product_id)]",
        tracking=True,
        help='Default mix design used for this sector | تصميم الخلطة الافتراضي لهذا القطاع',
    )
    mix_cost_per_unit = fields.Monetary(
        related='mix_id.cost_per_unit',
        string='Mix Cost / Unit | تكلفة الخلطة للوحدة',
        currency_field='currency_id',
        readonly=True,
    )
    total_mix_cost = fields.Monetary(
        string='Total Mix Cost | إجمالي تكلفة الخلطة',
        compute='_compute_total_mix_cost',
        store=True,
        currency_field='currency_id',
    )

    @api.depends('mix_id.cost_per_unit', 'produced_quantity')
    def _compute_total_mix_cost(self):
        for rec in self:
            rec.total_mix_cost = (rec.mix_id.cost_per_unit if rec.mix_id else 0.0) * rec.produced_quantity
