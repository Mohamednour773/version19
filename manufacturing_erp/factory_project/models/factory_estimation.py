# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class FactoryEstimation(models.Model):
    """
    Project Estimation (Quote/BoQ) | مقايسة المشروع
    
    Detailed pricing and cost build-up for a project before confirmation.
    On approval, generates the project, sectors, sale order, and analytic account.
    
    تسعير تفصيلي وحساب التكلفة للمشروع قبل الاعتماد. عند الاعتماد ينشئ المشروع
    والقطاعات وأمر البيع والحساب التحليلي.
    """
    _name = 'factory.estimation'
    _description = 'Project Estimation | مقايسة المشروع'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(string='Reference | المرجع', default='New', copy=False, readonly=True)
    title = fields.Char(string='Project Title | عنوان المشروع', required=True, tracking=True)
    partner_id = fields.Many2one('res.partner', string='Customer | العميل', required=True, tracking=True)
    date = fields.Date(string='Date | التاريخ', default=fields.Date.context_today, required=True, tracking=True)
    validity_date = fields.Date(string='Validity Date | تاريخ سريان العرض', tracking=True)
    
    expected_start_date = fields.Date(string='Expected Start | تاريخ البدء المتوقع')
    expected_end_date = fields.Date(string='Expected End | تاريخ الانتهاء المتوقع')
    delivery_duration_days = fields.Integer(string='Delivery Duration (days) | مدة التنفيذ (يوم)')
    
    # Lines | البنود
    line_ids = fields.One2many('factory.estimation.line', 'estimation_id', string='Lines | البنود', copy=True)
    
    # Cost build-up | بناء التكلفة
    subtotal_materials = fields.Monetary(
        string='Materials Cost | تكلفة الخامات',
        compute='_compute_totals', store=True, currency_field='currency_id')
    subtotal_molds = fields.Monetary(
        string='Molds Cost | تكلفة القوالب',
        compute='_compute_totals', store=True, currency_field='currency_id')
    subtotal_labor = fields.Monetary(
        string='Labor Cost | تكلفة العمالة',
        compute='_compute_totals', store=True, currency_field='currency_id')
    subtotal_installation = fields.Monetary(
        string='Installation Cost | تكلفة التركيب',
        compute='_compute_totals', store=True, currency_field='currency_id')
    subtotal_overheads = fields.Monetary(
        string='Overheads | المصاريف العمومية',
        compute='_compute_totals', store=True, currency_field='currency_id')
    
    total_direct_cost = fields.Monetary(
        string='Total Direct Cost | إجمالي التكلفة المباشرة',
        compute='_compute_totals', store=True, currency_field='currency_id')
    
    overhead_percent = fields.Float(
        string='Overhead % | نسبة المصاريف العمومية',
        default=10.0, digits=(5, 2), tracking=True)
    profit_percent = fields.Float(
        string='Profit % | نسبة الربح',
        default=20.0, digits=(5, 2), tracking=True)
    contingency_percent = fields.Float(
        string='Contingency % | نسبة الطوارئ',
        default=5.0, digits=(5, 2), tracking=True)
    
    contingency_amount = fields.Monetary(
        string='Contingency | الطوارئ',
        compute='_compute_totals', store=True, currency_field='currency_id')
    profit_amount = fields.Monetary(
        string='Profit | الربح',
        compute='_compute_totals', store=True, currency_field='currency_id')
    total_cost = fields.Monetary(
        string='Total Cost | إجمالي التكلفة',
        compute='_compute_totals', store=True, currency_field='currency_id')
    total_amount = fields.Monetary(
        string='Total Price | إجمالي السعر',
        compute='_compute_totals', store=True, currency_field='currency_id',
        help='Final price quoted to the customer | السعر النهائي المعروض على العميل')
    
    margin_amount = fields.Monetary(
        string='Margin | الهامش',
        compute='_compute_totals', store=True, currency_field='currency_id')
    margin_percent = fields.Float(
        string='Margin % | نسبة الهامش',
        compute='_compute_totals', store=True, digits=(5, 2))
    
    # State | الحالة
    state = fields.Selection([
        ('draft', 'Draft | مسودة'),
        ('submitted', 'Submitted | مرسلة'),
        ('approved', 'Approved | معتمدة'),
        ('won', 'Won → Project Created | فائزة → تم إنشاء مشروع'),
        ('lost', 'Lost | خاسرة'),
        ('cancelled', 'Cancelled | ملغاة'),
    ], string='Status | الحالة', default='draft', tracking=True)
    
    # Generated records | السجلات الناتجة
    project_id = fields.Many2one('project.project', string='Generated Project | المشروع الناتج', readonly=True)
    sale_order_id = fields.Many2one('sale.order', string='Sale Order | أمر البيع', readonly=True)
    
    notes = fields.Text(string='Notes | ملاحظات')
    
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', string='Salesperson | المسؤول', default=lambda self: self.env.user)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('factory.estimation') or 'New'
        return super().create(vals_list)

    @api.depends('line_ids', 'line_ids.subtotal', 'line_ids.cost_category',
                 'overhead_percent', 'profit_percent', 'contingency_percent')
    def _compute_totals(self):
        for rec in self:
            mats = sum(rec.line_ids.filtered(lambda l: l.cost_category == 'material').mapped('subtotal'))
            molds = sum(rec.line_ids.filtered(lambda l: l.cost_category == 'mold').mapped('subtotal'))
            labor = sum(rec.line_ids.filtered(lambda l: l.cost_category == 'labor').mapped('subtotal'))
            install = sum(rec.line_ids.filtered(lambda l: l.cost_category == 'installation').mapped('subtotal'))
            other = sum(rec.line_ids.filtered(lambda l: l.cost_category == 'other').mapped('subtotal'))
            
            rec.subtotal_materials = mats
            rec.subtotal_molds = molds
            rec.subtotal_labor = labor
            rec.subtotal_installation = install
            
            direct = mats + molds + labor + install + other
            rec.subtotal_overheads = direct * (rec.overhead_percent / 100.0)
            rec.total_direct_cost = direct
            
            cost_with_oh = direct + rec.subtotal_overheads
            rec.contingency_amount = cost_with_oh * (rec.contingency_percent / 100.0)
            rec.total_cost = cost_with_oh + rec.contingency_amount
            rec.profit_amount = rec.total_cost * (rec.profit_percent / 100.0)
            rec.total_amount = rec.total_cost + rec.profit_amount
            
            rec.margin_amount = rec.total_amount - rec.total_cost
            rec.margin_percent = (rec.margin_amount / rec.total_amount * 100.0) if rec.total_amount else 0.0

    def action_submit(self):
        for rec in self:
            if not rec.line_ids:
                raise ValidationError(_('Cannot submit an empty estimation | لا يمكن إرسال مقايسة فارغة'))
            rec.state = 'submitted'

    def action_approve(self):
        self.write({'state': 'approved'})

    def action_mark_lost(self):
        self.write({'state': 'lost'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_to_draft(self):
        self.write({'state': 'draft'})

    def action_create_project(self):
        """Convert approved estimation into a project + sectors + analytic account."""
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_('Only approved estimations can be converted | لا يمكن تحويل إلا المقايسات المعتمدة'))
        if self.project_id:
            raise UserError(_('A project has already been created for this estimation | تم إنشاء مشروع لهذه المقايسة بالفعل'))

        # 1. Create analytic account
        plan = self.env['account.analytic.plan'].search([], limit=1)
        if not plan:
            plan = self.env['account.analytic.plan'].create({'name': 'Projects | المشاريع'})
        analytic = self.env['account.analytic.account'].create({
            'name': self.title,
            'partner_id': self.partner_id.id,
            'plan_id': plan.id,
            'company_id': self.company_id.id,
        })

        # 2. Create project
        project = self.env['project.project'].create({
            'name': self.title,
            'partner_id': self.partner_id.id,
            'user_id': self.user_id.id,
            'date_start': self.expected_start_date,
            'date': self.expected_end_date,
            'company_id': self.company_id.id,
            'is_factory_project': True,
            'estimation_id': self.id,
        })
        # Set analytic account separately (field may have different semantics in some versions)
        if hasattr(project, 'analytic_account_id'):
            try:
                project.analytic_account_id = analytic.id
            except Exception:
                pass

        # 3. Create sectors from estimation lines (grouped by sector_name)
        sector_groups = {}
        for line in self.line_ids:
            key = line.sector_name or 'Main'
            sector_groups.setdefault(key, []).append(line)

        seq = 10
        for sector_key, lines in sector_groups.items():
            product_lines = [l for l in lines if l.product_id]
            main_product = product_lines[0].product_id if product_lines else False
            total_qty = sum(l.quantity for l in lines if l.cost_category in ('material', 'labor'))
            unit_price = (sum(l.subtotal for l in lines) / total_qty) if total_qty else 0.0
            
            self.env['factory.sector'].create({
                'name': sector_key,
                'code': f'SEC-{seq:03d}',
                'project_id': project.id,
                'product_id': main_product.id if main_product else False,
                'planned_quantity': total_qty,
                'unit_price': unit_price,
                'analytic_account_id': analytic.id,
                'sequence': seq,
            })
            seq += 10

        # 4. Create sale order
        so = self.env['sale.order'].create({
            'partner_id': self.partner_id.id,
            'date_order': fields.Datetime.now(),
            'project_id': project.id,
            'company_id': self.company_id.id,
            'user_id': self.user_id.id,
        })
        # Group SO lines per sector
        for sector_key, lines in sector_groups.items():
            for line in lines:
                if not line.product_id:
                    continue
                self.env['sale.order.line'].create({
                    'order_id': so.id,
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.quantity,
                    'price_unit': line.unit_price,
                    'name': f'[{sector_key}] {line.description or line.product_id.name}',
                })

        self.write({
            'state': 'won',
            'project_id': project.id,
            'sale_order_id': so.id,
        })
        return {
            'name': _('Project | المشروع'),
            'type': 'ir.actions.act_window',
            'res_model': 'project.project',
            'res_id': project.id,
            'view_mode': 'form',
        }

    def action_view_project(self):
        self.ensure_one()
        return {
            'name': _('Project | المشروع'),
            'type': 'ir.actions.act_window',
            'res_model': 'project.project',
            'res_id': self.project_id.id,
            'view_mode': 'form',
        }
