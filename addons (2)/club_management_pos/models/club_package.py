# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ClubPackage(models.Model):
    _inherit = 'club.package'

    available_in_pos = fields.Boolean(
        string='Available in POS',
        default=False,
        tracking=True,
        help='When checked, this package can be sold from the Point of Sale.',
    )

    @api.onchange('available_in_pos')
    def _onchange_available_in_pos(self):
        """Sync the available_in_pos flag to the linked product so POS sessions pick it up."""
        if not self.product_id:
            return
        self.product_id.available_in_pos = self.available_in_pos

    @api.constrains('available_in_pos', 'product_id')
    def _check_pos_requires_product(self):
        """A package cannot be offered in POS without a linked product.

        Without product_id the package cannot appear in the POS item list, so
        we block the combination early rather than letting reception discover the
        gap at session time.
        """
        for pkg in self:
            if pkg.available_in_pos and not pkg.product_id:
                raise ValidationError(
                    'يجب تحديد المنتج قبل تفعيل البيع عبر نقطة البيع.\n'
                    'A product must be set before enabling "Available in POS".'
                )
