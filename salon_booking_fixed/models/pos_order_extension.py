# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PosOrderLine(models.Model):
    """Link a POS order line to a salon appointment."""
    _inherit = 'pos.order.line'

    salon_appointment_id = fields.Many2one(
        comodel_name='calendar.event',
        string='Salon Appointment',
        ondelete='set null',
        readonly=True,
        copy=False,
        index=True,
    )
    salon_is_bookable = fields.Boolean(
        string='Requires Booking',
        compute='_compute_salon_is_bookable',
        store=True,
    )
    salon_pos_order_line_uuid = fields.Char(
        string='Salon POS Line UUID',
        copy=False,
        index=True,
    )

    @api.depends(
        'product_id',
        'product_id.product_tmpl_id.salon_is_bookable',
    )
    def _compute_salon_is_bookable(self):
        for line in self:
            line.salon_is_bookable = (
                line.product_id.product_tmpl_id.salon_is_bookable
                if line.product_id else False
            )

    def action_view_salon_appointment(self):
        """Quick action to open the linked appointment from a POS order line."""
        self.ensure_one()
        if not self.salon_appointment_id:
            raise UserError(_("No appointment is linked to this order line."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Appointment'),
            'res_model': 'calendar.event',
            'res_id': self.salon_appointment_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._salon_link_pending_appointments()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if {'salon_pos_order_line_uuid', 'salon_appointment_id'} & set(vals):
            self._salon_link_pending_appointments()
        return res

    def _salon_link_pending_appointments(self):
        for line in self:
            if line.salon_appointment_id:
                continue
            if not line.salon_pos_order_line_uuid:
                continue
            appointment = self.env['calendar.event'].search([
                ('salon_pos_order_line_uuid', '=', line.salon_pos_order_line_uuid),
                ('salon_pos_order_line_id', '=', False),
            ], limit=1)
            if appointment:
                line.salon_appointment_id = appointment.id
                appointment.sudo().write({'salon_pos_order_line_id': line.id})


class PosOrder(models.Model):
    """Expose salon appointment summary on POS order."""
    _inherit = 'pos.order'

    salon_appointment_count = fields.Integer(
        string='Appointments',
        compute='_compute_salon_appointment_count',
        store=False,
    )

    def _compute_salon_appointment_count(self):
        for order in self:
            order.salon_appointment_count = sum(
                1 for line in order.lines if line.salon_appointment_id
            )

    def action_view_salon_appointments(self):
        self.ensure_one()
        appointment_ids = self.lines.mapped('salon_appointment_id').ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('Salon Appointments'),
            'res_model': 'calendar.event',
            'view_mode': 'list,form',
            'domain': [('id', 'in', appointment_ids)],
        }


class ProductProduct(models.Model):
    """Expose salon_is_bookable to the POS frontend (product.product level)."""
    _inherit = 'product.product'

    @api.model
    def _load_pos_data_fields(self, config_id):
        fields = super()._load_pos_data_fields(config_id)
        if 'salon_is_bookable' not in fields:
            fields.append('salon_is_bookable')
        return fields


class ProductTemplate(models.Model):
    """Expose salon_is_bookable to the POS frontend (product.template level).

    In Odoo 19, addProductToOrder() receives a product.template instance,
    so the field must be loaded on the template model too.
    """
    _inherit = 'product.template'

    @api.model
    def _load_pos_data_fields(self, config_id):
        fields = super()._load_pos_data_fields(config_id)
        if 'salon_is_bookable' not in fields:
            fields.append('salon_is_bookable')
        return fields
