# -*- coding: utf-8 -*-
import logging
from datetime import timedelta
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'

    # ══════════════════════════════════════════════════════════════════════════
    # ENTRY POINT — called by Odoo 19 after POS payment is processed
    # ══════════════════════════════════════════════════════════════════════════

    def _process_saved_order(self, draft):
        """Hook into the post-payment flow to create/confirm club memberships.

        Phase 1 created draft memberships only.
        Phase 2 adds: auto-confirmation, walk-in tagging, soft validation
        warnings, registration-fee routing, and accurate payment mapping.

        ``draft=True``  → order saved but not yet paid (sync from POS UI).
                          We skip membership logic here.
        ``draft=False`` → order fully paid; this is our trigger.
        """
        result = super()._process_saved_order(draft)

        if not draft:
            self._create_memberships_from_pos_lines()

        return result

    # ══════════════════════════════════════════════════════════════════════════
    # MAIN ORCHESTRATOR
    # ══════════════════════════════════════════════════════════════════════════

    def _create_memberships_from_pos_lines(self):
        """Iterate all order lines and process those that are club packages.

        For each package line:
        1. Resolve the partner (walk-in detection, required-field check).
        2. If the package is a registration-fee package, route to the special
           handler instead of creating a membership.
        3. Create the draft membership.
        4. Run soft eligibility validations and post any warnings.
        5. Attempt auto-confirm if the POS config enables it.
        6. Summarise everything in a single chatter message on the order.
        """
        self.ensure_one()

        payment_method = self._map_pos_payment_to_membership()
        order_summaries = []  # collected per-line summaries for the final chatter

        for line in self.lines:
            pkg = self._find_package_for_line(line)
            if not pkg:
                continue

            # ── 1. Resolve partner ──────────────────────────────────────────
            partner = self.partner_id
            if not partner:
                self.message_post(body=(
                    '⚠️ <b>لم يتم تحديد عميل / No customer set.</b><br/>'
                    'Package <b>%s</b> was sold without a customer. '
                    'Please create the membership manually.'
                ) % pkg.name)
                _logger.info(
                    'POS order %s: package %s sold with no customer — skipping.',
                    self.name, pkg.name,
                )
                continue

            # ── 2. Walk-in detection & tagging ─────────────────────────────
            is_walkin = self._detect_walkin(partner)
            walkin_missing = []
            if is_walkin:
                self._tag_walkin_partner(partner)
                walkin_missing = self._check_required_walkin_fields(partner)

            # ── 3. Mark as club client (always, for any package sale) ───────
            if not partner.is_club_client:
                partner.is_club_client = True

            # ── 4. Determine branch ─────────────────────────────────────────
            branch = self.config_id.club_branch_id or pkg.branch_id

            # ── 5. Registration-fee packages — special routing ──────────────
            if pkg.is_registration_fee:
                self._handle_registration_fee_sale(pkg, partner, branch)
                continue

            # ── 6. Create the membership (always draft at creation) ─────────
            try:
                membership = self.env['club.membership'].create({
                    'partner_id': partner.id,
                    'branch_id': branch.id,
                    'package_id': pkg.id,
                    'date_start': fields.Date.context_today(self),
                    'payment_method': payment_method,
                    'payment_reference': self.name,
                    'state': 'draft',
                })
            except Exception as exc:
                self.message_post(body=(
                    '❌ Failed to create membership for <b>%s</b> / <b>%s</b>: %s'
                ) % (partner.name, pkg.name, exc))
                _logger.error(
                    'POS order %s: unexpected error creating membership — %s',
                    self.name, exc, exc_info=True,
                )
                continue

            line.club_membership_id = membership.id
            _logger.info(
                'POS order %s: created draft membership %s for partner %s / package %s.',
                self.name, membership.name, partner.name, pkg.name,
            )

            # ── 7. Soft eligibility warnings ────────────────────────────────
            warnings = self._pos_validate_membership_eligibility(
                pkg, partner, branch, membership
            )
            if walkin_missing:
                warnings.insert(0, (
                    '⚠️ Walk-in customer is missing required info (<b>%s</b>). '
                    'Membership left in Draft — reception please complete.'
                ) % ', '.join(walkin_missing))

            if warnings:
                warning_html = (
                    '🔔 <b>تحذيرات / Warnings — %s / %s:</b><br/>'
                    % (partner.name, pkg.name)
                    + '<br/>'.join('• ' + w for w in warnings)
                )
                self.message_post(body=warning_html)
                membership.message_post(body=warning_html)

            # ── 8. Auto-confirm ─────────────────────────────────────────────
            skip_confirm = bool(walkin_missing)
            if self.config_id.club_auto_confirm_membership and not skip_confirm:
                self._try_auto_confirm(membership, partner)

            # ── 9. Build summary line for the final chatter ─────────────────
            state_label = dict(
                self.env['club.membership']._fields['state'].selection
            ).get(membership.state, membership.state)
            order_summaries.append(
                '• <b>%s</b> → '
                '<a href="#" data-oe-model="club.membership" data-oe-id="%d">%s</a>'
                ' (%s)'
                % (pkg.name, membership.id, membership.name, state_label)
            )

        # ── Final summary chatter ────────────────────────────────────────────
        if order_summaries:
            self.message_post(body=(
                '✅ <b>Club memberships from this POS order:</b><br/>'
                + '<br/>'.join(order_summaries)
            ))

    # ══════════════════════════════════════════════════════════════════════════
    # HELPERS — package lookup
    # ══════════════════════════════════════════════════════════════════════════

    def _find_package_for_line(self, line):
        """Return the active club.package whose product matches this order line.

        Returns False if the product is not a club package (normal POS sale).
        """
        tmpl = line.product_id.product_tmpl_id
        return self.env['club.package'].search(
            [('product_id.product_tmpl_id', '=', tmpl.id), ('active', '=', True)],
            limit=1,
        )

    # ══════════════════════════════════════════════════════════════════════════
    # HELPERS — walk-in
    # ══════════════════════════════════════════════════════════════════════════

    def _detect_walkin(self, partner):
        """Return True if the partner looks like a fresh walk-in.

        Phase 2 (bug-fixed): uses a 4-hour sliding window instead of the
        session start_at boundary.  The original session-start comparison was
        fragile because transaction ordering and timezone handling could place
        ``partner.create_date`` a few microseconds before ``session.start_at``
        even when the cashier created the partner seconds into the session.

        A walk-in is a partner who:
        - is not yet flagged as a club client, AND
        - was created within the last 4 hours (covers any normal POS shift).
        """
        threshold = fields.Datetime.now() - timedelta(hours=4)
        is_walkin = (
            not partner.is_club_client
            and bool(partner.create_date)
            and partner.create_date >= threshold
        )
        _logger.info(
            'POS order %s: walk-in check — partner=%s (id=%s), '
            'is_club_client=%s, create_date=%s, threshold=%s → is_walkin=%s',
            self.name, partner.name, partner.id,
            partner.is_club_client, partner.create_date, threshold, is_walkin,
        )
        return is_walkin

    def _tag_walkin_partner(self, partner):
        """Add the Walk-in tag to the partner and post a chatter note.

        Phase 2 (bug-fixed):
        - Replaced ``raise_if_not_found=False`` (silent failure) with an
          explicit try/except that logs at ERROR level so missing data is
          immediately visible in the Odoo log.
        - Replaced the incorrect direct-assignment syntax
          ``partner.category_id = [(4, tag.id)]`` with
          ``partner.write({'category_id': [(4, tag.id)]})`` which correctly
          processes Many2many ORM commands.  Direct assignment ignores the
          command tuple and overwrites the field with the raw list object.
        """
        _logger.info(
            'POS order %s: tagging walk-in — partner=%s (id=%s), '
            'is_club_client_before=%s, create_date=%s, existing_tags=%s',
            self.name, partner.name, partner.id,
            partner.is_club_client, partner.create_date,
            partner.category_id.mapped('name'),
        )

        try:
            walkin_tag = self.env.ref('club_management_pos.category_walkin')
        except ValueError:
            _logger.error(
                'POS order %s: XML ID "club_management_pos.category_walkin" not found '
                '— partner %s (id=%s) will NOT receive the Walk-in tag. '
                'Re-install the module to restore the data record.',
                self.name, partner.name, partner.id,
            )
            return

        if walkin_tag not in partner.category_id:
            partner.write({'category_id': [(4, walkin_tag.id)]})
            _logger.info(
                'Walk-in tag applied to partner %s (id=%s).',
                partner.name, partner.id,
            )
        else:
            _logger.info(
                'POS order %s: Walk-in tag already present on partner %s (id=%s) — skipping.',
                self.name, partner.name, partner.id,
            )

        partner.message_post(body=(
            '🚶 Walk-in customer registered via POS <b>%s</b> on %s.'
        ) % (self.config_id.name, fields.Date.context_today(self)))

    def _check_required_walkin_fields(self, partner):
        """Return a list of missing required field labels for walk-in partners.

        Phase 2 requires name, phone, and email.  If any are absent the
        membership will be left in Draft regardless of the auto-confirm setting.
        """
        missing = []
        if not partner.name:
            missing.append('name')
        if not partner.phone:
            missing.append('phone')
        if not partner.email:
            missing.append('email')
        return missing

    # ══════════════════════════════════════════════════════════════════════════
    # HELPERS — registration fee routing
    # ══════════════════════════════════════════════════════════════════════════

    def _handle_registration_fee_sale(self, pkg, partner, branch):
        """Handle the sale of a registration-fee-only package.

        A registration-fee package is not a real subscription; it unlocks the
        ability to enrol in substantive packages that have
        ``requires_registration=True``.

        Instead of creating a new membership:
        1. Find the partner's most recent draft or active membership in this
           branch that is NOT itself a registration-fee record.
        2. Set ``registration_fee_paid=True`` on it (a Phase 2 extension flag).
        3. Post a chatter note on the order and on the found membership.
        4. If no eligible membership exists, surface a clear warning.
        """
        target = self.env['club.membership'].search([
            ('partner_id', '=', partner.id),
            ('branch_id', '=', branch.id),
            ('package_id.is_registration_fee', '=', False),
            ('state', 'in', ('draft', 'confirmed', 'active', 'suspended')),
        ], order='date_start desc', limit=1)

        if target:
            target.registration_fee_paid = True
            target.message_post(body=(
                '💳 Registration fee paid via POS order <b>%s</b> '
                '(package: %s) on %s.'
            ) % (self.name, pkg.name, fields.Date.context_today(self)))
            self.message_post(body=(
                '💳 <b>رسوم التسجيل / Registration fee</b> for '
                '<b>%s</b> (package: %s) linked to membership '
                '<a href="#" data-oe-model="club.membership" data-oe-id="%d">%s</a>.'
            ) % (partner.name, pkg.name, target.id, target.name))
            _logger.info(
                'POS order %s: registration fee (pkg %s) linked to membership %s.',
                self.name, pkg.name, target.name,
            )
        else:
            self.message_post(body=(
                '⚠️ <b>رسوم التسجيل / Registration fee</b>: '
                'Payment received from <b>%s</b> (package: %s) but no '
                'existing membership was found in branch <b>%s</b> to link it to. '
                'Please handle manually.'
            ) % (partner.name, pkg.name, branch.name))
            _logger.info(
                'POS order %s: registration fee paid by %s but no membership '
                'found to link in branch %s.',
                self.name, partner.name, branch.name,
            )

    # ══════════════════════════════════════════════════════════════════════════
    # HELPERS — soft eligibility validation (Feature 4)
    # ══════════════════════════════════════════════════════════════════════════

    def _pos_validate_membership_eligibility(self, pkg, partner, branch, membership):
        """Return a list of bilingual warning HTML strings for this membership.

        This method is intentionally side-effect-free.  The caller posts the
        warnings to the relevant chatters.

        Checks performed:
        1. Age range (only if partner has a date_of_birth).
        2. Required registration fee (if package.requires_registration).
        3. Active/confirmed membership conflict in the same branch.
        """
        warnings = []

        # ── Check 1: Age range ──────────────────────────────────────────────
        if partner.date_of_birth:
            age = partner.age  # stored computed field on res.partner
            if pkg.min_age and age < pkg.min_age:
                warnings.append(
                    'العميل <b>%s</b> عمره %d سنة، أقل من الحد الأدنى %d سنة لهذا الباكدج / '
                    'Customer <b>%s</b> (age %d) is below the minimum age %d for package <b>%s</b>.'
                    % (partner.name, age, pkg.min_age,
                       partner.name, age, pkg.min_age, pkg.name)
                )
            if pkg.max_age and pkg.max_age < 100 and age > pkg.max_age:
                warnings.append(
                    'العميل <b>%s</b> عمره %d سنة، أكبر من الحد الأقصى %d سنة لهذا الباكدج / '
                    'Customer <b>%s</b> (age %d) exceeds the maximum age %d for package <b>%s</b>.'
                    % (partner.name, age, pkg.max_age,
                       partner.name, age, pkg.max_age, pkg.name)
                )

        # ── Check 2: Registration fee prerequisite ──────────────────────────
        if pkg.requires_registration:
            has_reg = self.env['club.membership'].search_count([
                ('partner_id', '=', partner.id),
                ('branch_id', '=', branch.id),
                ('package_id.is_registration_fee', '=', True),
                ('state', 'in', ('confirmed', 'active', 'expired', 'suspended')),
            ])
            if not has_reg:
                warnings.append(
                    'العميل <b>%s</b> لم يدفع رسوم التسجيل المطلوبة لهذا الباكدج / '
                    'Customer <b>%s</b> has not paid the required registration fee '
                    'for package <b>%s</b>. Auto-confirm will fail until this is resolved.'
                    % (partner.name, partner.name, pkg.name)
                )

        # ── Check 3: Active/confirmed membership conflict ───────────────────
        conflict = self.env['club.membership'].search([
            ('partner_id', '=', partner.id),
            ('branch_id', '=', branch.id),
            ('state', 'in', ('confirmed', 'active')),
            ('id', '!=', membership.id),
        ], limit=1)
        if conflict:
            warnings.append(
                'العميل <b>%s</b> عنده اشتراك ساري بالفعل: <b>%s</b> / '
                'Customer <b>%s</b> already has an active membership: '
                '<a href="#" data-oe-model="club.membership" data-oe-id="%d"><b>%s</b></a>.'
                % (partner.name, conflict.name,
                   partner.name, conflict.id, conflict.name)
            )

        return warnings

    # ══════════════════════════════════════════════════════════════════════════
    # HELPERS — auto-confirm (Feature 1)
    # ══════════════════════════════════════════════════════════════════════════

    def _try_auto_confirm(self, membership, partner):
        """Call action_confirm on the membership, catching any business errors.

        The POS payment has already succeeded and cannot be rolled back, so we
        must never let a membership-confirmation failure propagate upward.

        On error: leaves membership in 'draft' and posts a bilingual chatter
        message on the POS order so reception staff can see exactly what
        happened and take over.
        """
        try:
            membership.action_confirm()
            _logger.info(
                'POS order %s: membership %s auto-confirmed successfully.',
                self.name, membership.name,
            )
        except (UserError, ValidationError) as exc:
            msg = str(exc.args[0]) if exc.args else str(exc)
            self.message_post(body=(
                '⚠️ <b>لم يتم التأكيد التلقائي / Could not auto-confirm</b> '
                'membership for <b>%s</b>:<br/>%s<br/>'
                '<i>الرجاء المراجعة اليدوية / Please review and confirm manually.</i>'
            ) % (partner.name, msg))
            _logger.warning(
                'POS order %s: auto-confirm for membership %s failed — %s',
                self.name, membership.name, msg,
            )
        except Exception as exc:
            self.message_post(body=(
                '❌ <b>خطأ غير متوقع / Unexpected error</b> during auto-confirm '
                'for <b>%s</b>: %s'
            ) % (partner.name, exc))
            _logger.error(
                'POS order %s: unexpected error during auto-confirm for %s — %s',
                self.name, membership.name, exc, exc_info=True,
            )

    # ══════════════════════════════════════════════════════════════════════════
    # HELPERS — payment method mapping (Feature 5, replaces Phase 1 version)
    # ══════════════════════════════════════════════════════════════════════════

    def _map_pos_payment_to_membership(self):
        """Map POS payment lines to the membership payment_method selection.

        Phase 2: when the order has split payments, the payment with the
        highest amount determines the method.

        Mapping priority for the dominant payment method:
        1. ``is_cash_count=True``                          → 'cash'
        2. ``use_payment_terminal`` is truthy (card reader) → 'card'
        3. journal type == 'bank'                          → 'transfer'
        4. name contains online/wallet/instapay keywords   → 'online'
        5. default                                         → 'cash'

        TODO Phase 3: remove the _logger.info debug line once stable.
        """
        self.ensure_one()
        if not self.payment_ids:
            return 'cash'

        # Pick the payment with the highest amount (handles split-payment orders)
        main_payment = max(self.payment_ids, key=lambda p: p.amount)
        pm = main_payment.payment_method_id

        if pm.is_cash_count:
            method = 'cash'
        elif pm.use_payment_terminal:
            method = 'card'
        elif pm.journal_id and pm.journal_id.type == 'bank':
            method = 'transfer'
        elif pm.name and any(
            kw in pm.name.lower() for kw in ('online', 'wallet', 'instapay')
        ):
            method = 'online'
        else:
            method = 'cash'

        _logger.info(
            'POS order %s: payment method "%s" (journal type: %s) mapped to "%s".',
            self.name,
            pm.name,
            pm.journal_id.type if pm.journal_id else 'n/a',
            method,
        )
        return method


class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    club_membership_id = fields.Many2one(
        'club.membership',
        string='Created Membership',
        readonly=True,
        copy=False,
        help='The membership created from this POS order line.',
    )
