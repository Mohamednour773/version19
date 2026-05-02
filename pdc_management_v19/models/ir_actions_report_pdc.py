"""Dynamic paperformat override for PDC check printing.

ROOT CAUSE
----------
wkhtmltopdf honours ``--page-width`` / ``--page-height`` CLI flags that Odoo
derives from the ``report.paperformat`` record linked to the action.  Those
CLI flags *override* any CSS ``@page { size: ... }`` directive in the
template, so the hardcoded ``paperformat_pdc_check`` (100 × 210 mm) was
always used regardless of the layout's configured dimensions.

FIX (Option B)
--------------
Inherit ``ir.actions.report``:

1. ``_render_qweb_pdf`` — inspect the incoming record set, compute the
   effective paper dimensions from the linked ``pdc.bank.layout``, and inject
   them into the ORM context before calling ``super()``.

2. ``get_paperformat`` — when the context key ``pdc_paperformat_dims`` is
   present and this is a PDC check-print action, look up (or lazily create)
   a ``report.paperformat`` record that matches those exact dimensions, and
   return it instead of the action's static paperformat.

Thread-safety: context is per-request, so concurrent renders are independent.

Batch-printing note
-------------------
wkhtmltopdf renders a *single* document with one set of CLI page-size flags,
so all pages must share the same physical dimensions.  When printing multiple
checks that span different bank layouts with different dimensions the code
uses the **first check's layout** and logs a warning if mixed dimensions are
detected.  Users should print multi-bank batches as separate jobs when
physical dimensions differ.
"""

import logging

from odoo import _, api, models

_logger = logging.getLogger(__name__)

# Reports managed by this override
_PDC_PRINT_REPORTS = frozenset([
    'pdc_management_v19.report_pdc_check_document',
    'pdc_management_v19.report_pdc_layout_test_document',
])

# Standard paper sizes (width × height) in landscape orientation, mm
_A4_LANDSCAPE = (297.0, 210.0)
_A4_PORTRAIT  = (210.0, 297.0)
_A5_LANDSCAPE = (210.0, 148.0)
_A5_PORTRAIT  = (148.0, 210.0)


class IrActionsReportPDC(models.Model):
    """Mixin onto ir.actions.report to provide per-layout paperformat selection."""

    _inherit = 'ir.actions.report'

    # ── Public override: render entry-point ──────────────────────────────────

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        """Inject dynamic page dimensions before delegating to wkhtmltopdf."""
        # Guard: only intercept when self is a specific report action record
        if self and self.report_name in _PDC_PRINT_REPORTS and res_ids:
            dims = self._pdc_resolve_dims(res_ids)
            if dims:
                width_mm, height_mm = dims
                self_ctx = self.with_context(
                    pdc_paperformat_dims={
                        'width': width_mm,
                        'height': height_mm,
                    }
                )
                _logger.debug(
                    'PDC check print: using %.1f × %.1f mm for report "%s" '
                    '(res_ids=%s).',
                    width_mm, height_mm, self.report_name, res_ids,
                )
                return super(IrActionsReportPDC, self_ctx)._render_qweb_pdf(
                    report_ref, res_ids, data
                )
        return super()._render_qweb_pdf(report_ref, res_ids, data)

    # ── Public override: paperformat selection ───────────────────────────────

    def get_paperformat(self):
        """Return a paperformat whose dimensions match the current render context."""
        dims = self._context.get('pdc_paperformat_dims')
        if dims and self.report_name in _PDC_PRINT_REPORTS:
            return self._pdc_get_or_create_paperformat(
                dims['width'], dims['height']
            )
        return super().get_paperformat()

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _pdc_resolve_dims(self, res_ids):
        """Return (width_mm, height_mm) for the records being printed.

        For ``report_pdc_check_document``   → read the check's bank default layout.
        For ``report_pdc_layout_test_document`` → read the layout directly.

        Returns ``None`` if dimensions cannot be determined (falls back to the
        action's static paperformat).
        """
        if self.report_name == 'pdc_management_v19.report_pdc_check_document':
            return self._pdc_dims_from_checks(res_ids)
        if self.report_name == 'pdc_management_v19.report_pdc_layout_test_document':
            return self._pdc_dims_from_layouts(res_ids)
        return None

    def _pdc_dims_from_checks(self, res_ids):
        """Resolve layout dimensions from a list of pdc.check IDs."""
        checks = self.env['pdc.check'].browse(res_ids)
        dims_seen = []

        for check in checks:
            layout = self._pdc_find_layout_for_check(check)
            if layout:
                dims_seen.append(self._pdc_layout_effective_dims(layout))

        if not dims_seen:
            _logger.debug(
                'PDC check print: no layout found for checks %s — '
                'falling back to static paperformat.',
                res_ids,
            )
            return None

        # Warn when a batch spans layouts with different physical dimensions
        unique_dims = set(dims_seen)
        if len(unique_dims) > 1:
            _logger.warning(
                'PDC check print: batch contains checks with different layout '
                'dimensions %s — using first check\'s layout (%.1f × %.1f mm). '
                'Consider printing each bank\'s checks as a separate job.',
                unique_dims, dims_seen[0][0], dims_seen[0][1],
            )

        return dims_seen[0]

    def _pdc_dims_from_layouts(self, res_ids):
        """Resolve paper dimensions directly from pdc.bank.layout records."""
        layouts = self.env['pdc.bank.layout'].browse(res_ids)
        if not layouts:
            return None
        dims_seen = [self._pdc_layout_effective_dims(lyt) for lyt in layouts]

        unique_dims = set(dims_seen)
        if len(unique_dims) > 1:
            _logger.warning(
                'PDC layout test: batch contains layouts with different '
                'dimensions %s — using first layout (%.1f × %.1f mm).',
                unique_dims, dims_seen[0][0], dims_seen[0][1],
            )

        return dims_seen[0]

    @api.model
    def _pdc_find_layout_for_check(self, check):
        """Return the best matching active layout for a single pdc.check."""
        if not check.bank_id:
            return None
        Layout = self.env['pdc.bank.layout']
        # Prefer: default layout scoped to the check's company
        layout = Layout.search([
            ('bank_id',    '=', check.bank_id.id),
            ('is_default', '=', True),
            ('active',     '=', True),
            ('company_id', '=', check.company_id.id),
        ], limit=1)
        if not layout:
            # Fall back: any default layout for this bank (any company)
            layout = Layout.search([
                ('bank_id',    '=', check.bank_id.id),
                ('is_default', '=', True),
                ('active',     '=', True),
            ], limit=1)
        if not layout:
            # Last resort: any active layout for this bank
            layout = Layout.search([
                ('bank_id', '=', check.bank_id.id),
                ('active',  '=', True),
            ], limit=1)
        return layout or None

    @staticmethod
    def _pdc_layout_effective_dims(layout):
        """Return the effective (width_mm, height_mm) for a layout record.

        Respects ``paper_format`` (a4 / a5 / custom) and ``orientation``.
        """
        fmt = layout.paper_format
        if fmt == 'custom':
            w = layout.paper_width  or 210.0
            h = layout.paper_height or 100.0
            return (w, h)
        if fmt == 'a4':
            return _A4_LANDSCAPE if layout.orientation == 'landscape' else _A4_PORTRAIT
        if fmt == 'a5':
            return _A5_LANDSCAPE if layout.orientation == 'landscape' else _A5_PORTRAIT
        # Fallback: standard bank check size
        return (210.0, 100.0)

    def _pdc_get_or_create_paperformat(self, width_mm, height_mm):
        """Return (creating if needed) a report.paperformat for the given dimensions.

        Paperformats are shared across renders — we search by the generated
        name before creating to avoid DB bloat on high-volume print queues.
        The record is created with ``sudo()`` because ``report.paperformat``
        requires admin rights to write.
        """
        # Normalise to 1 decimal place to avoid floating-point noise
        w = round(width_mm, 1)
        h = round(height_mm, 1)
        pf_name = 'PDC Check Paper %gx%g mm' % (w, h)

        PaperFormat = self.env['report.paperformat'].sudo()
        pf = PaperFormat.search([('name', '=', pf_name)], limit=1)
        if not pf:
            pf = PaperFormat.create({
                'name':            pf_name,
                'format':          'custom',
                'page_width':      w,
                'page_height':     h,
                # wkhtmltopdf treats width as the longer dimension in landscape
                # mode; since we want the PDF to respect @page orientation we
                # always specify exact width × height and let CSS @page handle
                # the visual rotation.
                'orientation':     'Landscape',
                'margin_top':      0,
                'margin_bottom':   0,
                'margin_left':     0,
                'margin_right':    0,
                'header_line':     False,
                'header_spacing':  0,
                'dpi':             96,
            })
            _logger.info(
                'PDC check print: created paperformat "%s" (%.1f × %.1f mm).',
                pf_name, w, h,
            )
        return pf
