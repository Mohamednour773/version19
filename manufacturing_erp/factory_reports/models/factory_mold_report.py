# -*- coding: utf-8 -*-
from odoo import models, fields, tools


class FactoryMoldReport(models.Model):
    """Mold Utilization Report | تقرير استخدام القوالب"""
    _name = 'factory.mold.report'
    _description = 'Mold Utilization Report | تقرير استخدام القوالب'
    _auto = False
    _rec_name = 'mold_id'
    _order = 'usage_percent desc'

    mold_id = fields.Many2one('factory.mold', string='Mold | القالب', readonly=True)
    category_id = fields.Many2one('factory.mold.category', string='Category | الفئة', readonly=True)
    mold_type = fields.Char(readonly=True)
    state = fields.Char(readonly=True)
    
    manufacturing_cost = fields.Monetary(currency_field='currency_id', readonly=True)
    expected_uses = fields.Integer(readonly=True)
    actual_uses = fields.Integer(readonly=True)
    remaining_uses = fields.Integer(readonly=True)
    usage_percent = fields.Float(readonly=True, digits=(5, 2))
    cost_per_unit = fields.Monetary(currency_field='currency_id', readonly=True)
    cost_consumed = fields.Monetary(currency_field='currency_id', readonly=True)
    cost_remaining = fields.Monetary(currency_field='currency_id', readonly=True)
    
    currency_id = fields.Many2one('res.currency', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    m.id AS id,
                    m.id AS mold_id,
                    m.category_id AS category_id,
                    m.mold_type AS mold_type,
                    m.state AS state,
                    m.manufacturing_cost AS manufacturing_cost,
                    m.expected_uses AS expected_uses,
                    m.actual_uses AS actual_uses,
                    m.remaining_uses AS remaining_uses,
                    m.usage_percent AS usage_percent,
                    m.cost_per_unit AS cost_per_unit,
                    m.cost_consumed AS cost_consumed,
                    m.cost_remaining AS cost_remaining,
                    m.currency_id AS currency_id,
                    m.company_id AS company_id
                FROM factory_mold m
                WHERE m.active = TRUE
            )
        """ % self._table)
