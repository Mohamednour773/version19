# -*- coding: utf-8 -*-
from odoo import models, fields, api


class FactoryStage(models.Model):
    """
    Manufacturing Stage | مرحلة التصنيع
    
    Represents stages like: Mold Preparation, Spraying/Casting, 
    Demolding, Curing, Finishing, Storage.
    
    يمثل المراحل مثل: تجهيز القالب، الرش/الصب، الفك، المعالجة، التشطيب، التخزين
    """
    _name = 'factory.stage'
    _description = 'Manufacturing Stage | مرحلة التصنيع'
    _order = 'sequence, id'

    name = fields.Char(string='Stage Name | اسم المرحلة', required=True, translate=True)
    code = fields.Char(string='Code | الكود', required=True)
    sequence = fields.Integer(string='Sequence | الترتيب', default=10)
    description = fields.Text(string='Description | الوصف', translate=True)
    
    stage_type = fields.Selection([
        ('mold_prep', 'Mold Preparation | تجهيز القالب'),
        ('casting', 'Casting / Spraying | الصب / الرش'),
        ('demolding', 'Demolding | الفك'),
        ('curing', 'Curing | المعالجة'),
        ('finishing', 'Finishing | التشطيب'),
        ('storage', 'Storage | التخزين'),
        ('delivery', 'Delivery | التوريد'),
        ('installation', 'Site Installation | التركيب بالموقع'),
        ('other', 'Other | أخرى'),
    ], string='Stage Type | نوع المرحلة', required=True, default='other')
    
    # Default duration and cost per unit | المدة والتكلفة الافتراضية
    default_duration_hours = fields.Float(
        string='Default Duration (Hours) | المدة الافتراضية (ساعات)',
        default=1.0,
    )
    default_labor_cost = fields.Monetary(
        string='Default Labor Cost / Unit | تكلفة العمالة الافتراضية للوحدة',
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
    )
    
    requires_quality_check = fields.Boolean(
        string='Requires Quality Check | يتطلب فحص جودة',
        default=False,
    )
    track_waste = fields.Boolean(
        string='Track Waste | تتبع الهالك',
        default=True,
        help='If enabled, waste/loss percentages are tracked at this stage | إذا تم التفعيل يتم تتبع نسب الهالك في هذه المرحلة',
    )
    
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
    )

    _sql_constraints = [
        ('code_company_uniq', 'unique(code, company_id)',
         'Stage code must be unique per company! | كود المرحلة يجب أن يكون فريداً لكل شركة!'),
    ]
