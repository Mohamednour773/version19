import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class PDCCheckCronMethods(models.Model):
    """Cron-job methods for pdc.check — separated to keep pdc_check.py manageable.

    Three daily scheduled jobs:
      1. _cron_send_due_reminders()          — email reminder per company thresholds
      2. _cron_detect_overdue_under_collection() — log / notify stuck deposits
    """
    _inherit = 'pdc.check'

    # ── Cron 1: Due-Date Reminders ────────────────────────────────────────────

    @api.model
    def _cron_send_due_reminders(self):
        """Send due-date reminder emails based on company alert thresholds.

        Respects per-company settings:
          pdc_alert_days_first  (default  3 days)
          pdc_alert_days_second (default  7 days)
          pdc_alert_days_third  (default 15 days)

        Only checks in 'registered' (received) or 'under_collection' are included.
        Guarantee checks are excluded — they have no cash-flow impact until activated.
        A check is reminded only on the exact day that matches a threshold window
        to prevent duplicate reminders on consecutive days.
        """
        template = self.env.ref(
            'pdc_management_v19.mail_template_pdc_due_soon', raise_if_not_found=False,
        )
        if not template:
            _logger.warning(
                'PDC due-soon template (mail_template_pdc_due_soon) not found — '
                'skipping reminder cron.'
            )
            return

        today = fields.Date.today()

        for company in self.env['res.company'].search([]):
            thresholds = [
                company.pdc_alert_days_first or 3,
                company.pdc_alert_days_second or 7,
                company.pdc_alert_days_third or 15,
            ]
            # De-duplicate thresholds, drop zeroes (disabled reminders)
            active_thresholds = sorted({d for d in thresholds if d > 0})
            if not active_thresholds:
                continue

            max_days = max(active_thresholds)
            domain = [
                ('company_id', '=', company.id),
                ('state', 'in', ['registered', 'under_collection']),
                ('check_type', 'not in', ['guarantee_received', 'guarantee_issued']),
                ('due_date', '>=', today),
                ('due_date', '<=', fields.Date.add(today, days=max_days)),
            ]
            checks = self.search(domain)

            sent = 0
            for check in checks:
                days_to_due = (check.due_date - today).days
                # Only remind on the exact threshold day
                if days_to_due not in active_thresholds:
                    continue
                try:
                    template.with_context(days_to_due=days_to_due).send_mail(
                        check.id,
                        force_send=False,
                        raise_exception=False,
                    )
                    sent += 1
                    _logger.info(
                        'PDC due reminder queued: %s (due in %d day(s), company %s).',
                        check.name, days_to_due, company.name,
                    )
                except Exception as exc:
                    _logger.error(
                        'Failed to queue due reminder for check %s: %s',
                        check.name, exc,
                    )

            if sent:
                _logger.info(
                    'PDC due-reminder cron: %d email(s) queued for company "%s".',
                    sent, company.name,
                )

    # ── Cron 2: Overdue Under-Collection Detection ────────────────────────────

    @api.model
    def _cron_detect_overdue_under_collection(self):
        """Log checks stuck in under_collection past their due date.

        Does NOT auto-bounce — that requires deliberate user action to record the
        bounce reason, charges, and journal entry correctly.  This cron only raises
        visibility through the server log so operations teams can act.

        Design decision (v1.0.0): log-only.  A dedicated "overdue under-collection"
        mail template was considered but not added to v1 to avoid sending
        misleading "due soon" emails for checks that are already overdue.
        Per-check notification for overdue deposits can be added in v1.1 with
        a purpose-built template.
        """
        today = fields.Date.today()
        domain = [
            ('state', '=', 'under_collection'),
            ('due_date', '<', today),
        ]
        overdue = self.search(domain)

        if not overdue:
            _logger.debug('PDC overdue-collection cron: no overdue checks found.')
            return

        # Log check names so ops teams can identify them without querying the DB
        check_names = ', '.join(overdue.mapped('name')[:20])
        if len(overdue) > 20:
            check_names += _(' … and %d more', len(overdue) - 20)

        _logger.warning(
            'PDC overdue-collection cron: %d check(s) are past due date '
            'and still in "Under Collection" state. Manual review required. '
            'Checks: %s',
            len(overdue), check_names,
        )


class PDCCheckBookCronMethods(models.Model):
    """Cron-job method for pdc.check.book — daily low-stock alert."""
    _inherit = 'pdc.check.book'

    # ── Cron 3: Check Book Low-Stock Alert ────────────────────────────────────

    @api.model
    def _cron_check_book_low_stock(self):
        """Send email alert for active check books that have fallen below threshold.

        Only books in 'active' state with available_checks > 0 (not yet fully
        depleted) but <= low_stock_threshold are alerted.  Books already in
        'depleted' state generate their own warning at the point of depletion.
        """
        template = self.env.ref(
            'pdc_management_v19.mail_template_pdc_book_low', raise_if_not_found=False,
        )
        if not template:
            _logger.warning(
                'PDC book-low template (mail_template_pdc_book_low) not found — '
                'skipping low-stock cron.'
            )
            return

        # filtered() keeps only those where low_stock_alert is True
        # (available_checks <= low_stock_threshold and state == 'active')
        low_books = self.search(
            [('state', '=', 'active'), ('available_checks', '>', 0)]
        ).filtered(lambda b: b.low_stock_alert)

        if not low_books:
            _logger.debug('PDC check-book low-stock cron: no books below threshold.')
            return

        _logger.info(
            'PDC check-book low-stock cron: %d book(s) below threshold.',
            len(low_books),
        )

        for book in low_books:
            try:
                template.send_mail(
                    book.id,
                    force_send=False,
                    raise_exception=False,
                )
                _logger.info(
                    'Low-stock alert queued for check book "%s" '
                    '(%d / %d checks remaining).',
                    book.name, book.available_checks, book.total_checks,
                )
            except Exception as exc:
                _logger.error(
                    'Failed to send low-stock alert for book %s: %s',
                    book.name, exc,
                )
