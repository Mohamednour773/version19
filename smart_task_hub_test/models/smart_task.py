# -*- coding: utf-8 -*-
import json
import logging
import re
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SmartTask(models.Model):
    _name        = 'smart.task'
    _description = 'Smart Task Hub'
    _inherit     = ['mail.thread', 'mail.activity.mixin']
    _order       = 'priority_level asc, create_date desc'

    # ── Basic Info ────────────────────────────────────────────────
    name        = fields.Char('Task Title', required=True, tracking=True)
    description = fields.Html('Task Description', required=True)
    client_id   = fields.Many2one('res.partner', 'Client', required=True, tracking=True)
    project_id  = fields.Many2one('project.project', 'Project', tracking=True)
    assigned_to = fields.Many2one('res.users', 'Assigned To', tracking=True)
    helpdesk_ticket_id = fields.Many2one('helpdesk.ticket', 'Linked Helpdesk Ticket')
    project_task_id    = fields.Many2one('project.task', 'Linked Project Task')

    # ── Priority & Classification ─────────────────────────────────
    priority_level = fields.Selection([
        ('1_critical', '🔴 Critical'),
        ('2_high',     '🟠 High'),
        ('3_medium',   '🟡 Medium'),
        ('4_low',      '🟢 Low'),
    ], string='Priority', default='3_medium', tracking=True)

    priority_score = fields.Integer('Priority Score (0-100)', default=50, tracking=True)

    odoo_module = fields.Selection([
        ('accounting',    'Accounting & Finance'),
        ('inventory',     'Inventory & Warehouse'),
        ('manufacturing', 'Manufacturing (MRP)'),
        ('sales',         'Sales & CRM'),
        ('purchase',      'Purchase'),
        ('hr',            'HR & Payroll'),
        ('project',       'Project Management'),
        ('ecommerce',     'eCommerce & Website'),
        ('pos',           'Point of Sale'),
        ('fleet',         'Fleet'),
        ('maintenance',   'Maintenance'),
        ('quality',       'Quality'),
        ('other',         'Other / General'),
    ], string='Odoo Module', tracking=True)

    task_type = fields.Selection([
        ('bug',           '🐛 Bug / Error'),
        ('config',        '⚙️ Configuration'),
        ('customization', '🔧 Customization Request'),
        ('training',      '📚 Training'),
        ('consulting',    '💼 Consulting'),
        ('gap_analysis',  '📊 Gap Analysis'),
        ('integration',   '🔗 Integration'),
        ('upgrade',       '⬆️ Upgrade / Migration'),
    ], string='Task Type', tracking=True)

    solution_type = fields.Selection([
        ('config_change',  'Configuration Change'),
        ('process_fix',    'Process / Workflow Fix'),
        ('custom_dev',     'Custom Development'),
        ('training',       'Training Required'),
        ('standard_odoo',  'Standard Odoo Feature'),
        ('third_party',    'Third-Party Module'),
    ], string='Solution Type', tracking=True)

    root_cause = fields.Selection([
        ('configuration', 'Configuration Issue'),
        ('user_error',    'User / Training Issue'),
        ('workflow',      'Workflow Design Issue'),
        ('code_bug',      'Code / Technical Bug'),
        ('data_issue',    'Data Quality Issue'),
        ('integration',   'Integration Issue'),
        ('requirements',  'Unclear Requirements'),
    ], string='Root Cause', tracking=True)

    assignment_type = fields.Selection([
        ('functional', '👤 Functional Consultant'),
        ('developer',  '💻 Developer'),
        ('support',    '🎧 Support Agent'),
        ('architect',  '🏗️ Solution Architect'),
        ('manager',    '📋 Project Manager'),
    ], string='Assignment Type', tracking=True)

    complexity = fields.Selection([
        ('easy',   '🟢 Easy'),
        ('medium', '🟡 Medium'),
        ('hard',   '🔴 Hard'),
    ], string='Complexity', tracking=True)

    # ── Effort & Risk ─────────────────────────────────────────────
    effort_estimate = fields.Float('Effort (Hours)', tracking=True)
    effort_category = fields.Selection([
        ('quick',   'Quick Fix (< 2h)'),
        ('short',   'Short (2–8h)'),
        ('medium',  'Medium (1–3 days)'),
        ('large',   'Large (3–10 days)'),
        ('project', 'Full Project (> 10 days)'),
    ], string='Effort Category', tracking=True)

    risk_level = fields.Selection([
        ('low',      '🟢 Low Risk'),
        ('medium',   '🟡 Medium Risk'),
        ('high',     '🔴 High Risk'),
        ('critical', '☠️ Critical Risk'),
    ], string='Risk Level', tracking=True)
    risk_flags = fields.Text('Risk Details')

    sla_hours          = fields.Float('SLA (Hours)', tracking=True)
    escalation_rule    = fields.Char('Escalation Rule')

    # ── AI Analysis Fields ────────────────────────────────────────
    ai_status = fields.Selection([
        ('pending',   '⏳ Pending Analysis'),
        ('analyzing', '🔄 Analyzing...'),
        ('reviewed',  '✅ AI Reviewed'),
        ('failed',    '❌ Failed'),
    ], string='AI Status', default='pending', tracking=True)

    gpt_analysis          = fields.Html('GPT Analysis')
    gpt_solution          = fields.Html('GPT Solution')
    claude_review         = fields.Html('Claude Review & Audit')
    ai_summary            = fields.Html('AI Executive Summary')
    client_communication  = fields.Html('Client Response Template')
    test_cases            = fields.Html('Suggested Test Cases')
    gap_analysis_notes    = fields.Html('Gap Analysis Notes')
    auto_fix_suggestions  = fields.Html('⚡ Auto Fix Suggestions')
    kb_entry              = fields.Html('📚 KB Entry Draft')

    # ── Duplicate & KB ────────────────────────────────────────────
    duplicate_ids = fields.Many2many(
        'smart.task', 'smart_task_duplicate_rel',
        'task_id', 'duplicate_id',
        string='Similar/Duplicate Tasks'
    )
    is_duplicate_flagged = fields.Boolean('Duplicate Flagged', default=False)
    similar_kb_ids       = fields.Many2many(
        'smart.knowledge.base', 'smart_task_kb_rel',
        'task_id', 'kb_id',
        string='Similar KB Articles'
    )
    knowledge_base_id    = fields.Many2one('smart.knowledge.base', 'Saved KB Article')

    # ── State ─────────────────────────────────────────────────────
    state = fields.Selection([
        ('draft',       '📝 Draft'),
        ('in_analysis', '🔍 In Analysis'),
        ('in_progress', '⚙️ In Progress'),
        ('review',      '👁️ Review'),
        ('done',        '✅ Done'),
        ('cancelled',   '❌ Cancelled'),
    ], string='Status', default='draft', tracking=True)

    analysis_date  = fields.Datetime('Last Analyzed')
    resolution_date = fields.Datetime('Resolution Date')

    # u2500u2500 Voice & Screenshot u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500u2500
    screenshot_image    = fields.Binary('Screenshot', attachment=True)
    screenshot_filename = fields.Char('Screenshot Filename')
    screenshot_analysis = fields.Text('Screenshot Analysis (GPT-4V)')
    voice_input_control = fields.Char(
        string='Voice Input',
        compute='_compute_voice_dummy',
        store=False,
    )

    # ── Computed ──────────────────────────────────────────────────
    color = fields.Integer('Color', compute='_compute_color')

    @api.depends('priority_level')
    def _compute_color(self):
        mapping = {'1_critical': 1, '2_high': 2, '3_medium': 3, '4_low': 10}
        for rec in self:
            rec.color = mapping.get(rec.priority_level, 3)

    # ── Onchange ──────────────────────────────────────────────────
    @api.onchange('project_id')
    def _onchange_project_id(self):
        if self.project_id and self.project_id.partner_id:
            self.client_id = self.project_id.partner_id

    # ── Create Trigger ────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            rec._check_duplicates()
            rec._find_similar_kb()
            if self.env['ir.config_parameter'].sudo().get_param(
                    'smart_task_hub_test.auto_analyze', 'True') == 'True':
                rec.sudo().action_analyze_with_ai()
        return records

    # ── Duplicate Detection ───────────────────────────────────────
    def _check_duplicates(self):
        if not self.description:
            return
        plain = re.sub('<[^<]+?>', '', self.description or '').lower()
        words = set(w for w in plain.split() if len(w) > 4)
        if not words:
            return
        existing = self.search([
            ('id', '!=', self.id),
            ('client_id', '=', self.client_id.id),
            ('state', 'not in', ['done', 'cancelled']),
        ])
        similar = []
        for task in existing:
            task_plain = re.sub('<[^<]+?>', '', task.description or '').lower()
            task_words = set(w for w in task_plain.split() if len(w) > 4)
            if words and task_words:
                overlap = len(words & task_words) / max(len(words), len(task_words))
                if overlap > 0.4:
                    similar.append(task.id)
        if similar:
            self.duplicate_ids = [(6, 0, similar)]
            self.is_duplicate_flagged = True
            self.message_post(
                body=_('<b>⚠️ Possible Duplicate Detected!</b> Similar open tasks exist for this client.'),
                message_type='notification'
            )

    def _find_similar_kb(self):
        """Find KB articles similar to this task and link them."""
        if not self.description:
            return
        plain = re.sub('<[^<]+?>', '', self.description or '')
        similar = self.env['smart.knowledge.base'].find_similar(plain, limit=3)
        if similar:
            self.similar_kb_ids = [(6, 0, similar.ids)]
            self.message_post(
                body=_('<b>📚 %d Similar KB Articles Found!</b> Check the KB tab for reusable solutions.') % len(similar),
                message_type='notification'
            )

    # ── AI Analysis Entry Point ───────────────────────────────────
    def action_analyze_with_ai(self):
        """3-phase AI analysis: Diagnose > Solve > Audit."""
        self.ensure_one()
        self.write({'ai_status': 'analyzing', 'state': 'in_analysis'})
        try:
            gateway = self.env['smart.ai.gateway']
            task_context = self._build_task_context()

            # Phase 1: Diagnose
            self.message_post(body=_('<b>Phase 1: Diagnosing...</b>'), message_type='notification')
            phase1_raw = gateway.call_gpt_phase1_diagnose(task_context)
            self._parse_phase1_result(phase1_raw)

            # Phase 2: Solve
            self.message_post(body=_('<b>Phase 2: Building Solution...</b>'), message_type='notification')
            diagnosis_summary = self._build_diagnosis_summary(phase1_raw)
            phase2_raw = gateway.call_gpt_phase2_solve(task_context, diagnosis_summary)
            self._parse_phase2_result(phase2_raw)

            # Phase 3: Claude Audit (only if API key configured)
            anthropic_key = self.env['ir.config_parameter'].sudo().get_param(
                'smart_task_hub_test.anthropic_api_key', '')
            if anthropic_key:
                self.message_post(body=_('<b>Phase 3: Claude Auditing...</b>'), message_type='notification')
                claude_prompt = self._build_claude_audit_prompt(phase1_raw, phase2_raw)
                claude_result = gateway.call_claude(claude_prompt)
                self._parse_claude_result(claude_result)
            else:
                self.claude_review = (
                    '<p><em>Claude audit skipped - Anthropic API key not configured. '
                    'Go to Smart Task Hub &gt; Settings to add it.</em></p>'
                )

            self.write({
                'ai_status': 'reviewed',
                'analysis_date': fields.Datetime.now(),
                'state': 'in_progress',
            })
            self._save_to_knowledge_base()
            self.message_post(
                body=_('<b>AI Analysis Complete (3 Phases)</b><br/>'
                       'Priority: %s | Score: %s/100 | Module: %s | Effort: %s hrs') % (
                    dict(self._fields['priority_level'].selection).get(self.priority_level, ''),
                    self.priority_score,
                    self.odoo_module or 'Unknown',
                    self.effort_estimate or '?'
                ),
                message_type='notification'
            )
        except Exception as e:
            _logger.exception("AI Analysis failed for task %s", self.id)
            self.write({'ai_status': 'failed'})
            self.message_post(
                body=_('<b>AI Analysis Failed:</b> %s') % str(e),
                message_type='notification'
            )

    # ── Task Context Builder ─────────────────────────────────────
    def _build_task_context(self):
        """Build a clean task context string for AI phases."""
        plain_desc = re.sub('<[^<]+?>', '', self.description or '').strip()

        # ── Screenshot Analysis — highest priority section ─────────
        screenshot_section = ''
        if self.screenshot_analysis:
            screenshot_section = (
                '\n\n'
                '════════════════════════════════════════\n'
                'SCREENSHOT ANALYSIS (GPT-4V) — READ THIS FIRST:\n'
                '════════════════════════════════════════\n'
                + self.screenshot_analysis.strip() +
                '\n════════════════════════════════════════\n'
                'NOTE: The above is extracted VERBATIM from the actual screenshot.\n'
                'Base your diagnosis on these exact error messages and field values.\n'
                '════════════════════════════════════════'
            )

        kb_context = ''
        if self.similar_kb_ids:
            kb_context = '\n\nSIMILAR KB ARTICLES (reuse if applicable):\n'
            for kb in self.similar_kb_ids[:2]:
                kb_context += f'- [{kb.odoo_module}] {kb.name}: {(kb.problem_description or "")[:200]}\n'

        return (
            f"Client: {self.client_id.name}\n"
            f"Project: {self.project_id.name if self.project_id else 'Not specified'}\n"
            f"Title: {self.name}\n"
            f"Description: {plain_desc}\n"
            f"Odoo Version: {self.env['ir.config_parameter'].sudo().get_param('smart_task_hub_test.odoo_version', 'Odoo 19')}"
            f"{screenshot_section}"
            f"{kb_context}"
        )

    def _build_diagnosis_summary(self, phase1_raw):
        """Extract key info from phase 1 JSON for phase 2 prompt."""
        try:
            import re as _re
            cleaned = phase1_raw.strip()
            if cleaned.startswith('`'):
                cleaned = _re.sub(r'^```(?:json)?\s*', '', cleaned, flags=_re.MULTILINE)
                cleaned = _re.sub(r'```\s*$', '', cleaned, flags=_re.MULTILINE).strip()
            match = _re.search(r'\{.*\}', cleaned, _re.DOTALL)
            if not match:
                return phase1_raw[:1000]
            data = json.loads(match.group())
            rca = data.get('root_cause_analysis', [])
            top_cause = rca[0] if rca else {}
            return (
                f"Priority: {data.get('priority_level','3_medium')} (Score: {data.get('priority_score',50)})\n"
                f"Module: {data.get('odoo_module','other')}\n"
                f"Task Type: {data.get('task_type','consulting')}\n"
                f"Complexity: {data.get('complexity','medium')}\n"
                f"Effort: {data.get('effort_hours',4)} hrs\n"
                f"Risk: {data.get('risk_level','low')}\n"
                f"SLA: {data.get('sla_hours',24)} hrs\n"
                f"Problem: {data.get('problem_summary','')}\n"
                f"Top Hypothesis: {top_cause.get('cause','')} (confidence: {top_cause.get('confidence',0)}%)\n"
                f"Verification: {top_cause.get('verification','')}\n"
                f"Final Diagnosis: {data.get('final_diagnosis','')}\n"
                f"Needs Excel: {data.get('needs_excel_output', False)}\n"
                f"Excel Details: {data.get('excel_description','')}"
            )
        except Exception:
            return phase1_raw[:1000]

    def _build_claude_audit_prompt(self, phase1_raw, phase2_raw):
        """Build the combined prompt for Claude to audit both phases."""
        plain_desc = re.sub('<[^<]+?>', '', self.description or '')
        return (
            f"ORIGINAL TASK:\n"
            f"Client: {self.client_id.name}\n"
            f"Title: {self.name}\n"
            f"Description: {plain_desc}\n\n"
            f"PHASE 1 - DIAGNOSIS (GPT):\n{phase1_raw[:2000]}\n\n"
            f"PHASE 2 - SOLUTION (GPT):\n{phase2_raw[:2000]}\n\n"
            f"AUDIT INSTRUCTIONS:\n"
            f"1. Check if client_communication uses the real client name: {self.client_id.name}\n"
            f"2. Check if auto_fix_suggestions have FULL menu paths (not generic)\n"
            f"3. Check if test_cases have specific values and navigation paths\n"
            f"4. Check if safe_solution steps are executable without follow-up questions\n"
            f"5. For AVCO/costing issues: verify stock.valuation.layer was checked\n"
            f"Provide your audit review now."
        )

    # ── Phase Result Parsers ──────────────────────────────────────
    def _parse_phase1_result(self, raw):
        """Parse Phase 1 (Diagnose) JSON and fill classification fields."""
        try:
            cleaned = raw.strip()
            if cleaned.startswith('`'):
                cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.MULTILINE)
                cleaned = re.sub(r'```\s*$', '', cleaned, flags=re.MULTILINE).strip()
            match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if not match:
                raise ValueError("No JSON in phase 1 response")
            data = json.loads(match.group())

            # Build root cause HTML
            rca_raw = data.get('root_cause_analysis', [])
            rca_html = '<div style="margin:12px 0;">'
            if isinstance(rca_raw, list):
                for i, h in enumerate(rca_raw, 1):
                    conf = int(h.get('confidence', 0))
                    bg = '#eafaf1' if conf >= 70 else '#fef9e7' if conf >= 40 else '#f9f9f9'
                    bc = '#27ae60' if conf >= 70 else '#f39c12' if conf >= 40 else '#bdc3c7'
                    tc = '#27ae60' if conf >= 70 else '#e67e22' if conf >= 40 else '#7f8c8d'
                    rca_html += (
                        f'<div style="background:{bg};border-left:4px solid {bc};'
                        f'padding:12px 16px;margin-bottom:10px;border-radius:0 6px 6px 0;">'
                        f'<div style="display:flex;justify-content:space-between;margin-bottom:6px;">'
                        f'<strong>Hypothesis {i}: {h.get("cause","")}</strong>'
                        f'<span style="background:{tc};color:white;padding:2px 10px;'
                        f'border-radius:12px;font-size:12px;font-weight:bold;">{conf}%</span>'
                        f'</div>'
                        f'<p style="margin:4px 0;color:#34495e;">{h.get("explanation","")}</p>'
                        f'<p style="margin:4px 0;font-size:12px;color:#7f8c8d;">'
                        f'<strong>Verify:</strong> {h.get("verification","")}</p>'
                        f'</div>'
                    )
            rca_html += '</div>'

            # Confidence badges
            conf_score = int(data.get('confidence_score', 0))
            conf_color = '#27ae60' if conf_score >= 75 else '#e67e22' if conf_score >= 50 else '#c0392b'
            smart = data.get('smart_summary', {})
            smart_html = ''
            if isinstance(smart, dict):
                smart_html = (
                    f'<div style="background:#f8f9fa;border-radius:8px;padding:14px;margin-bottom:14px;">'
                    f'<p><strong>Issue:</strong> {smart.get("issue","")}</p>'
                    f'<p><strong>Root Cause:</strong> {smart.get("root_cause","")}</p>'
                    f'<p><strong>Solution:</strong> {smart.get("solution","")}</p>'
                    f'</div>'
                )

            gpt_analysis_html = (
                f'<div style="text-align:center;margin:12px 0 18px;">'
                f'<span style="background:{conf_color};color:white;padding:6px 16px;'
                f'border-radius:20px;font-weight:bold;font-size:13px;">'
                f'Diagnosis Confidence: {conf_score}%</span>'
                f'</div>'
                + smart_html
                + f'<p>{data.get("problem_summary","")}</p>'
                + '<h4>Root Cause Analysis</h4>' + rca_html
                + f'<h4>Final Diagnosis</h4><p>{data.get("final_diagnosis","")}</p>'
                + (f'<h4>Risk Flags</h4><p>{data.get("risk_flags","")}</p>'
                   if data.get("risk_flags") else '')
            )

            self.write({
                'priority_level': data.get('priority_level', '3_medium'),
                'priority_score': conf_score or int(data.get('priority_score', 50)),
                'odoo_module': data.get('odoo_module', 'other'),
                'task_type': data.get('task_type', 'consulting'),
                'root_cause': data.get('root_cause', 'requirements'),
                'solution_type': data.get('solution_type', 'standard_odoo'),
                'assignment_type': data.get('assignment_type', 'functional'),
                'complexity': data.get('complexity', 'medium'),
                'effort_estimate': float(data.get('effort_hours', 4)),
                'effort_category': data.get('effort_category', 'short'),
                'risk_level': data.get('risk_level', 'low'),
                'risk_flags': data.get('risk_flags', ''),
                'sla_hours': float(data.get('sla_hours', 24)),
                'escalation_rule': data.get('escalation_rule', ''),
                'gpt_analysis': gpt_analysis_html,
            })
            self._auto_assign()

        except (json.JSONDecodeError, ValueError) as e:
            _logger.error("Phase 1 parse error: %s", e)
            self.write({'gpt_analysis': f'<p><strong>Parse Error Phase 1:</strong> {e}</p><pre>{raw[:2000]}</pre>'})

    def _parse_phase2_result(self, raw):
        """Parse Phase 2 (Solve) JSON and fill solution fields."""
        try:
            cleaned = raw.strip()
            if cleaned.startswith('`'):
                cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.MULTILINE)
                cleaned = re.sub(r'```\s*$', '', cleaned, flags=re.MULTILINE).strip()
            match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if not match:
                raise ValueError("No JSON in phase 2 response")
            data = json.loads(match.group())

            sol_conf = int(data.get('solution_confidence', 0))
            sol_conf_color = '#27ae60' if sol_conf >= 75 else '#e67e22' if sol_conf >= 50 else '#c0392b'

            solution_html = (
                f'<div style="text-align:center;margin:12px 0 18px;">'
                f'<span style="background:{sol_conf_color};color:white;padding:6px 16px;'
                f'border-radius:20px;font-weight:bold;font-size:13px;">'
                f'Solution Confidence: {sol_conf}%</span>'
                f'</div>'
                + '<h4>Safe Solution</h4>' + data.get('safe_solution', '')
                + '<h4>Alternative Solution</h4>' + data.get('alternative_solution', '')
                + ('<h4>Risky Solution (Last Resort)</h4>' + data.get('risky_solution', '')
                   if data.get('risky_solution') else '')
                + ('<h4>SLA & Escalation</h4>' + data.get('sla_detail', '')
                   if data.get('sla_detail') else '')
                + '<h4>Validation Steps</h4>' + data.get('validation_steps', '')
                + ('<h4>Best Practice</h4>' + data.get('best_practice', '')
                   if data.get('best_practice') else '')
            )

            auto_fix_raw = data.get('auto_fix_suggestions', [])
            auto_fix_html = ''
            if isinstance(auto_fix_raw, list) and auto_fix_raw:
                auto_fix_html = '<p><strong>Quick Actions:</strong></p><ul>' + ''.join(
                    f'<li>{a}</li>' for a in auto_fix_raw
                ) + '</ul>'
            rec = data.get('recommended_actions', [])
            if rec:
                auto_fix_html += '<p><strong>Recommended Actions:</strong></p><ol>' + ''.join(
                    f'<li>{a}</li>' for a in rec
                ) + '</ol>'

            if data.get('customization_needed'):
                auto_fix_html += (
                    f'<h4>Customization Required</h4>'
                    f'<p>{data.get("customization_detail","")}</p>'
                )

            # Fix client name placeholder if AI used [Client] instead of real name
            client_comm = data.get('client_communication', '')
            client_comm = client_comm.replace('[Client]', self.client_id.name)
            client_comm = client_comm.replace('[USE ACTUAL CLIENT NAME FROM TASK]', self.client_id.name)
            client_comm = client_comm.replace('[client]', self.client_id.name)

            self.write({
                'gpt_solution': solution_html,
                'auto_fix_suggestions': auto_fix_html,
                'test_cases': data.get('test_cases', ''),
                'client_communication': client_comm,
                'gap_analysis_notes': data.get('gap_analysis', ''),
                'kb_entry': data.get('kb_entry', ''),
            })

        except (json.JSONDecodeError, ValueError) as e:
            _logger.error("Phase 2 parse error: %s", e)
            self.write({'gpt_solution': f'<p><strong>Parse Error Phase 2:</strong> {e}</p><pre>{raw[:2000]}</pre>'})

        # ── Prompt Builders ───────────────────────────────────────────
    def _build_gpt_prompt(self):
        plain_desc = re.sub('<[^<]+?>', '', self.description or '')

        # Include similar KB context if available
        kb_context = ''
        if self.similar_kb_ids:
            kb_context = '\n\nSIMILAR KB ARTICLES FOUND (reuse if applicable):\n'
            for kb in self.similar_kb_ids[:2]:
                kb_context += f'- [{kb.odoo_module}] {kb.name}: {(kb.problem_description or "")[:200]}\n'

        return f"""You are NOT a general assistant.
You are an ELITE AI CONSULTANT ENGINE specialized in Odoo ERP, acting as a senior expert team.
You combine: Senior Odoo Functional Consultant, Senior Technical Developer,
Accounting & Costing Expert, Inventory & MRP Specialist, POS Expert, Support Lead, AI Systems Thinker.

YOUR CORE OBJECTIVE:
- Diagnose issues with HIGH accuracy
- Validate before suggesting solutions — NEVER assume
- Show confidence levels for every conclusion
- Act like a senior consultant, not a chatbot
- If uncertain → say it clearly, never hallucinate

TASK TO ANALYZE:
- Client: {self.client_id.name}
- Project: {self.project_id.name if self.project_id else 'Not specified'}
- Title: {self.name}
- Description: {plain_desc}
{kb_context}

IMAGE ANALYSIS RULE: If the description contains screenshot references or error text extracted from UI,
analyze every visible element: error messages, field values, button states, missing elements.
Never guess — only state what is visible or strongly inferred.

RESPOND WITH RAW JSON ONLY. Start with {{ and end with }}.
NO ```json blocks. NO text before or after. NO markdown.

JSON STRUCTURE (every field required):
{{
  "priority_level": "1_critical|2_high|3_medium|4_low",
  "priority_score": 75,
  "priority_score_reason": "Score breakdown: business_impact/40 + urgency/30 + blocking/20 + financial/10",
  "odoo_module": "accounting|inventory|manufacturing|sales|purchase|hr|project|ecommerce|pos|fleet|maintenance|quality|other",
  "task_type": "bug|config|customization|training|consulting|gap_analysis|integration|upgrade",
  "root_cause": "configuration|user_error|workflow|code_bug|data_issue|integration|requirements",
  "solution_type": "config_change|process_fix|custom_dev|training|standard_odoo|third_party",
  "assignment_type": "functional|developer|support|architect|manager",
  "assignment_reason": "Which roles needed and WHY each one specifically",
  "complexity": "easy|medium|hard",
  "effort_hours": 4.0,
  "effort_category": "quick|short|medium|large|project",
  "risk_level": "low|medium|high|critical",
  "sla_hours": 8.0,
  "escalation_rule": "If not resolved in X hours → notify [exact role]",
  "confidence_score": 85,
  "solution_confidence": 80,

  "problem_summary": "1-2 sentences: exactly what is broken and business impact. No copy of description.",

  "functional_analysis": "<p><strong>Business Impact:</strong> [who is affected, financial risk, operational disruption]</p><p><strong>Affected Modules:</strong> [list with reason each is affected]</p>",

  "image_analysis": {{
    "used": false,
    "findings": "No image provided OR: [exactly what is visible: error text, field values, UI state]",
    "confidence": "low|medium|high"
  }},

  "root_cause_analysis": [
    {{
      "cause": "Hypothesis 1 — [type: Data/Config/Code/User/Access/Cache/Customization]",
      "explanation": "Why this could cause the issue — technical mechanism",
      "confidence": 85,
      "verification": "Exact steps to verify: Module → Menu → Field/Report → what to look for"
    }},
    {{
      "cause": "Hypothesis 2 — [type]",
      "explanation": "Why this could cause the issue",
      "confidence": 60,
      "verification": "Exact verification steps"
    }},
    {{
      "cause": "Hypothesis 3 — [type]",
      "explanation": "Why this could cause the issue",
      "confidence": 40,
      "verification": "Exact verification steps"
    }}
  ],

  "final_diagnosis": "<p><strong>Most Likely Cause:</strong> [Hypothesis X with confidence %]</p><p><strong>Justification:</strong> [why this is most likely based on evidence — not assumption]</p><p><strong>stock.move vs SVL level:</strong> [if inventory: exactly which model is corrupted and which fields]</p><p><strong>Costing Method Impact:</strong> [AVCO/FIFO/Standard exact formula distortion if applicable]</p><p><strong>Accounting Entry Effect:</strong> [DR/CR account numbers affected if applicable]</p>",

  "solution_validation": {{
    "is_verified": true,
    "reason": "Why this solution is reliable and has been tested in similar scenarios",
    "risk_level": "low|medium|high"
  }},

  "proposed_solution": {{
    "safe_solution": "<p><strong>Fix Type: [Configuration|Data Fix|Process Fix|Customization]</strong></p><p>⚠️ Take database backup before proceeding.</p><ol><li>[Full menu: Module → Sub-menu → Page → Field → exact value]</li><li>[Every step executable without asking follow-up questions]</li></ol><p><strong>POST-FIX:</strong></p><ol><li>[Exact test → expected result]</li></ol>",
    "alternative_solution": "<p>[Safer fallback if main fix is risky]</p>",
    "risky_solution": "<p><strong>⚠️ USE ONLY IF NECESSARY:</strong> [High-risk fix with clear warnings]</p>"
  }},

  "customization_suggestion": {{
    "needed": false,
    "reason": "[Why standard Odoo is not enough — or why it IS enough]",
    "suggested_solution": "[What the customization should do — or N/A]",
    "complexity": "easy|medium|hard"
  }},

  "auto_fix_suggestions": [
    "Quick fix 1: [exact action — e.g. Inventory → Configuration → Settings → enable X]",
    "Quick fix 2: [exact action]",
    "Quick fix 3: [exact action]"
  ],

  "smart_summary": {{
    "issue": "1-line problem statement",
    "root_cause": "1-line technical cause",
    "solution": "1-line fix approach"
  }},

  "issue_summary": "<p><strong>Business Impact:</strong> [what breaks + who affected + financial risk]</p><p><strong>Affected Modules:</strong> [list]</p>",

  "duplicate_check": "<p>[Similar to known issue? Reference it + reuse solution + note differences. Or: No duplicate detected.]</p>",

  "risk_flags": "<p><strong>Risk: [LOW|MEDIUM|HIGH|CRITICAL]</strong></p><ul><li><strong>Cascade:</strong> [what else breaks if this is wrong]</li><li><strong>SVL/Posted Entry:</strong> [if inventory/accounting — reversibility]</li><li><strong>Irreversible Actions:</strong> [list specifically or N/A]</li></ul>",

  "sla_detail": "<p><strong>Resolution SLA:</strong> [X hours] — <strong>Escalation:</strong> [rule] — <strong>Why:</strong> [justification]</p>",

  "validation_steps": "<p><strong>Functional:</strong></p><ol><li>[Exact Odoo navigation → what to confirm]</li></ol><p><strong>Data (GL/Inventory):</strong></p><ol><li>[Report name + navigation + expected value]</li></ol><p><strong>Reporting:</strong></p><ol><li>[Confirm numbers match — exact formula]</li></ol>",

  "test_cases": "<p><strong>Tests:</strong></p><ol><li><strong>Happy Path:</strong> [action] → Expected: [exact values]</li><li><strong>Edge Case:</strong> [action] → Expected: [outcome]</li><li><strong>Regression:</strong> [workflow] → Confirm: [unchanged behavior]</li></ol>",

  "client_communication": "<p>Dear {self.client_id.name},</p><p>Issue: <strong>{self.name}</strong>.</p><p><strong>Root Cause:</strong> [1 non-technical sentence]. <strong>Fix approach:</strong> [timeline]. <strong>Risk:</strong> [level + impact].</p><p>No transactions in [module] during fix window [date/time].</p><p>Best regards,<br/>Consulting Team</p>",

  "executive_summary": "[Business impact + financial risk in 1 sentence]. [Internal root cause in 1 sentence]. [Fix type + effort + risk in 1 sentence].",

  "kb_entry": "<p><strong>Problem:</strong> [concise]</p><p><strong>Root Cause:</strong> [technical]</p><p><strong>Solution:</strong> [approach]</p><p><strong>Tags:</strong> [module, type, keywords for future search]</p>",

  "gap_analysis": "<p>[Only if standard Odoo 19 cannot handle this: gap + OCA module or custom rec. Empty string if not applicable.]</p>",

  "best_practice": "<p><strong>Prevention:</strong></p><ul><li>[Exact Odoo setting: Module → Menu → Field → Value]</li><li>[Process rule]</li><li>[Monitoring: report + frequency + expected result]</li></ul>",

  "recommended_actions": [
    "Action 1: [immediate step the user can take right now]",
    "Action 2: [next step after action 1]",
    "Action 3: [validation step]"
  ]
}}

ABSOLUTE RULES — violation breaks the system:
1. confidence_score and solution_confidence: integers 0-100
2. root_cause_analysis: ARRAY of objects with cause/explanation/confidence/verification
3. image_analysis: always present — used=false if no image
4. proposed_solution: object with safe_solution/alternative_solution/risky_solution
5. customization_suggestion: object with needed/reason/suggested_solution/complexity
6. smart_summary: object with issue/root_cause/solution
7. NEVER say "check", "review", "adjust" — give EXACT field + value + menu path
8. AVCO: state exact formula distortion. FIFO: identify exact layer consumed wrong.
9. Negative stock: always mention _run_fifo_vacuum() behavior
10. Every account referenced must include number (e.g. 110200 Stock Valuation)
11. SLA: critical=2h | high=8h | medium=24h | low=72h (adjust to actual severity)"""
    def _build_claude_prompt(self, gpt_output):
        plain_desc = re.sub('<[^<]+?>', '', self.description or '')
        return f"""Review this GPT analysis for an Odoo consulting task.

ORIGINAL TASK:
- Client: {self.client_id.name}
- Title: {self.name}
- Description: {plain_desc}

GPT ANALYSIS:
{gpt_output}

Provide your audit in HTML covering:

<h3>✅ Analysis Validation</h3>
- Priority correct? Priority score correct (0-100)? If not, what and why?
- Root cause hypotheses complete? Any missing hypotheses?
- Solution type appropriate?
- Are menu paths correct and complete?

<h3>⚠️ Risks & Warnings</h3>
- What risks did GPT miss?
- Cascade risks for inventory/accounting?
- Data integrity or irreversibility concerns?
- Is database backup mentioned? If not, add it.

<h3>🔧 Solution Improvements</h3>
- Missing steps in the fix?
- Better alternatives?
- Odoo 19 specific considerations?
- Auto-fix suggestions accurate?

<h3>📋 Implementation Checklist</h3>
- Pre-implementation steps
- Key validation points
- Post-implementation verification

<h3>📚 KB Entry Quality</h3>
- Is the KB entry reusable for future duplicate detection?
- Are tags specific enough?

<h3>🎯 Final Verdict</h3>
- Score: Approved / Approved with Modifications / Rejected
- Ranked action plan for consultant (what to do first)"""

    # ── Result Parsers ────────────────────────────────────────────
    def _parse_gpt_result(self, raw):
        try:
            # Strip markdown code blocks if GPT wrapped JSON in ```json...```
            cleaned = raw.strip()
            if cleaned.startswith('`'):
                cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.MULTILINE)
                cleaned = re.sub(r'```\s*$', '', cleaned, flags=re.MULTILINE)
                cleaned = cleaned.strip()

            match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if not match:
                raise ValueError("No JSON object found in GPT response")
            data = json.loads(match.group())

            # ── Build GPT Analysis HTML ────────────────────────────
            # root_cause_analysis can be array (new) or string (old)
            rca_raw = data.get('root_cause_analysis', '')
            if isinstance(rca_raw, list):
                rca_html = '<div style="margin:12px 0;">'
                for i, h in enumerate(rca_raw, 1):
                    conf = h.get('confidence', 0)
                    bg   = '#eafaf1' if conf >= 70 else '#fef9e7' if conf >= 40 else '#f9f9f9'
                    bc   = '#27ae60' if conf >= 70 else '#f39c12' if conf >= 40 else '#bdc3c7'
                    tc   = '#27ae60' if conf >= 70 else '#e67e22' if conf >= 40 else '#7f8c8d'
                    rca_html += (
                        f'<div style="background:{bg};border-left:4px solid {bc};'
                        f'padding:12px 16px;margin-bottom:12px;border-radius:0 6px 6px 0;">'
                        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">'
                        f'<strong style="font-size:13px;">Hypothesis {i}: {h.get("cause","")}</strong>'
                        f'<span style="background:{tc};color:white;padding:2px 10px;'
                        f'border-radius:12px;font-size:12px;font-weight:bold;">{conf}%</span>'
                        f'</div>'
                        f'<p style="margin:4px 0;color:#34495e;">{h.get("explanation","")}</p>'
                        f'<p style="margin:4px 0;font-size:12px;color:#7f8c8d;">'
                        f'<strong>✅ Verify:</strong> {h.get("verification","")}</p>'
                        f'</div>'
                    )
                rca_html += '</div>'
            else:
                rca_html = str(rca_raw)

            # proposed_solution can be object (new) or string (old)
            sol_raw = data.get('proposed_solution', '')
            if isinstance(sol_raw, dict):
                solution_html = (
                    '<h4>✅ Safe Solution</h4>' + sol_raw.get('safe_solution', '') +
                    '<h4>🔄 Alternative</h4>' + sol_raw.get('alternative_solution', '') +
                    ('<h4>⚠️ Risky (Last Resort)</h4>' + sol_raw.get('risky_solution', '')
                     if sol_raw.get('risky_solution') else '')
                )
            else:
                solution_html = str(sol_raw)

            # smart_summary
            smart = data.get('smart_summary', {})
            if isinstance(smart, dict):
                smart_html = (
                    f'<p>🔴 <strong>Issue:</strong> {smart.get("issue","")}</p>'
                    f'<p>🔍 <strong>Root Cause:</strong> {smart.get("root_cause","")}</p>'
                    f'<p>🔧 <strong>Solution:</strong> {smart.get("solution","")}</p>'
                )
            else:
                smart_html = str(smart)

            # confidence badges — centered, with proper spacing
            conf_score = int(data.get('confidence_score', 0))
            sol_conf   = int(data.get('solution_confidence', 0))
            conf_color = '#27ae60' if conf_score >= 75 else '#e67e22' if conf_score >= 50 else '#c0392b'
            confidence_html = (
                f'<div style="text-align:center;margin:16px 0 20px 0;">'
                f'<span style="background:{conf_color};color:white;padding:6px 16px;'
                f'border-radius:20px;font-weight:bold;font-size:13px;margin-right:12px;">'
                f'🎯 Diagnosis Confidence: {conf_score}%</span>'
                f'<span style="background:#2980b9;color:white;padding:6px 16px;'
                f'border-radius:20px;font-weight:bold;font-size:13px;">'
                f'🔧 Solution Confidence: {sol_conf}%</span>'
                f'</div>'
            )

            # Build main gpt_analysis tab
            functional_html = confidence_html + '\n'.join(filter(None, [
                data.get('issue_summary', '') or data.get('functional_analysis', '') or data.get('problem_summary', ''),
                '<h4>🔍 Root Cause Analysis</h4>' + rca_html,
                ('<h4>📸 Image Analysis</h4>' + (
                    f'<p>Confidence: {data["image_analysis"]["confidence"]}<br/>'
                    f'{data["image_analysis"]["findings"]}</p>'
                )) if isinstance(data.get('image_analysis'), dict) and data['image_analysis'].get('used') else '',
                '<h4>🎯 Final Diagnosis</h4>' + data.get('final_diagnosis', '')
                    if data.get('final_diagnosis') else '',
                '<h4>🔁 Duplicate Check</h4>' + data.get('duplicate_check', '')
                    if data.get('duplicate_check') else '',
            ]))

            # Build gpt_solution tab
            sol_valid = data.get('solution_validation', {})
            if isinstance(sol_valid, dict):
                sol_valid_html = (
                    f'<p>✅ <strong>Verified:</strong> {sol_valid.get("reason","")} '
                    f'| Risk: {sol_valid.get("risk_level","")}</p>'
                )
            else:
                sol_valid_html = ''

            full_solution_html = '\n'.join(filter(None, [
                sol_valid_html,
                solution_html,
                '<h4>⏱️ SLA &amp; Escalation</h4>' + data.get('sla_detail', '')
                    if data.get('sla_detail') else '',
                '<h4>🧪 Validation Steps</h4>' + data.get('validation_steps', '')
                    if data.get('validation_steps') else '',
                '<h4>🛡️ Best Practice</h4>' + data.get('best_practice', '')
                    if data.get('best_practice') else '',
            ]))

            # recommended_actions → auto_fix_suggestions
            rec_actions = data.get('recommended_actions', []) or data.get('auto_fix_suggestions_list', [])
            auto_fix_raw = data.get('auto_fix_suggestions', '')
            if isinstance(auto_fix_raw, list):
                auto_fix_html = '<p><strong>⚡ Quick Actions:</strong></p><ul>' + ''.join(
                    f'<li>{a}</li>' for a in auto_fix_raw
                ) + '</ul>'
                if rec_actions:
                    auto_fix_html += '<p><strong>🎯 Recommended Actions:</strong></p><ol>' + ''.join(
                        f'<li>{a}</li>' for a in rec_actions
                    ) + '</ol>'
            else:
                auto_fix_html = str(auto_fix_raw)

            # customization_suggestion
            custom = data.get('customization_suggestion', {})
            if isinstance(custom, dict) and custom.get('needed'):
                custom_html = (
                    f'<p>🔧 <strong>Customization Needed:</strong> {custom.get("reason","")}</p>'
                    f'<p><strong>Suggested:</strong> {custom.get("suggested_solution","")}</p>'
                    f'<p><strong>Complexity:</strong> {custom.get("complexity","")}</p>'
                )
                auto_fix_html += '<h4>🧩 Customization Required</h4>' + custom_html

            # Executive summary with smart_summary
            exec_summary = data.get('executive_summary', '') or data.get('problem_summary', '')
            ai_summary_html = smart_html + ('<hr/>' + f'<p>{exec_summary}</p>' if exec_summary else '')

            vals = {
                'priority_level':       data.get('priority_level', '3_medium'),
                'priority_score':       conf_score or int(data.get('priority_score', 50)),
                'odoo_module':          data.get('odoo_module', 'other'),
                'task_type':            data.get('task_type', 'consulting'),
                'root_cause':           data.get('root_cause', 'requirements'),
                'solution_type':        data.get('solution_type', 'standard_odoo'),
                'assignment_type':      data.get('assignment_type', 'functional'),
                'complexity':           data.get('complexity', 'medium'),
                'effort_estimate':      float(data.get('effort_hours', 4)),
                'effort_category':      data.get('effort_category', 'short'),
                'risk_level':           data.get('risk_level', 'low'),
                'risk_flags':           data.get('risk_flags') or '',
                'sla_hours':            float(data.get('sla_hours', 24)),
                'escalation_rule':      data.get('escalation_rule', ''),
                'gpt_analysis':         functional_html,
                'gpt_solution':         full_solution_html,
                'auto_fix_suggestions': auto_fix_html,
                'test_cases':           data.get('test_cases', ''),
                'client_communication': data.get('client_communication', ''),
                'gap_analysis_notes':   data.get('gap_analysis', ''),
                'ai_summary':           ai_summary_html,
                'kb_entry':             data.get('kb_entry', ''),
            }
            self.write(vals)
            self._auto_assign()

        except (json.JSONDecodeError, ValueError) as e:
            _logger.error("Failed to parse GPT result: %s\nRaw: %s", e, raw[:500])
            self.write({'gpt_analysis': f'<p><strong>⚠️ Parse Error:</strong> {e}</p><pre style="font-size:11px;white-space:pre-wrap">{raw[:3000]}</pre>'})
    def _parse_claude_result(self, raw):
        self.write({'claude_review': raw})

    # ── Auto Assignment ───────────────────────────────────────────
    def _auto_assign(self):
        if self.assigned_to:
            return
        get = self.env['ir.config_parameter'].sudo().get_param
        mapping = {
            'functional': get('smart_task_hub.default_functional_user'),
            'developer':  get('smart_task_hub.default_developer_user'),
            'support':    get('smart_task_hub.default_support_user'),
            'architect':  get('smart_task_hub.default_architect_user'),
        }
        user_id = mapping.get(self.assignment_type)
        if user_id:
            try:
                self.assigned_to = int(user_id)
            except (ValueError, TypeError):
                pass

    # ── Knowledge Base ────────────────────────────────────────────
    def _save_to_knowledge_base(self):
        if self.ai_status != 'reviewed' or not self.gpt_solution:
            return
        plain_desc = re.sub('<[^<]+?>', '', self.description or '')
        kb = self.env['smart.knowledge.base'].create({
            'name':                self.name,
            'odoo_module':         self.odoo_module,
            'task_type':           self.task_type,
            'root_cause':          self.root_cause,
            'solution_type':       self.solution_type,
            'complexity':          self.complexity,
            'risk_level':          self.risk_level,
            'priority_score':      self.priority_score,
            'problem_description': plain_desc[:500],
            'root_cause_detail':   self.gpt_analysis,
            'solution_content':    self.gpt_solution,
            'prevention_notes':    self.best_practice_html(),
            'source_task_id':      self.id,
            'is_published':        True,
        })
        self.knowledge_base_id = kb.id

    def best_practice_html(self):
        """Extract best practice from gpt_solution if available."""
        sol = self.gpt_solution or ''
        idx = sol.find('Best Practice')
        return sol[idx:] if idx > -1 else ''


    # ── Voice / Screenshot helpers ────────────────────────────────
    @api.depends()
    def _compute_voice_dummy(self):
        for rec in self:
            rec.voice_input_control = ''

    def action_analyze_screenshot(self):
        """
        1. Send screenshot to GPT-4V to extract exact error text / UI state.
        2. Store result in screenshot_analysis field (used by _build_task_context).
        3. Run full 3-phase AI analysis with the vision data as primary input.
        """
        self.ensure_one()
        if not self.screenshot_image:
            raise UserError(_('Please upload a screenshot first.'))
        try:
            gateway     = self.env['smart.ai.gateway']

            self.message_post(
                body=_('<b>Analyzing screenshot with GPT-4V...</b>'),
                message_type='notification',
            )

            vision_text = gateway.call_gpt_vision(self.screenshot_image)

            if not vision_text or not vision_text.strip():
                raise UserError(_(
                    'GPT-4V returned an empty response. '
                    'Please check the vision model setting and try again.'
                ))

            # Store in dedicated field — _build_task_context picks this up
            # as a HIGH-PRIORITY section separate from the user description.
            self.write({'screenshot_analysis': vision_text.strip()})

            # Also show in description for visual feedback in the form
            current_desc = self.description or ''
            vision_html = (
                '<br/><hr/>'
                '<p><strong>Screenshot Analysis (GPT-4V):</strong></p>'
                '<p>' + vision_text.strip().replace('\n', '<br/>') + '</p>'
            )
            self.write({'description': current_desc + vision_html})

            self.message_post(
                body=_('<b>Screenshot analyzed — running full AI analysis...</b>'),
                message_type='notification',
            )
            self.action_analyze_with_ai()

        except UserError:
            raise
        except Exception as e:
            _logger.exception("Screenshot analysis failed for task %s", self.id)
            raise UserError(_('Screenshot analysis failed: %s') % str(e))


    # ── Action Buttons ────────────────────────────────────────────
    def action_retry_analysis(self):
        self.ensure_one()
        self.write({'ai_status': 'pending', 'gpt_analysis': False, 'claude_review': False})
        self.action_analyze_with_ai()

    def action_mark_done(self):
        self.write({'state': 'done', 'resolution_date': fields.Datetime.now()})

    def action_create_project_task(self):
        self.ensure_one()
        task = self.env['project.task'].create({
            'name':       self.name,
            'project_id': self.project_id.id if self.project_id else False,
            'user_ids':   [(4, self.assigned_to.id)] if self.assigned_to else [],
            'description': self.gpt_solution or self.description,
        })
        self.project_task_id = task.id
        return {'type': 'ir.actions.act_window', 'res_model': 'project.task',
                'res_id': task.id, 'view_mode': 'form'}

    def action_create_helpdesk_ticket(self):
        self.ensure_one()
        plain = re.sub('<[^<]+?>', '', self.description or '')
        ticket = self.env['helpdesk.ticket'].create({
            'name':        self.name,
            'partner_id':  self.client_id.id,
            'description': plain,
            'user_id':     self.assigned_to.id if self.assigned_to else False,
        })
        self.helpdesk_ticket_id = ticket.id
        return {'type': 'ir.actions.act_window', 'res_model': 'helpdesk.ticket',
                'res_id': ticket.id, 'view_mode': 'form'}
