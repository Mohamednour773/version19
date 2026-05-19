# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class FactoryProduction(models.Model):
    """
    Factory Production Order | أمر إنتاج المصنع
    
    Custom production order tailored to project-based GRC/Precast manufacturing.
    Each order is linked to a sector, follows configurable manufacturing stages,
    consumes a specific mix design, and uses specific molds.
    
    أمر إنتاج مخصص للتصنيع القائم على المشاريع.
    كل أمر مرتبط بقطاع، يتبع مراحل تصنيع، يستهلك خلطة محددة، ويستخدم قوالب محددة.
    """
    _name = 'factory.production'
    _description = 'Factory Production Order | أمر إنتاج المصنع'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_planned desc, id desc'

    name = fields.Char(string='Reference | المرجع', default='New', copy=False, readonly=True, tracking=True)
    
    # Core links | الروابط الأساسية
    project_id = fields.Many2one('project.project', string='Project | المشروع', required=True, tracking=True)
    sector_id = fields.Many2one(
        'factory.sector', string='Sector | القطاع', required=True,
        domain="[('project_id','=',project_id)]", tracking=True)
    product_id = fields.Many2one(
        'product.product', string='Product | المنتج', required=True, tracking=True)
    mix_id = fields.Many2one(
        'factory.mix', string='Mix Design | الخلطة',
        domain="[('product_id','=',product_id),('state','=','approved')]", tracking=True)
    mold_ids = fields.Many2many(
        'factory.mold', 'production_mold_rel', 'production_id', 'mold_id',
        string='Molds | القوالب',
        domain="[('product_id','=',product_id),('state','in',['available','in_use'])]")
    
    # Quantities | الكميات
    quantity_planned = fields.Float(
        string='Planned Quantity | الكمية المخططة',
        required=True, digits='Product Unit of Measure', tracking=True)
    quantity_produced = fields.Float(
        string='Produced Quantity | الكمية المنتجة',
        compute='_compute_quantities', store=True)
    quantity_waste = fields.Float(
        string='Waste Quantity | كمية الهالك',
        compute='_compute_quantities', store=True)
    quantity_remaining = fields.Float(
        string='Remaining | المتبقي',
        compute='_compute_quantities', store=True)
    uom_id = fields.Many2one('uom.uom', string='UoM | الوحدة', related='product_id.uom_id', store=True)
    
    # Dates | التواريخ
    date_planned = fields.Datetime(
        string='Planned Date | تاريخ التخطيط',
        default=fields.Datetime.now, required=True, tracking=True)
    date_start = fields.Datetime(string='Start Date | تاريخ البدء', readonly=True)
    date_finished = fields.Datetime(string='Finish Date | تاريخ الانتهاء', readonly=True)
    
    # Stages | المراحل
    stage_line_ids = fields.One2many(
        'factory.production.stage', 'production_id', string='Stages | المراحل', copy=False)
    current_stage_id = fields.Many2one(
        'factory.stage', string='Current Stage | المرحلة الحالية', compute='_compute_current_stage', store=True)
    
    # Mix consumption | استهلاك الخلطة
    consumption_id = fields.Many2one(
        'factory.mix.consumption', string='Mix Consumption | استهلاك الخلطة', readonly=True, copy=False)
    
    # Cost rollup | تجميع التكلفة
    cost_materials = fields.Monetary(
        string='Materials Cost | تكلفة الخامات',
        compute='_compute_costs', store=True, currency_field='currency_id')
    cost_molds = fields.Monetary(
        string='Molds Cost | تكلفة القوالب',
        compute='_compute_costs', store=True, currency_field='currency_id')
    cost_labor = fields.Monetary(
        string='Labor Cost | تكلفة العمالة',
        compute='_compute_costs', store=True, currency_field='currency_id')
    cost_total = fields.Monetary(
        string='Total Cost | إجمالي التكلفة',
        compute='_compute_costs', store=True, currency_field='currency_id')
    cost_per_unit = fields.Monetary(
        string='Cost per Unit | تكلفة الوحدة',
        compute='_compute_costs', store=True, currency_field='currency_id')
    
    # State | الحالة
    state = fields.Selection([
        ('draft', 'Draft | مسودة'),
        ('planned', 'Planned | مخطط'),
        ('in_progress', 'In Progress | قيد التنفيذ'),
        ('done', 'Done | منتهي'),
        ('cancelled', 'Cancelled | ملغي'),
    ], string='Status | الحالة', default='draft', tracking=True)
    
    notes = fields.Text(string='Notes | ملاحظات')
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account | الحساب التحليلي')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', string='Responsible | المسؤول', default=lambda self: self.env.user)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('factory.production') or 'New'
        return super().create(vals_list)

    @api.depends('stage_line_ids.quantity_done', 'stage_line_ids.quantity_waste', 'stage_line_ids.state',
                 'stage_line_ids.stage_id', 'quantity_planned')
    def _compute_quantities(self):
        for rec in self:
            # produced = max done qty across "finishing/storage" stages
            final_stages = rec.stage_line_ids.filtered(
                lambda s: s.state == 'done' and s.stage_id.stage_type in ('finishing', 'storage'))
            if final_stages:
                rec.quantity_produced = max(final_stages.mapped('quantity_done'))
            else:
                # fallback: max quantity done across all done stages
                done = rec.stage_line_ids.filtered(lambda s: s.state == 'done')
                rec.quantity_produced = max(done.mapped('quantity_done')) if done else 0.0
            rec.quantity_waste = sum(rec.stage_line_ids.mapped('quantity_waste'))
            rec.quantity_remaining = max(0.0, rec.quantity_planned - rec.quantity_produced)

    @api.depends('stage_line_ids.state', 'stage_line_ids.stage_id.sequence')
    def _compute_current_stage(self):
        for rec in self:
            in_progress = rec.stage_line_ids.filtered(lambda s: s.state == 'in_progress')
            if in_progress:
                rec.current_stage_id = in_progress.sorted('id')[0].stage_id
            else:
                pending = rec.stage_line_ids.filtered(lambda s: s.state in ('pending', 'ready'))
                if pending:
                    rec.current_stage_id = pending.sorted(lambda s: s.stage_id.sequence)[0].stage_id
                else:
                    rec.current_stage_id = False

    @api.depends('consumption_id.actual_cost', 'mold_ids.cost_per_unit',
                 'stage_line_ids.labor_cost', 'quantity_produced')
    def _compute_costs(self):
        for rec in self:
            rec.cost_materials = rec.consumption_id.actual_cost if rec.consumption_id else 0.0
            rec.cost_molds = sum(rec.mold_ids.mapped('cost_per_unit')) * rec.quantity_produced
            rec.cost_labor = sum(rec.stage_line_ids.mapped('labor_cost'))
            rec.cost_total = rec.cost_materials + rec.cost_molds + rec.cost_labor
            rec.cost_per_unit = (rec.cost_total / rec.quantity_produced) if rec.quantity_produced else 0.0

    @api.onchange('sector_id')
    def _onchange_sector_id(self):
        if self.sector_id:
            if self.sector_id.product_id:
                self.product_id = self.sector_id.product_id
            if self.sector_id.mix_id:
                self.mix_id = self.sector_id.mix_id
            if self.sector_id.analytic_account_id:
                self.analytic_account_id = self.sector_id.analytic_account_id
            if hasattr(self.sector_id, 'mold_ids'):
                self.mold_ids = [(6, 0, self.sector_id.mold_ids.ids)]

    def action_plan(self):
        """Generate stage lines from configured manufacturing stages."""
        for rec in self:
            if not rec.stage_line_ids:
                stages = self.env['factory.stage'].search(
                    [('stage_type', 'in',
                      ['mold_prep', 'casting', 'demolding', 'curing', 'finishing', 'storage'])],
                    order='sequence')
                lines = []
                for stage in stages:
                    lines.append((0, 0, {
                        'stage_id': stage.id,
                        'quantity_planned': rec.quantity_planned,
                        'state': 'pending',
                    }))
                rec.stage_line_ids = lines
            rec.state = 'planned'

    def action_start(self):
        for rec in self:
            if not rec.mix_id:
                raise UserError(_('Please select a mix design first | يرجى اختيار خلطة أولاً'))
            if not rec.mold_ids:
                raise UserError(_('Please select molds first | يرجى اختيار القوالب أولاً'))
            rec.state = 'in_progress'
            rec.date_start = fields.Datetime.now()
            # Create the consumption record
            if not rec.consumption_id:
                cons = self.env['factory.mix.consumption'].create({
                    'mix_id': rec.mix_id.id,
                    'project_id': rec.project_id.id,
                    'sector_id': rec.sector_id.id,
                    'produced_quantity': rec.quantity_planned,
                    'date': fields.Date.context_today(rec),
                })
                cons.action_load_mix_lines()
                rec.consumption_id = cons.id

    def action_done(self):
        for rec in self:
            # Confirm consumption
            if rec.consumption_id and rec.consumption_id.state == 'draft':
                rec.consumption_id.action_confirm()
            # Register mold usages
            for mold in rec.mold_ids:
                mold.register_usage(
                    project_id=rec.project_id.id,
                    sector_id=rec.sector_id.id,
                    use_count=1,
                    produced_qty=rec.quantity_produced,
                    notes=_('Auto from production %s') % rec.name,
                )
            rec.state = 'done'
            rec.date_finished = fields.Datetime.now()

    def action_cancel(self):
        for rec in self:
            if rec.consumption_id and rec.consumption_id.state != 'cancelled':
                rec.consumption_id.action_cancel()
            rec.state = 'cancelled'

    def action_reset(self):
        self.write({'state': 'draft'})

    def action_view_consumption(self):
        self.ensure_one()
        return {
            'name': _('Mix Consumption | استهلاك الخلطة'),
            'type': 'ir.actions.act_window',
            'res_model': 'factory.mix.consumption',
            'res_id': self.consumption_id.id,
            'view_mode': 'form',
        }
