# -*- coding: utf-8 -*-
from odoo import models, fields, tools


class FactoryProfitabilityReport(models.Model):
    """
    Project Profitability Report | تقرير ربحية المشروع
    
    A SQL view aggregating profitability per project for fast filtering,
    grouping, and pivot analysis. Read-only model.
    
    عرض SQL يجمع الربحية لكل مشروع للتصفية والتجميع والتحليل السريع.
    موديل للقراءة فقط.
    """
    _name = 'factory.profitability.report'
    _description = 'Project Profitability Report | تقرير ربحية المشروع'
    _auto = False
    _rec_name = 'project_id'
    _order = 'actual_margin desc'

    project_id = fields.Many2one('project.project', string='Project | المشروع', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Customer | العميل', readonly=True)
    user_id = fields.Many2one('res.users', string='Manager | المدير', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    currency_id = fields.Many2one('res.currency', readonly=True)
    date_start = fields.Date(readonly=True)
    
    estimated_revenue = fields.Monetary(currency_field='currency_id', readonly=True)
    estimated_cost = fields.Monetary(currency_field='currency_id', readonly=True)
    estimated_margin = fields.Monetary(currency_field='currency_id', readonly=True)
    
    actual_revenue = fields.Monetary(currency_field='currency_id', readonly=True)
    actual_cost_total = fields.Monetary(currency_field='currency_id', readonly=True)
    actual_cost_materials = fields.Monetary(currency_field='currency_id', readonly=True)
    actual_cost_molds = fields.Monetary(currency_field='currency_id', readonly=True)
    actual_cost_labor = fields.Monetary(currency_field='currency_id', readonly=True)
    actual_cost_installation = fields.Monetary(currency_field='currency_id', readonly=True)
    actual_margin = fields.Monetary(currency_field='currency_id', readonly=True)
    actual_margin_percent = fields.Float(readonly=True, digits=(5, 2))
    
    cost_variance = fields.Monetary(currency_field='currency_id', readonly=True)
    cost_variance_percent = fields.Float(readonly=True, digits=(5, 2))
    
    sector_count = fields.Integer(readonly=True)
    progress_percent = fields.Float(readonly=True, digits=(5, 2))

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    p.id AS id,
                    p.id AS project_id,
                    p.partner_id AS partner_id,
                    p.user_id AS user_id,
                    p.company_id AS company_id,
                    p.currency_id AS currency_id,
                    p.date_start AS date_start,
                    p.estimated_revenue AS estimated_revenue,
                    p.estimated_cost AS estimated_cost,
                    p.estimated_margin AS estimated_margin,
                    p.actual_revenue AS actual_revenue,
                    p.actual_cost_total AS actual_cost_total,
                    p.actual_cost_materials AS actual_cost_materials,
                    p.actual_cost_molds AS actual_cost_molds,
                    p.actual_cost_labor AS actual_cost_labor,
                    p.actual_cost_installation AS actual_cost_installation,
                    p.actual_margin AS actual_margin,
                    p.actual_margin_percent AS actual_margin_percent,
                    p.cost_variance AS cost_variance,
                    p.cost_variance_percent AS cost_variance_percent,
                    p.sector_count AS sector_count,
                    p.progress_percent AS progress_percent
                FROM project_project p
                WHERE p.is_factory_project = TRUE
                  AND p.active = TRUE
            )
        """ % self._table)
