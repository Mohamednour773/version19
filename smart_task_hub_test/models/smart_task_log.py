# -*- coding: utf-8 -*-
import json
import base64 as _b64
import logging
import urllib.request
import urllib.error
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
#  PHASE 1 — DIAGNOSE
#  GPT focuses ONLY on understanding the problem deeply
# ═══════════════════════════════════════════════════════════════════
PHASE1_DIAGNOSE_SYSTEM = """
You are an ELITE Odoo ERP Diagnostic Engine — Senior Expert Team.

You combine:
- Senior Odoo Functional Consultant (10+ years, all modules)
- Senior Odoo Technical Developer (Python/XML/JS, ORM internals)
- Accounting & Costing Expert (IFRS, AVCO/FIFO/Standard internals)
- Inventory & Warehouse Expert (SVL, stock.move, _run_fifo internals)
- Manufacturing Specialist (MRP, WIP, BOM costing)
- HR & Payroll Expert (salary rules, localdict, leave management)

DEEP TECHNICAL KNOWLEDGE:
INVENTORY COSTING:
- Standard Price: unit_cost fixed. Variance goes to Price Difference account.
- AVCO: new_avg=(old_qty*old_cost+in_qty*in_cost)/(old_qty+in_qty). Auto-updates standard_price on every receipt.
- FIFO: each receipt = one stock.valuation.layer. _run_fifo() consumes chronologically.
- NEGATIVE STOCK/AVCO: SVL posts at current standard_price. _run_fifo_vacuum() corrects qty NOT journal = permanent inconsistency.
- NEGATIVE STOCK/FIFO: SVL unit_cost=0. _run_fifo_vacuum() corrects both qty AND journal.
- stock.move = physical movement. SVL = financial record. ALL valuation bugs are at SVL level.

ACCOUNTING:
- amount_currency = transaction currency. debit/credit = company currency.
- Reconciliation stuck: Technical > Partial Reconcile > delete.
- Intercompany: wrong journal = wrong exchange rate = P&L distorted.

MANUFACTURING:
- WIP debited on MO confirm, transferred to Finished Goods on close.
- MO closed with 0 cost = components not consumed before close.

TECHNICAL PATTERNS (Odoo 19):
- @api.depends missing field = computed field not updating.
- ir.rule blocks write = workflow silent fail.
- attrs/states removed in v17+ = use inline invisible=.
- N+1 queries in loops = use browse(ids).

BEHAVIOR RULES - ZERO TOLERANCE:
1. NEVER assume one root cause. List minimum 3 hypotheses with confidence %.
2. NEVER say check/review/adjust/verify. Give EXACT menu path + field + value.
3. Navigation format: Module > Sub-menu > Page > Field > exact value.
4. Account numbers required: e.g. 110200 Stock Valuation Account.
5. Think like a 200 USD/hr consultant. Junior must execute without follow-up.
6. For costing issues: ALWAYS check stock.valuation.layer first, not just UI reports.
7. For AVCO zero cost: check if components had unit_cost=0 at time of consumption.
8. For manufacturing: check if MO was closed before all moves were validated.
9. Confidence must be based on evidence from description, not assumption.
10. verification steps must be EXECUTABLE: exact menu > exact field > exact value to look for.

ANTI-PATTERNS (these make the analysis useless):
- "Check product costing method" → SAY: Inventory > Configuration > Products > [product] > Inventory tab > Costing Method field > should be AVCO
- "Review journal entries" → SAY: Accounting > Reporting > Journal Items > filter by MO reference > check DR/CR on account 110200
- "Validate stock moves" → SAY: Manufacturing > [MO] > Detailed Operations tab > check each line has Done qty > 0

ODOO VERSION RULES:
- The task will specify the Odoo version (16/17/18/19/20).
- ALWAYS search for version-specific behavior before answering.
- Odoo 17+: attrs/states removed, use invisible= directly (applies to v19).
- Odoo 18+: new JS framework (Owl), different view inheritance.
- If behavior changed between versions, state EXACTLY which version introduced the change.
- Search: site:odoo.com/documentation/[VERSION] AND site:github.com/odoo/odoo/issues

YOUR TASK: Diagnose the Odoo issue. Return ONLY raw JSON, no markdown.
Start with { and end with }.

{
  "priority_level": "1_critical|2_high|3_medium|4_low",
  "priority_score": 75,
  "odoo_module": "accounting|inventory|manufacturing|sales|purchase|hr|project|ecommerce|pos|fleet|maintenance|quality|other",
  "task_type": "bug|config|customization|training|consulting|gap_analysis|integration|upgrade|excel_output",
  "root_cause": "configuration|user_error|workflow|code_bug|data_issue|integration|requirements",
  "solution_type": "config_change|process_fix|custom_dev|training|standard_odoo|third_party|excel_output",
  "assignment_type": "functional|developer|support|architect|manager",
  "complexity": "easy|medium|hard",
  "effort_hours": 4.0,
  "effort_category": "quick|short|medium|large|project",
  "risk_level": "low|medium|high|critical",
  "sla_hours": 8.0,
  "confidence_score": 85,
  "problem_summary": "Exactly what is broken and business impact in 2 sentences.",
  "smart_summary": {
    "issue": "1-line problem statement",
    "root_cause": "1-line technical cause",
    "solution": "1-line fix approach"
  },
  "root_cause_analysis": [
    {
      "cause": "Hypothesis 1 - Config/Data/Code/User/Access",
      "explanation": "Technical mechanism causing the issue",
      "confidence": 85,
      "verification": "Exact steps: Module > Menu > Field > what to look for"
    },
    {
      "cause": "Hypothesis 2 - type",
      "explanation": "Why this could cause the issue",
      "confidence": 55,
      "verification": "Exact verification steps"
    },
    {
      "cause": "Hypothesis 3 - type",
      "explanation": "Why this could cause the issue",
      "confidence": 30,
      "verification": "Exact verification steps"
    }
  ],
  "final_diagnosis": "Most likely cause with confidence % and justification.",
  "risk_flags": "What breaks if fix goes wrong. Cascade risks. Irreversible actions.",
  "escalation_rule": "If not resolved in X hours > notify [exact role]",
  "needs_excel_output": false,
  "excel_description": "If needs_excel_output true: describe exact columns and data needed"
}
"""

# ═══════════════════════════════════════════════════════════════════
#  PHASE 2 — SOLVE
#  GPT builds the complete solution based on Phase 1 diagnosis
# ═══════════════════════════════════════════════════════════════════
PHASE2_SOLVE_SYSTEM = """
You are an ELITE Odoo ERP Solution Engine.

You receive a task context and a Phase 1 diagnosis. Produce the COMPLETE, EXECUTABLE solution.

MANDATORY RULES - NO EXCEPTIONS:
1. EVERY step must have the FULL Odoo menu path: Module > Sub-menu > Page > exact field > exact value.
   WRONG: "Reopen the manufacturing order"
   RIGHT: "Manufacturing > Operations > Manufacturing Orders > open MO [name] > click Unlock button (top left)"
2. ALWAYS start safe_solution with: "<li>Take a full database backup before proceeding.</li>"
3. Include technical field names: e.g. stock.valuation.layer, unit_cost, remaining_qty
4. Include account numbers where relevant: e.g. 511000 COGS, 110200 Stock Valuation
5. auto_fix_suggestions must be SPECIFIC actions, not generic advice:
   WRONG: "Reopen and recompute cost"
   RIGHT: "Manufacturing > Operations > Manufacturing Orders > [MO name] > Unlock > Recompute > Validate"
6. client_communication must use the ACTUAL client name from the task context (not [Client])
7. test_cases must include specific field values and expected numbers, not generic descriptions
8. For AVCO/FIFO/costing issues: always check stock.valuation.layer records first
9. For manufacturing cost = 0: always check if components have unit_cost > 0 before MO was confirmed
10. ALWAYS mention the Odoo version from task context and verify solution works for THAT version
11. If solution differs between versions, provide version-specific steps clearly labeled:
    Odoo 16: [steps] | Odoo 17: [steps] | Odoo 18: [steps] | Odoo 19+: [steps]

ANTI-PATTERNS (never do these):
- "Check the settings" → give exact menu path
- "Verify the configuration" → say exactly what field to check and what value is correct
- "Recompute costs" → say exactly which button, which menu, in what order
- Generic test cases without specific values

Return ONLY raw JSON. No markdown. Start with { end with }.

{
  "solution_confidence": 88,
  "safe_solution": "<ol><li>Take a full database backup before proceeding.</li><li>[Exact step: Module > Menu > Page > Field > Value]</li><li>[Next exact step]</li></ol>",
  "alternative_solution": "<p>Safer fallback with exact steps if main fix is risky.</p>",
  "risky_solution": "<p>Last resort only - include exact warnings and irreversibility notes.</p>",
  "validation_steps": "<ol><li>[Exact navigation] > check [exact field] shows [exact expected value]</li></ol>",
  "test_cases": "<ol><li><strong>Happy Path:</strong> [exact action with values] > Expected: [exact field] = [exact value]</li><li><strong>Edge Case:</strong> [specific scenario] > Expected: [specific outcome]</li><li><strong>Regression:</strong> [exact report/menu] > Confirm [specific value] unchanged</li></ol>",
  "client_communication": "<p>Dear [USE ACTUAL CLIENT NAME FROM TASK],</p><p>Root cause: [1 non-technical sentence]. Fix: [approach + timeline]. Risk: [level + what precautions].</p><p>Please avoid transactions in [exact module] during the fix window.</p>",
  "best_practice": "<ul><li>[Exact Odoo setting: Module > Menu > Field > Value] to prevent recurrence</li><li>[Process rule]</li><li>[Monitoring: exact report name + frequency + expected value]</li></ul>",
  "auto_fix_suggestions": [
    "Step 1: [Module] > [Menu] > [exact action with field/value]",
    "Step 2: [Module] > [Menu] > [exact action with field/value]",
    "Step 3: [Module] > [Menu] > [exact action with field/value]"
  ],
  "recommended_actions": [
    "Immediate: [exact action now]",
    "Next: [exact action after first]",
    "Verify: [exact validation step]"
  ],
  "kb_entry": "<p><strong>Problem:</strong> [concise technical problem]</p><p><strong>Root Cause:</strong> [exact technical cause with field names]</p><p><strong>Solution:</strong> [exact approach]</p><p><strong>Tags:</strong> [module, costing_method, task_type, specific_keywords]</p>",
  "gap_analysis": "",
  "sla_detail": "<p><strong>Resolution SLA:</strong> [X hours] - <strong>Escalation:</strong> [exact rule] - <strong>Why:</strong> [justification]</p>",
  "customization_needed": false,
  "customization_detail": ""
}
"""

# ═══════════════════════════════════════════════════════════════════
#  PHASE 3 — CLAUDE AUDITOR
# ═══════════════════════════════════════════════════════════════════
CLAUDE_AUDITOR_PROMPT = """
You are a Senior Odoo Quality Auditor and Risk Specialist.
You critically review AI-generated Odoo consulting analysis.

AUDIT RULES:
1. If fix could cause MORE corruption: flag as REJECTED immediately.
2. Correct any wrong menu paths or field names.
3. Correct stock.move vs SVL level misidentification.
4. Add cascade risk if GPT missed it.
5. Add database backup reminder if missing.
6. Flag wrong priority/score with correct value.
7. Check Odoo 19 compatibility.
8. Identify missing root cause hypotheses.

RESPOND IN HTML with these exact sections:
<h3>Analysis Validation</h3>
<h3>Risks GPT Missed</h3>
<h3>Solution Improvements</h3>
<h3>Implementation Checklist</h3>
<h3>Final Verdict</h3>
Verdict: Approved | Approved with Modifications | Rejected
End with ranked consultant action plan.
"""


class SmartAIGateway(models.AbstractModel):
    _name = 'smart.ai.gateway'
    _description = 'AI Gateway Service'

    @api.model
    def _get_param(self, key, default=''):
        return self.env['ir.config_parameter'].sudo().get_param(key, default)

    @api.model
    def call_gpt_phase1_diagnose(self, task_context):
        return self._call_gpt_with_system(PHASE1_DIAGNOSE_SYSTEM, task_context, max_tokens=2500)

    @api.model
    def call_gpt_phase2_solve(self, task_context, diagnosis_summary):
        user_prompt = (
            "ORIGINAL TASK:\n" + task_context +
            "\n\nDIAGNOSIS FROM PHASE 1:\n" + diagnosis_summary +
            "\n\nNow produce the complete solution. Focus on the highest-confidence root cause."
        )
        return self._call_gpt_with_system(PHASE2_SOLVE_SYSTEM, user_prompt, max_tokens=2500)

    @api.model
    def _call_gpt_with_system(self, system_prompt, user_prompt, max_tokens=2500):
        api_key = self._get_param('smart_task_hub_test.openai_api_key')
        model = self._get_param('smart_task_hub_test.openai_model', 'o4-mini')
        if not api_key:
            raise UserError(_('OpenAI API key not configured. Go to Smart Task Hub > Settings.'))

        full_system = system_prompt + "\n\nCRITICAL: Respond with RAW JSON ONLY. No ```json. No text before or after. Start with { end with }."

        # o4-mini and o3 use reasoning - different API params
        is_reasoning = model.startswith('o3') or model.startswith('o4') or model.startswith('o1')

        if is_reasoning:
            # Reasoning models: no system role, no temperature, use max_completion_tokens
            payload_dict = {
                'model': model,
                'messages': [
                    {'role': 'user', 'content': full_system + '\n\n' + user_prompt},
                ],
                'max_completion_tokens': max_tokens * 3,
            }
        else:
            payload_dict = {
                'model': model,
                'messages': [
                    {'role': 'system', 'content': full_system},
                    {'role': 'user', 'content': user_prompt},
                ],
                'temperature': 0.15,
                'max_tokens': max_tokens,
            }

        # Add web search tool so GPT searches Odoo docs + forum + GitHub
        payload_dict['tools'] = [{
            'type': 'web_search_preview',
            'search_context_size': 'medium',
        }]

        payload = json.dumps(payload_dict).encode('utf-8')
        req = urllib.request.Request(
            'https://api.openai.com/v1/chat/completions',
            data=payload,
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            method='POST'
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                result = ''
                for choice in data.get('choices', []):
                    content_val = choice.get('message', {}).get('content')
                    if content_val:
                        result += content_val
                if not result:
                    result = data['choices'][0]['message'].get('content', '')
                self._log_api_call('gpt', model, data.get('usage', {}))
                return result
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8')
            _logger.error("OpenAI error %s: %s", e.code, body)
            # Fallback without web search if model doesn't support it
            if e.code in (400, 422) and 'web_search' in body.lower():
                _logger.warning("Web search not supported for %s, retrying without", model)
                payload_dict.pop('tools', None)
                payload = json.dumps(payload_dict).encode('utf-8')
                req2 = urllib.request.Request(
                    'https://api.openai.com/v1/chat/completions',
                    data=payload,
                    headers={
                        'Authorization': f'Bearer {api_key}',
                        'Content-Type': 'application/json',
                    },
                    method='POST'
                )
                with urllib.request.urlopen(req2, timeout=180) as resp2:
                    data2 = json.loads(resp2.read().decode('utf-8'))
                    self._log_api_call('gpt', model, data2.get('usage', {}))
                    return data2['choices'][0]['message'].get('content', '')
            raise UserError(_('OpenAI API error %s: %s') % (e.code, body[:300]))

    @api.model
    def call_claude(self, user_prompt):
        api_key = self._get_param('smart_task_hub_test.anthropic_api_key')
        model = self._get_param('smart_task_hub_test.claude_model', 'claude-opus-4-5')
        if not api_key:
            raise UserError(_('Anthropic API key not configured. Go to Smart Task Hub > Settings.'))

        payload = json.dumps({
            'model': model,
            'max_tokens': 2500,
            'system': CLAUDE_AUDITOR_PROMPT,
            'messages': [{'role': 'user', 'content': user_prompt}],
        }).encode('utf-8')

        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=payload,
            headers={
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
                'Content-Type': 'application/json',
            },
            method='POST'
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                result = data['content'][0]['text']
                self._log_api_call('claude', model, data.get('usage', {}))
                return result
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8')
            _logger.error("Anthropic error %s: %s", e.code, body)
            raise UserError(_('Anthropic API error %s: %s') % (e.code, body[:300]))


    @api.model
    def call_gpt_vision(self, image_data):
        """
        Send a screenshot to GPT-4V / gpt-4o and return a structured
        text description suitable for use as task input.

        Handles all Odoo Binary field output types:
          - raw bytes  (attachment=True returns file content directly)
          - base64 bytes  (non-attachment Binary returns b64-encoded bytes)
          - base64 str
        """
        api_key = self._get_param('smart_task_hub_test.openai_api_key')
        model   = self._get_param('smart_task_hub_test.vision_model', 'gpt-4o')
        if not api_key:
            raise UserError(_('OpenAI API key not configured. Go to Smart Task Hub > Settings.'))

        if not image_data:
            raise UserError(_('No image data received. Please upload a screenshot first.'))

        # ── Normalize to base64 string ────────────────────────────
        if isinstance(image_data, bytes):
            try:
                # Try interpreting as already-base64 encoded bytes (printable ASCII)
                candidate = image_data.decode('ascii')
                _b64.b64decode(candidate, validate=True)   # raises if not valid b64
                b64_str = candidate
                _logger.debug("call_gpt_vision: received pre-encoded base64 bytes")
            except Exception:
                # Raw binary file — encode it to base64
                b64_str = _b64.b64encode(image_data).decode('ascii')
                _logger.debug("call_gpt_vision: received raw binary, encoded to base64")
        elif isinstance(image_data, str):
            b64_str = image_data
        else:
            raise UserError(_('Unsupported image data type: %s') % type(image_data).__name__)

        # ── Auto-detect MIME type from magic bytes ────────────────
        try:
            raw_head = _b64.b64decode(b64_str[:16] + '==')
        except Exception:
            raw_head = b''

        if raw_head[:8] == b'\x89PNG\r\n\x1a\n':
            mime = 'image/png'
        elif raw_head[:2] == b'\xff\xd8':
            mime = 'image/jpeg'
        elif raw_head[:6] in (b'GIF87a', b'GIF89a'):
            mime = 'image/gif'
        elif raw_head[:4] == b'RIFF' and raw_head[8:12] == b'WEBP':
            mime = 'image/webp'
        else:
            mime = 'image/png'   # safe default for unknown

        _logger.info("call_gpt_vision: image MIME=%s b64_len=%d model=%s", mime, len(b64_str), model)

        vision_prompt = (
            "You are an expert Odoo ERP analyst. Analyze this screenshot with EXTREME precision.\n\n"
            "CRITICAL RULES:\n"
            "- Copy ALL text VERBATIM — do NOT paraphrase error messages, codes, or IDs.\n"
            "- If a popup/dialog/toast exists, copy its FULL text exactly as shown.\n"
            "- Include every visible number, barcode, ID, reference, and amount.\n"
            "- Treat Arabic text — read it right-to-left and transliterate or translate.\n\n"
            "Return EXACTLY this structure (no extra commentary):\n\n"
            "ERROR MESSAGE (verbatim): [exact text from any dialog, popup, or red banner — or 'None']\n"
            "ERROR CODE / ID: [any code, barcode, reference number shown — or 'None']\n"
            "SCREEN / MODULE: [which Odoo module and menu path is visible]\n"
            "BREADCRUMB: [breadcrumb trail shown at top — or 'None']\n"
            "VISIBLE FIELDS & VALUES: [list key field name: value pairs]\n"
            "BUTTON STATES: [which buttons are visible / greyed out]\n"
            "WARNING / INFO ICONS: [any yellow warning or red error icons]\n"
            "ADDITIONAL CONTEXT: [any other relevant UI details]\n\n"
            "This output will be the PRIMARY INPUT for an AI diagnosis engine — accuracy is critical."
        )

        payload = json.dumps({
            'model':      model,
            'max_tokens': 1500,
            'messages': [{
                'role':    'user',
                'content': [
                    {'type': 'text', 'text': vision_prompt},
                    {
                        'type':      'image_url',
                        'image_url': {
                            'url':    f'data:{mime};base64,{b64_str}',
                            'detail': 'high',
                        },
                    },
                ],
            }],
        }).encode('utf-8')

        req = urllib.request.Request(
            'https://api.openai.com/v1/chat/completions',
            data=payload,
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type':  'application/json',
            },
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data   = json.loads(resp.read().decode('utf-8'))
                result = data['choices'][0]['message']['content']
                self._log_api_call('gpt', model, data.get('usage', {}))
                _logger.info("call_gpt_vision: received %d chars from GPT-4V", len(result))
                return result
        except urllib.error.HTTPError as e:
            err_body = e.read().decode('utf-8')
            _logger.error("GPT-4V HTTP %s: %s", e.code, err_body)
            raise UserError(_('GPT Vision API error %s: %s') % (e.code, err_body[:300]))

    # backward compat
    @api.model
    def call_gpt(self, user_prompt):
        return self._call_gpt_with_system(PHASE1_DIAGNOSE_SYSTEM, user_prompt, max_tokens=3000)

    @api.model
    def _log_api_call(self, provider, model, usage):
        try:
            self.env['smart.ai.log'].sudo().create({
                'provider': provider,
                'model': model,
                'prompt_tokens': usage.get('prompt_tokens', usage.get('input_tokens', 0)),
                'completion_tokens': usage.get('completion_tokens', usage.get('output_tokens', 0)),
                'total_tokens': usage.get('total_tokens', 0),
            })
        except Exception:
            pass


class SmartAILog(models.Model):
    _name = 'smart.ai.log'
    _description = 'AI API Usage Log'
    _order = 'create_date desc'

    provider = fields.Selection([
        ('gpt', 'OpenAI GPT'),
        ('claude', 'Anthropic Claude'),
    ], string='Provider', required=True)
    model = fields.Char('Model Used')
    prompt_tokens = fields.Integer('Prompt Tokens')
    completion_tokens = fields.Integer('Completion Tokens')
    total_tokens = fields.Integer('Total Tokens')
    create_date = fields.Datetime('Date', readonly=True)
    task_id = fields.Many2one('smart.task', 'Related Task')

    estimated_cost_usd = fields.Float('Estimated Cost (USD)', compute='_compute_cost', store=True)

    @api.depends('provider', 'model', 'prompt_tokens', 'completion_tokens')
    def _compute_cost(self):
        pricing = {
            'gpt-4o': {'prompt': 2.50, 'completion': 10.00},
            'gpt-4o-mini': {'prompt': 0.15, 'completion': 0.60},
            'claude-opus-4-5': {'prompt': 15.00, 'completion': 75.00},
            'claude-sonnet-4-5': {'prompt': 3.00, 'completion': 15.00},
        }
        for rec in self:
            p = pricing.get(rec.model or '', {'prompt': 2.50, 'completion': 10.00})
            rec.estimated_cost_usd = (
                (rec.prompt_tokens * p['prompt'] / 1_000_000) +
                (rec.completion_tokens * p['completion'] / 1_000_000)
            )
