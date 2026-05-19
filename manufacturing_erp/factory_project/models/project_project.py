# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class ProjectProject(models.Model):
    _inherit = 'project.project'

    is_factory_project = fields.Boolean(string='Factory Project | مشروع مصنع', default=False)
    estimation_id = fields.Many2one('factory.estimation', string='Source Estimation | المقايسة المصدر', readonly=True)
    
    sector_ids = fields.One2many('factory.sector', 'project_id', string='Sectors | القطاعات')
    sector_count = fields.Integer(compute='_compute_sector_count', string='Sector Count | عدد القطاعات')
    
    # Cost summaries from sectors
    total_planned_value = fields.Monetary(
        string='Total Planned Value | إجمالي القيمة المخططة',
        compute='_compute_project_totals', store=True, currency_field='currency_id')
    total_produced_value = fields.Monetary(
        string='Total Produced Value | قيمة المنتج',
        compute='_compute_project_totals', store=True, currency_field='currency_id')
    total_delivered_value = fields.Monetary(
        string='Total Delivered Value | قيمة الموَرَّد',
        compute='_compute_project_totals', store=True, currency_field='currency_id')
    progress_percent = fields.Float(
        string='Progress % | نسبة الإنجاز',
        compute='_compute_project_totals', store=True, digits=(5, 2))
    
    currency_id = fields.Many2one(related='company_id.currency_id', store=True, readonly=True)

    def _compute_sector_count(self):
        for rec in self:
            rec.sector_count = len(rec.sector_ids)

    @api.depends('sector_ids', 'sector_ids.planned_quantity', 'sector_ids.produced_quantity',
                 'sector_ids.delivered_quantity', 'sector_ids.unit_price', 'sector_ids.total_value')
    def _compute_project_totals(self):
        for rec in self:
            total_planned = sum(rec.sector_ids.mapped('total_value'))
            total_produced = sum(s.produced_quantity * s.unit_price for s in rec.sector_ids)
            total_delivered = sum(s.delivered_quantity * s.unit_price for s in rec.sector_ids)
            rec.total_planned_value = total_planned
            rec.total_produced_value = total_produced
            rec.total_delivered_value = total_delivered
            rec.progress_percent = (total_delivered / total_planned * 100.0) if total_planned else 0.0

    def action_view_sectors(self):
        self.ensure_one()
        return {
            'name': _('Sectors | القطاعات'),
            'type': 'ir.actions.act_window',
            'res_model': 'factory.sector',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }
