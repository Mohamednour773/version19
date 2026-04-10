# -*- coding: utf-8 -*-
import base64
import json
import logging
import urllib.request
import urllib.error

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class SmartTaskController(http.Controller):

    @http.route(
        '/smart_task_hub_test/transcribe_voice',
        type='json', auth='user', methods=['POST'], csrf=False,
    )
    def transcribe_voice(self, audio_data, audio_format, task_id=None):
        """
        Receive base64-encoded audio from the browser, forward it to
        OpenAI Whisper, and return the transcript in the original language.
        """
        try:
            ICP     = request.env['ir.config_parameter'].sudo()
            api_key = ICP.get_param('smart_task_hub_test.openai_api_key')
            if not api_key:
                return {
                    'success': False,
                    'error':   'OpenAI API key not configured. Go to Smart Task Hub → Settings.',
                }

            model    = ICP.get_param('smart_task_hub_test.whisper_model', 'whisper-1')
            # Language code — default 'ar' for Arabic transcription.
            # Set empty string in settings to let Whisper auto-detect.
            language = ICP.get_param('smart_task_hub_test.whisper_language', 'ar').strip()

            # Decode base64 audio bytes
            audio_bytes = base64.b64decode(audio_data)

            # ── Build multipart/form-data manually ───────────────
            boundary   = b'SmartTaskHubBoundary7MA4YWxk'
            mime_map   = {
                'webm': b'audio/webm',
                'mp4':  b'audio/mp4',
                'mp3':  b'audio/mpeg',
                'wav':  b'audio/wav',
                'm4a':  b'audio/mp4',
            }
            audio_mime = mime_map.get(audio_format, b'audio/webm')
            filename   = ('audio.' + audio_format).encode()

            # model part
            body = (
                b'--' + boundary + b'\r\n'
                b'Content-Disposition: form-data; name="model"\r\n\r\n' +
                model.encode() + b'\r\n'
            )

            # language part — only add if language is specified
            if language:
                body += (
                    b'--' + boundary + b'\r\n'
                    b'Content-Disposition: form-data; name="language"\r\n\r\n' +
                    language.encode() + b'\r\n'
                )

            # response_format — force verbose_json to get language info in logs
            body += (
                b'--' + boundary + b'\r\n'
                b'Content-Disposition: form-data; name="response_format"\r\n\r\n'
                b'json\r\n'
            )

            # audio file part
            body += (
                b'--' + boundary + b'\r\n'
                b'Content-Disposition: form-data; name="file"; filename="' + filename + b'"\r\n'
                b'Content-Type: ' + audio_mime + b'\r\n\r\n' +
                audio_bytes +
                b'\r\n--' + boundary + b'--\r\n'
            )

            req = urllib.request.Request(
                'https://api.openai.com/v1/audio/transcriptions',
                data=body,
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type':  f'multipart/form-data; boundary={boundary.decode()}',
                },
                method='POST',
            )

            with urllib.request.urlopen(req, timeout=60) as resp:
                data       = json.loads(resp.read().decode('utf-8'))
                transcript = data.get('text', '')
                _logger.info(
                    "Whisper transcribed %d chars (lang=%s) for task %s",
                    len(transcript), language or 'auto', task_id,
                )
                return {'success': True, 'transcript': transcript}

        except urllib.error.HTTPError as e:
            err_body = e.read().decode('utf-8')
            _logger.error("Whisper API HTTP %s: %s", e.code, err_body)
            return {'success': False, 'error': f'Whisper API error {e.code}: {err_body[:300]}'}
        except Exception as e:
            _logger.exception("Voice transcription failed")
            return {'success': False, 'error': str(e)}
