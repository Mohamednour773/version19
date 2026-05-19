# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class FactorySector(models.Model):
    _inherit = 'factory.sector'

    delivery_permit_ids = fields.One2many(
        'factory.delivery.permit', 'sector_id', string='Delivery Permits | أذون التوريد')
    installation_ids = fields.One2many(
        'factory.installation', 'sector_id', string='Installations | التركيبات')
    
    delivery_count = fields.Integer(compute='_compute_site_counts', string='Delivery Count')
    installation_count = fields.Integer(compute='_compute_site_counts', string='Installation Count')

    def _compute_site_counts(self):
        for rec in self:
            rec.delivery_count = len(rec.delivery_permit_ids)
            rec.installation_count = len(rec.installation_ids)

    @api.depends('delivery_permit_ids.state', 'delivery_permit_ids.line_ids.quantity_delivered',
                 'installation_ids.state', 'installation_ids.quantity_installed',
                 'production_ids.state', 'production_ids.quantity_produced')
    def _compute_quantities(self):
        super()._compute_quantities()
        for rec in self:
            confirmed_deliveries = rec.delivery_permit_ids.filtered(lambda d: d.state == 'confirmed')
            rec.delivered_quantity = sum(
                line.quantity_delivered for d in confirmed_deliveries for line in d.line_ids)
            done_installations = rec.installation_ids.filtered(lambda i: i.state == 'done')
            rec.installed_quantity = sum(done_installations.mapped('quantity_installed'))
