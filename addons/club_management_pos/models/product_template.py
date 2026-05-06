# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    club_package_id = fields.Many2one(
        'club.package',
        string='Linked Club Package',
        compute='_compute_club_package_id',
        help='The club package that uses this product. Informational only.',
    )

    @api.depends('product_variant_ids')
    def _compute_club_package_id(self):
        """Find the first club.package whose product maps back to this template.

        Uses limit=1 so if a data-entry error results in two packages sharing the
        same product we take the first rather than raising.
        """
        for tmpl in self:
            pkg = self.env['club.package'].search(
                [('product_id.product_tmpl_id', '=', tmpl.id)],
                limit=1,
            )
            tmpl.club_package_id = pkg
