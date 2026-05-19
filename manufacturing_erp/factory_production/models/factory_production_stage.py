# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class FactoryProductionStage(models.Model):
    """
    Production Stage Line | سطر مرحلة الإنتاج
    
    Tracks one stage execution within a production order with:
    - Planned vs actual quantities
    - Waste tracked at this stage
    - Labor time and cost
    - Start/finish timestamps
    
    يتتبع تنفيذ مرحلة واحدة داخل أمر الإنتاج:
    - الكميات المخططة مقابل الفعلية
    - الهالك في هذه المرحلة
    - وقت وتكلفة العمالة
    - تواريخ البدء والانتهاء
    """
    _name = 'factory.production.stage'
    _description = 'Production Stage Line | سطر مرحلة إنتاج'
    _order = 'production_id, stage_sequence, id'

    production_id = fields.Many2one(
        'factory.production', string='Production | الإنتاج', required=True, ondelete='cascade')
    stage_id = fields.Many2one('factory.stage', string='Stage | المرحلة', required=True)
    stage_sequence = fields.Integer(related='stage_id.sequence', store=True)
    stage_type = fields.Selection(related='stage_id.stage_type', store=True)
    
    quantity_planned = fields.Float(string='Planned Qty | الكمية المخططة', digits='Product Unit of Measure')
    quantity_done = fields.Float(string='Done Qty | الكمية المنجزة', digits='Product Unit of Measure')
    quantity_waste = fields.Float(string='Waste Qty | الهالك', digits='Product Unit of Measure')
    waste_percent = fields.Float(
        string='Waste % | نسبة الهالك',
        compute='_compute_waste_percent', store=True, digits=(5, 2))
    
    date_start = fields.Datetime(string='Start | البدء')
    date_finished = fields.Datetime(string='Finish | الانتهاء')
    duration_hours = fields.Float(
        string='Duration (h) | المدة (ساعة)',
        compute='_compute_duration', store=True)
    
    # Labor | العمالة
    employee_ids = fields.Many2many(
        'hr.employee', 'production_stage_employee_rel', 'stage_id', 'employee_id',
        string='Employees | الموظفون')
    labor_hours = fields.Float(string='Labor Hours | ساعات العمالة')
    labor_rate = fields.Monetary(
        string='Labor Rate | السعر/الساعة', currency_field='currency_id')
    labor_cost = fields.Monetary(
        string='Labor Cost | تكلفة العمالة',
        compute='_compute_labor_cost', store=True, currency_field='currency_id')
    
    state = fields.Selection([
        ('pending', 'Pending | قيد الانتظار'),
        ('ready', 'Ready | جاهز'),
        ('in_progress', 'In Progress | قيد التنفيذ'),
        ('done', 'Done | منتهي'),
        ('cancelled', 'Cancelled | ملغي'),
    ], string='Status | الحالة', default='pending')
    
    quality_passed = fields.Boolean(string='Quality Passed | نجح الفحص')
    notes = fields.Text(string='Notes | ملاحظات')
    
    currency_id = fields.Many2one(related='production_id.currency_id', store=True)

    @api.depends('quantity_waste', 'quantity_done')
    def _compute_waste_percent(self):
        for rec in self:
            total = rec.quantity_done + rec.quantity_waste
            rec.waste_percent = (rec.quantity_waste / total * 100.0) if total else 0.0

    @api.depends('date_start', 'date_finished')
    def _compute_duration(self):
        for rec in self:
            if rec.date_start and rec.date_finished:
                delta = rec.date_finished - rec.date_start
                rec.duration_hours = delta.total_seconds() / 3600.0
            else:
                rec.duration_hours = 0.0

    @api.depends('labor_hours', 'labor_rate')
    def _compute_labor_cost(self):
        for rec in self:
            rec.labor_cost = rec.labor_hours * rec.labor_rate

    @api.onchange('stage_id')
    def _onchange_stage_id(self):
        if self.stage_id and not self.labor_rate:
            self.labor_rate = self.stage_id.default_labor_cost
        if self.stage_id and not self.labor_hours:
            self.labor_hours = self.stage_id.default_duration_hours

    def action_start(self):
        for rec in self:
            rec.state = 'in_progress'
            rec.date_start = fields.Datetime.now()

    def action_done(self):
        for rec in self:
            rec.state = 'done'
            rec.date_finished = fields.Datetime.now()
            if not rec.quantity_done:
                rec.quantity_done = rec.quantity_planned

    def action_cancel(self):
        self.write({'state': 'cancelled'})
