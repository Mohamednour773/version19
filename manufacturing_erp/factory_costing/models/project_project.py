# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class ProjectProject(models.Model):
    _inherit = 'project.project'

    # Estimated (from estimation) | المتوقع
    estimated_cost = fields.Monetary(
        related='estimation_id.total_cost', store=True, string='Estimated Cost | التكلفة المتوقعة')
    estimated_revenue = fields.Monetary(
        related='estimation_id.total_amount', store=True, string='Estimated Revenue | الإيراد المتوقع')
    estimated_margin = fields.Monetary(
        related='estimation_id.margin_amount', store=True, string='Estimated Margin | الهامش المتوقع')
    
    # Actual costs aggregated across modules | التكاليف الفعلية المجمعة
    actual_cost_materials = fields.Monetary(
        string='Actual Materials | الخامات الفعلية',
        compute='_compute_actual_costs', store=True, currency_field='currency_id')
    actual_cost_molds = fields.Monetary(
        string='Actual Molds | القوالب الفعلية',
        compute='_compute_actual_costs', store=True, currency_field='currency_id')
    actual_cost_labor = fields.Monetary(
        string='Actual Labor | العمالة الفعلية',
        compute='_compute_actual_costs', store=True, currency_field='currency_id')
    actual_cost_installation = fields.Monetary(
        string='Actual Installation | التركيب الفعلي',
        compute='_compute_actual_costs', store=True, currency_field='currency_id')
    actual_cost_expenses = fields.Monetary(
        string='Actual Site Expenses | مصاريف الموقع الفعلية',
        compute='_compute_actual_costs', store=True, currency_field='currency_id')
    actual_cost_total = fields.Monetary(
        string='Actual Total Cost | إجمالي التكلفة الفعلية',
        compute='_compute_actual_costs', store=True, currency_field='currency_id')
    
    # Revenue (from invoices via SO) | الإيراد
    actual_revenue = fields.Monetary(
        string='Actual Revenue | الإيراد الفعلي',
        compute='_compute_actual_revenue', store=True, currency_field='currency_id')
    
    # Profitability | الربحية
    actual_margin = fields.Monetary(
        string='Actual Margin | الهامش الفعلي',
        compute='_compute_profitability', store=True, currency_field='currency_id')
    actual_margin_percent = fields.Float(
        string='Margin % | نسبة الهامش',
        compute='_compute_profitability', store=True, digits=(5, 2))
    
    # Variances vs estimation | الفروقات
    cost_variance = fields.Monetary(
        string='Cost Variance | فرق التكلفة',
        compute='_compute_profitability', store=True, currency_field='currency_id',
        help='Actual cost minus estimated cost | التكلفة الفعلية ناقص المتوقعة')
    cost_variance_percent = fields.Float(
        string='Cost Variance % | نسبة فرق التكلفة',
        compute='_compute_profitability', store=True, digits=(5, 2))

    @api.depends('sector_ids', 'sector_ids.production_ids.state', 'sector_ids.production_ids.cost_materials',
                 'sector_ids.production_ids.cost_molds', 'sector_ids.production_ids.cost_labor',
                 'sector_ids.installation_ids.state', 'sector_ids.installation_ids.total_cost',
                 'sector_ids.installation_ids.accessory_cost', 'sector_ids.installation_ids.finishing_cost',
                 'sector_ids.installation_ids.labor_cost', 'sector_ids.installation_ids.expenses_cost')
    def _compute_actual_costs(self):
        for rec in self:
            productions = rec.sector_ids.mapped('production_ids').filtered(lambda p: p.state == 'done')
            installations = rec.sector_ids.mapped('installation_ids').filtered(lambda i: i.state == 'done')
            
            rec.actual_cost_materials = (
                sum(productions.mapped('cost_materials')) +
                sum(installations.mapped('accessory_cost')) +
                sum(installations.mapped('finishing_cost'))
            )
            rec.actual_cost_molds = sum(productions.mapped('cost_molds'))
            rec.actual_cost_labor = (
                sum(productions.mapped('cost_labor')) +
                sum(installations.mapped('labor_cost'))
            )
            rec.actual_cost_installation = sum(installations.mapped('accessory_cost')) + sum(installations.mapped('finishing_cost'))
            rec.actual_cost_expenses = sum(installations.mapped('expenses_cost'))
            
            rec.actual_cost_total = (
                rec.actual_cost_materials +
                rec.actual_cost_molds +
                rec.actual_cost_labor +
                rec.actual_cost_expenses
            )

    @api.depends('analytic_account_id')
    def _compute_actual_revenue(self):
        """Pull confirmed invoice lines tied to this project's analytic account."""
        for rec in self:
            if not rec.analytic_account_id:
                rec.actual_revenue = 0.0
                continue
            # Use analytic lines on invoices as a proxy for revenue
            AAL = self.env['account.analytic.line']
            lines = AAL.search([
                ('auto_account_id', '=', rec.analytic_account_id.id),
                ('amount', '>', 0),  # positive amounts on invoices
            ])
            # Sum amounts originating from posted invoices
            total = 0.0
            for ln in lines:
                if ln.move_line_id and ln.move_line_id.move_id.state == 'posted':
                    if ln.move_line_id.move_id.move_type in ('out_invoice', 'out_refund'):
                        total += ln.amount
            rec.actual_revenue = total

    @api.depends('actual_revenue', 'actual_cost_total', 'estimated_cost')
    def _compute_profitability(self):
        for rec in self:
            rec.actual_margin = rec.actual_revenue - rec.actual_cost_total
            rec.actual_margin_percent = (rec.actual_margin / rec.actual_revenue * 100.0) if rec.actual_revenue else 0.0
            rec.cost_variance = rec.actual_cost_total - rec.estimated_cost
            rec.cost_variance_percent = (rec.cost_variance / rec.estimated_cost * 100.0) if rec.estimated_cost else 0.0

    def action_view_profitability(self):
        self.ensure_one()
        return {
            'name': _('Profitability | الربحية'),
            'type': 'ir.actions.act_window',
            'res_model': 'project.project',
            'res_id': self.id,
            'view_mode': 'form',
            'context': {'show_profitability_tab': 1},
        }

    def action_view_analytic_lines(self):
        self.ensure_one()
        return {
            'name': _('Analytic Lines | السطور التحليلية'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.analytic.line',
            'view_mode': 'list,form',
            'domain': [('auto_account_id', '=', self.analytic_account_id.id)] if self.analytic_account_id else [('id','=',0)],
        }
