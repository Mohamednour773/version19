# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'

    def _process_saved_order(self, draft):
        """Override to create draft club.membership records for package lines.

        Called by Odoo 19 after a POS order is synced from the frontend and
        payment lines have been processed.  We hook in here (rather than in
        sync_from_ui) because at this point the order is fully persisted and
        payment_ids are populated, so we can reliably detect the payment method.

        Phase 1 rule: memberships stay in 'draft'.  Reception staff confirm them
        manually using the existing action_confirm button on the membership form.
        """
        result = super()._process_saved_order(draft)

        # Only create memberships for paid orders (draft=False means fully paid).
        if not draft:
            self._create_memberships_from_pos_lines()

        return result

    def _create_memberships_from_pos_lines(self):
        """Iterate order lines and create a draft membership for every package line.

        Skips lines that have no linked club.package.  Logs a chatter warning on
        the order when a package is found but no customer is set (walk-in support
        is Phase 2).
        """
        self.ensure_one()
        ClubMembership = self.env['club.membership']
        payment_method = self._map_pos_payment_to_membership()

        created_summaries = []

        for line in self.lines:
            tmpl = line.product_id.product_tmpl_id
            pkg = self.env['club.package'].search(
                [('product_id.product_tmpl_id', '=', tmpl.id), ('active', '=', True)],
                limit=1,
            )
            if not pkg:
                continue

            partner = self.partner_id
            if not partner:
                self.message_post(
                    body=(
                        "⚠️ Package <b>%s</b> was sold without a customer. "
                        "Please create the membership manually." % pkg.name
                    )
                )
                _logger.info(
                    'POS order %s: package %s sold without a customer — skipping membership creation.',
                    self.name, pkg.name,
                )
                continue

            # Determine branch: POS config takes priority, then package's own branch.
            branch = self.config_id.club_branch_id or pkg.branch_id

            # Mark partner as club client so the membership domain is satisfied.
            if not partner.is_club_client:
                partner.is_club_client = True

            membership = ClubMembership.create({
                'partner_id': partner.id,
                'branch_id': branch.id,
                'package_id': pkg.id,
                'date_start': fields.Date.context_today(self),
                'payment_method': payment_method,
                'payment_reference': self.name,
                'state': 'draft',
            })

            line.club_membership_id = membership.id

            created_summaries.append(
                '• <b>%s</b> → Membership <a href="#" data-oe-model="club.membership" '
                'data-oe-id="%d">%s</a> (draft)' % (pkg.name, membership.id, membership.name)
            )
            _logger.info(
                'POS order %s: created draft membership %s for partner %s / package %s.',
                self.name, membership.name, partner.name, pkg.name,
            )

        if created_summaries:
            self.message_post(
                body=(
                    'Draft memberships created from this POS order:<br/>'
                    + '<br/>'.join(created_summaries)
                    + '<br/><i>Reception staff: please open each membership and click Confirm.</i>'
                )
            )

    def _map_pos_payment_to_membership(self):
        """Map POS payment methods to the membership payment_method selection.

        Priority:
        1. Any cash payment → 'cash'
        2. Any payment with a terminal → 'card'
        3. Default → 'cash'

        Intentionally simple in Phase 1.  Phase 2 will distinguish online/transfer.
        """
        self.ensure_one()
        for payment in self.payment_ids:
            if payment.payment_method_id.is_cash_count:
                return 'cash'
        for payment in self.payment_ids:
            if payment.payment_method_id.use_payment_terminal:
                return 'card'
        return 'cash'


class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    club_membership_id = fields.Many2one(
        'club.membership',
        string='Created Membership',
        readonly=True,
        copy=False,
        help='The draft membership created from this POS order line.',
    )
