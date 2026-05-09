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

        Uses limit=1 so if a data-entry error results in two packages sharing
        the same product we take the first rather than raising.
        """
        for tmpl in self:
            pkg = self.env['club.package'].search(
                [('product_id.product_tmpl_id', '=', tmpl.id)],
                limit=1,
            )
            tmpl.club_package_id = pkg

    @api.model
    def _load_pos_data_domain(self, data, config):
        """Feature 3 — Branch filtering.

        Extends the standard POS product domain so that when a POS config has
        ``club_branch_id`` set, products linked to packages from *other* branches
        are excluded from the session's product catalogue.

        Non-package products (regular stock/service items) are never filtered —
        only products that are the ``product_id`` of an ``available_in_pos``
        club.package in the wrong branch are excluded.

        If ``club_branch_id`` is empty, no filtering happens and all
        available-in-pos packages show regardless of branch.
        """
        domain = super()._load_pos_data_domain(data, config)

        if not config.club_branch_id:
            return domain

        # Find package products that belong to a *different* branch.
        # Conservatively: if a product is linked to ANY package in a wrong
        # branch (even if also linked to a correct-branch package — a data
        # issue), we exclude it so the wrong-branch package cannot be sold.
        bad_packages = self.env['club.package'].search([
            ('available_in_pos', '=', True),
            ('branch_id', '!=', config.club_branch_id.id),
            ('active', '=', True),
        ])
        bad_tmpl_ids = bad_packages.mapped('product_id.product_tmpl_id.id')
        if bad_tmpl_ids:
            domain += [('id', 'not in', bad_tmpl_ids)]
            _logger.info(
                'POS session (config %s, branch %s): excluding %d product template(s) '
                'linked to packages from other branches.',
                config.name, config.club_branch_id.name, len(bad_tmpl_ids),
            )

        return domain
