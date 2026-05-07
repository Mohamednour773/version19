# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ProductTemplate(models.Model):
    """Add salon booking fields to product.template."""
    _inherit = 'product.template'

    salon_is_bookable = fields.Boolean(
        string='Bookable Service',
        default=False,
        tracking=True,
        help=(
            'When enabled, adding this product to a POS order will prompt '
            'staff to book a salon appointment. The product will also appear '
            'in the website appointment flow.'
        ),
    )
    salon_appointment_type_id = fields.Many2one(
        comodel_name='appointment.type',
        string='Appointment Type',
        ondelete='set null',
        domain=[('is_salon_service', '=', True)],
        help='The appointment type used when booking this product.',
    )
    salon_employee_ids = fields.Many2many(
        comodel_name='hr.employee',
        relation='product_tmpl_salon_employee_rel',
        column1='product_tmpl_id',
        column2='employee_id',
        string='Available Stylists',
        help=(
            'Employees who can perform this service. '
            'Leave empty to use the appointment type\'s employee list.'
        ),
    )
    salon_default_duration = fields.Integer(
        string='Default Duration (min)',
        default=30,
        help='Override the global default slot duration for this service.',
    )

    @api.onchange('salon_is_bookable')
    def _onchange_salon_is_bookable(self):
        """Auto-set product type to service when bookable is enabled."""
        if self.salon_is_bookable and self.type != 'service':
            self.type = 'service'

    @api.onchange('salon_appointment_type_id')
    def _onchange_salon_appointment_type_id(self):
        """Sync employee list from the linked appointment type."""
        if (self.salon_appointment_type_id
                and self.salon_appointment_type_id.salon_employee_ids):
            self.salon_employee_ids = (
                self.salon_appointment_type_id.salon_employee_ids
            )
