/** @odoo-module **/

/**
 * Smart Task Hub — Voice Recorder OWL Widget (Odoo 17)
 *
 * Registered as a "char" field widget named "voice_recorder".
 * Renders a microphone button that:
 *   1. Captures audio via MediaRecorder API
 *   2. Sends base64 audio to /smart_task_hub/transcribe_voice (Whisper)
 *   3. Appends the transcript to the description field
 *   4. Auto-triggers action_analyze_with_ai()
 */

import { Component, useState, xml } from "@odoo/owl";
import { registry }                  from "@web/core/registry";
import { standardFieldProps }        from "@web/views/fields/standard_field_props";
import { useService }                from "@web/core/utils/hooks";

export class VoiceRecorderField extends Component {

    static template = xml`
        <div class="smart_voice_recorder d-inline-flex align-items-center gap-2 py-1">
            <button
                class="btn btn-sm d-inline-flex align-items-center gap-1"
                t-att-class="{
                    'btn-danger':           state.isRecording,
                    'btn-warning':          state.isProcessing,
                    'btn-outline-secondary': !state.isRecording and !state.isProcessing
                }"
                t-on-click="onButtonClick"
                t-att-disabled="state.isProcessing">
                <t t-esc="state.label"/>
            </button>
            <span t-if="state.isRecording"   class="text-danger  small fst-italic">Recording… click to stop</span>
            <span t-if="state.isProcessing"  class="text-warning small fst-italic">Transcribing with Whisper…</span>
        </div>
    `;

    static props = { ...standardFieldProps };

    setup() {
        this.state = useState({
            isRecording:  false,
            isProcessing: false,
            label:        "🎤 Voice Input",
        });
        this.mediaRecorder = null;
        this.audioChunks   = [];
        this.notification  = useService("notification");
        this.rpc           = useService("rpc");
    }

    // ── Public handler ─────────────────────────────────────────
    async onButtonClick() {
        if (this.state.isProcessing) return;
        if (this.state.isRecording) {
            this._stopRecording();
        } else {
            await this._startRecording();
        }
    }

    // ── Recording ──────────────────────────────────────────────
    async _startRecording() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            this.audioChunks = [];

            const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
                ? "audio/webm;codecs=opus"
                : MediaRecorder.isTypeSupported("audio/webm")
                    ? "audio/webm"
                    : "audio/mp4";

            this.mediaRecorder = new MediaRecorder(stream, { mimeType });

            this.mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) this.audioChunks.push(e.data);
            };

            this.mediaRecorder.onstop = async () => {
                stream.getTracks().forEach((t) => t.stop());
                await this._processAudio(mimeType);
            };

            this.mediaRecorder.start();
            this.state.isRecording = true;
            this.state.label       = "🔴 Stop";
        } catch (err) {
            this.notification.add(
                "Microphone access denied: " + err.message,
                { type: "danger" }
            );
        }
    }

    _stopRecording() {
        if (this.mediaRecorder && this.mediaRecorder.state !== "inactive") {
            this.mediaRecorder.stop();
        }
        this.state.isRecording  = false;
        this.state.isProcessing = true;
        this.state.label        = "⏳";
    }

    // ── Processing ─────────────────────────────────────────────
    async _processAudio(mimeType) {
        try {
            const blob   = new Blob(this.audioChunks, { type: mimeType });
            const base64 = await this._blobToBase64(blob);
            // Determine file extension sent to controller
            const ext    = mimeType.includes("webm") ? "webm" : "mp4";
            const taskId = this.props.record.resId;

            const result = await this.rpc("/smart_task_hub_test/transcribe_voice", {
                audio_data:   base64,
                audio_format: ext,
                task_id:      taskId,
            });

            if (result && result.success) {
                // Append transcript to existing description
                const currentDesc = this.props.record.data.description || "";
                const voiceBlock  = (
                    `<p><strong>🎤 Voice Input:</strong></p>` +
                    `<p>${result.transcript}</p>`
                );
                const newDesc = currentDesc ? currentDesc + voiceBlock : voiceBlock;
                await this.props.record.update({ description: newDesc });

                this.notification.add(
                    "Voice transcribed! Saving and launching AI analysis…",
                    { type: "success" }
                );

                // Save then trigger AI analysis
                await this.props.record.save();

                if (taskId) {
                    await this.rpc("/web/dataset/call_kw", {
                        model:  "smart.task",
                        method: "action_analyze_with_ai",
                        args:   [[taskId]],
                        kwargs: {},
                    });
                    await this.props.record.load();
                }
            } else {
                this.notification.add(
                    "Transcription failed: " + ((result && result.error) || "Unknown error"),
                    { type: "danger" }
                );
            }
        } catch (err) {
            this.notification.add("Voice processing error: " + err.message, { type: "danger" });
        } finally {
            this.state.isProcessing = false;
            this.state.label        = "🎤 Voice Input";
        }
    }

    // ── Helpers ────────────────────────────────────────────────
    _blobToBase64(blob) {
        return new Promise((resolve, reject) => {
            const reader   = new FileReader();
            reader.onload  = (e) => resolve(e.target.result.split(",")[1]);
            reader.onerror = reject;
            reader.readAsDataURL(blob);
        });
    }
}

registry.category("fields").add("voice_recorder", {
    component:      VoiceRecorderField,
    displayName:    "Voice Recorder",
    supportedTypes: ["char"],
});
