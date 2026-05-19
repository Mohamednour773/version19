# -*- coding: utf-8 -*-
from odoo import models, fields, tools


class FactoryWasteReport(models.Model):
    """Waste Analysis Report | تقرير تحليل الهالك"""
    _name = 'factory.waste.report'
    _description = 'Waste Analysis Report | تقرير تحليل الهالك'
    _auto = False
    _rec_name = 'production_id'
    _order = 'waste_percent desc'

    production_id = fields.Many2one('factory.production', string='Production | الإنتاج', readonly=True)
    project_id = fields.Many2one('project.project', readonly=True)
    sector_id = fields.Many2one('factory.sector', readonly=True)
    product_id = fields.Many2one('product.product', readonly=True)
    mix_id = fields.Many2one('factory.mix', readonly=True)
    date_planned = fields.Datetime(readonly=True)
    state = fields.Char(readonly=True)
    
    quantity_planned = fields.Float(readonly=True)
    quantity_produced = fields.Float(readonly=True)
    quantity_waste = fields.Float(readonly=True)
    waste_percent = fields.Float(readonly=True, digits=(5, 2))
    
    company_id = fields.Many2one('res.company', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    p.id AS id,
                    p.id AS production_id,
                    p.project_id AS project_id,
                    p.sector_id AS sector_id,
                    p.product_id AS product_id,
                    p.mix_id AS mix_id,
                    p.date_planned AS date_planned,
                    p.state AS state,
                    p.quantity_planned AS quantity_planned,
                    p.quantity_produced AS quantity_produced,
                    p.quantity_waste AS quantity_waste,
                    CASE
                        WHEN (p.quantity_produced + p.quantity_waste) > 0
                        THEN (p.quantity_waste / (p.quantity_produced + p.quantity_waste)) * 100.0
                        ELSE 0.0
                    END AS waste_percent,
                    p.company_id AS company_id
                FROM factory_production p
                WHERE p.state = 'done'
            )
        """ % self._table)
