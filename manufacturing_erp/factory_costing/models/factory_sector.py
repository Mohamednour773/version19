# -*- coding: utf-8 -*-
from odoo import models, fields, api


class FactorySector(models.Model):
    _inherit = 'factory.sector'

    actual_cost_materials = fields.Monetary(
        string='Actual Materials Cost | تكلفة الخامات الفعلية',
        compute='_compute_sector_costs', store=True, currency_field='currency_id')
    actual_cost_molds = fields.Monetary(
        string='Actual Molds Cost | تكلفة القوالب الفعلية',
        compute='_compute_sector_costs', store=True, currency_field='currency_id')
    actual_cost_labor = fields.Monetary(
        string='Actual Labor Cost | تكلفة العمالة الفعلية',
        compute='_compute_sector_costs', store=True, currency_field='currency_id')
    actual_cost_installation = fields.Monetary(
        string='Actual Installation | تكلفة التركيب الفعلية',
        compute='_compute_sector_costs', store=True, currency_field='currency_id')
    actual_cost_total = fields.Monetary(
        string='Actual Total | إجمالي التكلفة الفعلية',
        compute='_compute_sector_costs', store=True, currency_field='currency_id')
    actual_cost_per_unit = fields.Monetary(
        string='Actual Cost per Unit | التكلفة الفعلية للوحدة',
        compute='_compute_sector_costs', store=True, currency_field='currency_id')
    
    actual_margin = fields.Monetary(
        string='Actual Margin | الهامش الفعلي',
        compute='_compute_sector_costs', store=True, currency_field='currency_id')
    actual_margin_percent = fields.Float(
        string='Margin % | نسبة الهامش',
        compute='_compute_sector_costs', store=True, digits=(5, 2))

    @api.depends('production_ids.state', 'production_ids.cost_materials',
                 'production_ids.cost_molds', 'production_ids.cost_labor',
                 'installation_ids.state', 'installation_ids.total_cost',
                 'produced_quantity', 'total_value')
    def _compute_sector_costs(self):
        for rec in self:
            prods = rec.production_ids.filtered(lambda p: p.state == 'done')
            insts = rec.installation_ids.filtered(lambda i: i.state == 'done')
            
            rec.actual_cost_materials = sum(prods.mapped('cost_materials'))
            rec.actual_cost_molds = sum(prods.mapped('cost_molds'))
            rec.actual_cost_labor = sum(prods.mapped('cost_labor')) + sum(insts.mapped('labor_cost'))
            rec.actual_cost_installation = sum(insts.mapped('total_cost'))
            rec.actual_cost_total = rec.actual_cost_materials + rec.actual_cost_molds + rec.actual_cost_labor + rec.actual_cost_installation
            rec.actual_cost_per_unit = (rec.actual_cost_total / rec.produced_quantity) if rec.produced_quantity else 0.0
            
            rec.actual_margin = rec.total_value - rec.actual_cost_total
            rec.actual_margin_percent = (rec.actual_margin / rec.total_value * 100.0) if rec.total_value else 0.0
