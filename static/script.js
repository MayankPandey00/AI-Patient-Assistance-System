let isRecording = false;
        let activeRole = null;
        let audioCtx = null;
        let mediaStream = null;
        let processor = null;
        let recordedChunks = [];

        function showAlert(message, isError = false) {
            const box = document.getElementById('alertBox');
            const msg = document.getElementById('alertMessage');
            msg.innerText = message;
            box.style.display = 'flex';
            box.style.backgroundColor = isError ? '#fef2f2' : '#f0fdf4';
            box.style.color = isError ? '#991b1b' : '#166534';
            box.style.border = isError ? '1px solid #fecaca' : '1px solid #bbf7d0';
        }

        // =========================================================================
        // MODULE 1: VOICE INPUT MODULE (Pure 16kHz PCM .WAV Hardware Mic Recorder)
        // Sends genuine .wav file directly to Python SpeechRecognition (No FFmpeg!)
        // =========================================================================
        async function toggleMicRecording(role) {
            if (isRecording) {
                await stopRecordingAndProcess();
                return;
            }

            try {
                mediaStream = await navigator.mediaDevices.getUserMedia({
                    audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
                });

                audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                const source = audioCtx.createMediaStreamSource(mediaStream);
                processor = audioCtx.createScriptProcessor(4096, 1, 1);
                recordedChunks = [];

                const volBarId = role === 'PATIENT' ? 'patientVolumeBar' : 'doctorVolumeBar';
                const volBar = document.getElementById(volBarId);

                processor.onaudioprocess = function(e) {
                    if (!isRecording) return;
                    const inputData = e.inputBuffer.getChannelData(0);
                    recordedChunks.push(new Float32Array(inputData));

                    // Calculate live volume level so user sees mic is working!
                    let sum = 0;
                    for (let i = 0; i < inputData.length; i++) sum += inputData[i] * inputData[i];
                    let rms = Math.sqrt(sum / inputData.length);
                    let pct = Math.min(100, Math.round(rms * 400));
                    volBar.style.width = pct + '%';
                };

                source.connect(processor);
                processor.connect(audioCtx.destination);

                isRecording = true;
                activeRole = role;
                setMicUI(role, true);

            } catch (err) {
                showAlert("Microphone Error: " + err.message + ". Please open http://localhost:5000 and allow microphone permission.", true);
            }
        }

        async function stopRecordingAndProcess() {
            const role = activeRole;
            isRecording = false;
            setMicUI(role, false);

            const sampleRate = audioCtx ? audioCtx.sampleRate : 44100;
            if (processor) processor.disconnect();
            if (mediaStream) mediaStream.getTracks().forEach(t => t.stop());
            if (audioCtx) await audioCtx.close();

            const recBox = document.getElementById(role === 'PATIENT' ? 'patientRecognizedText' : 'doctorRecognizedText');
            recBox.innerText = "⏳ Module 2 (Python SpeechRecognition) converting voice to text...";

            const wavBlob = createWavBlob(recordedChunks, sampleRate);
            await sendWavToPythonSTT(wavBlob, role);
        }

        function createWavBlob(buffers, sampleRate) {
            let totalLen = 0;
            for (let b of buffers) totalLen += b.length;
            const samples = new Float32Array(totalLen);
            let offset = 0;
            for (let b of buffers) {
                samples.set(b, offset);
                offset += b.length;
            }

            const buffer = new ArrayBuffer(44 + samples.length * 2);
            const view = new DataView(buffer);
            const writeStr = (pos, str) => {
                for (let i = 0; i < str.length; i++) view.setUint8(pos + i, str.charCodeAt(i));
            };

            writeStr(0, 'RIFF');
            view.setUint32(4, 36 + samples.length * 2, true);
            writeStr(8, 'WAVE');
            writeStr(12, 'fmt ');
            view.setUint32(16, 16, true);
            view.setUint16(20, 1, true);
            view.setUint16(22, 1, true);
            view.setUint32(24, sampleRate, true);
            view.setUint32(28, sampleRate * 2, true);
            view.setUint16(32, 2, true);
            view.setUint16(34, 16, true);
            writeStr(36, 'data');
            view.setUint32(40, samples.length * 2, true);

            let index = 44;
            for (let i = 0; i < samples.length; i++, index += 2) {
                let s = Math.max(-1, Math.min(1, samples[i]));
                view.setInt16(index, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
            }
            return new Blob([view], { type: 'audio/wav' });
        }

        async function sendWavToPythonSTT(wavBlob, speakerRole) {
            const patientLang = document.getElementById('patientLang').value;
            const doctorLang = document.getElementById('doctorLang').value;
            const srcLang = speakerRole === 'PATIENT' ? patientLang : doctorLang;
            const targetLang = speakerRole === 'PATIENT' ? doctorLang : patientLang;
            const patientId = document.getElementById('patientId').value || 'PT-101';

            const formData = new FormData();
            formData.append('audio', wavBlob, 'voice_input.wav');
            formData.append('speaker_role', speakerRole);
            formData.append('src_lang', srcLang);
            formData.append('target_lang', targetLang);
            formData.append('patient_id', patientId);

            try {
                const response = await fetch('/api/voice-pipeline', {
                    method: 'POST',
                    body: formData
                });
                const data = await response.json();

                if (data.success) {
                    updateTerminalsAndPlayAudio(speakerRole, data.original_text, data.translated_text, data.tts_url, srcLang, targetLang);
                } else {
                    const recBox = document.getElementById(speakerRole === 'PATIENT' ? 'patientRecognizedText' : 'doctorRecognizedText');
                    recBox.innerText = data.error;
                    showAlert(data.error, true);
                }
            } catch (err) {
                showAlert("Backend connection error: Ensure 'python app.py' is running.", true);
            }
        }

        function setMicUI(role, recording) {
            const isPatient = role === 'PATIENT';
            const btn = document.getElementById(isPatient ? 'patientMicBtn' : 'doctorMicBtn');
            const status = document.getElementById(isPatient ? 'patientMicStatus' : 'doctorMicStatus');
            const volBar = document.getElementById(isPatient ? 'patientVolumeBar' : 'doctorVolumeBar');

            if (recording) {
                btn.classList.add('recording');
                btn.innerText = '⏹️';
                status.innerText = '🔴 Recording Live... Speak now, then click ⏹️ to Translate!';
                status.style.color = '#dc2626';
            } else {
                btn.classList.remove('recording');
                btn.innerText = '🎤';
                status.innerText = 'Click Mic to Speak → Click Again to Translate';
                status.style.color = '#475569';
                volBar.style.width = '0%';
            }
        }

        // =========================================================================
        // TEXT & EMERGENCY FAST-TRACK PIPELINE
        // =========================================================================
        async function sendManualText(speakerRole) {
            const inputEl = document.getElementById(speakerRole === 'PATIENT' ? 'patientTextInput' : 'doctorTextInput');
            const text = inputEl.value.trim();
            if (!text) return;
            inputEl.value = '';

            const patientLang = document.getElementById('patientLang').value;
            const doctorLang = document.getElementById('doctorLang').value;
            const srcLang = speakerRole === 'PATIENT' ? patientLang : doctorLang;

            await executeTextPipeline(text, srcLang, speakerRole);
        }

        async function sendEmergency(phrase, srcLang, speakerRole) {
            if (speakerRole === 'PATIENT') document.getElementById('patientLang').value = srcLang;
            else document.getElementById('doctorLang').value = srcLang;
            await executeTextPipeline(phrase, srcLang, speakerRole);
        }

        async function executeTextPipeline(text, srcLang, speakerRole) {
            const patientLang = document.getElementById('patientLang').value;
            const doctorLang = document.getElementById('doctorLang').value;
            const targetLang = speakerRole === 'PATIENT' ? doctorLang : patientLang;
            const patientId = document.getElementById('patientId').value || 'PT-101';

            try {
                const res = await fetch('/api/text-pipeline', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        text: text,
                        speaker_role: speakerRole,
                        src_lang: srcLang,
                        target_lang: targetLang,
                        patient_id: patientId
                    })
                });
                const data = await res.json();
                if (data.success) {
                    updateTerminalsAndPlayAudio(speakerRole, data.original_text, data.translated_text, data.tts_url, srcLang, targetLang);
                } else {
                    showAlert(data.error, true);
                }
            } catch (err) {
                showAlert("Cannot connect to Flask backend. Ensure 'python app.py' is running.", true);
            }
        }

        // =========================================================================
        // MODULE 4: RESPONSE GENERATION (UI + gTTS Audio Playback)
        // =========================================================================
        function updateTerminalsAndPlayAudio(speakerRole, originalText, translatedText, ttsUrl, srcLang, targetLang) {
            if (speakerRole === 'PATIENT') {
                document.getElementById('patientRecognizedText').innerText = originalText;
                document.getElementById('doctorTranslatedOutput').innerText = translatedText;
                const player = document.getElementById('doctorAudioPlayer');
                player.src = ttsUrl + "&t=" + Date.now();
                player.play().catch(() => {});
            } else {
                document.getElementById('doctorRecognizedText').innerText = originalText;
                document.getElementById('patientTranslatedOutput').innerText = translatedText;
                const player = document.getElementById('patientAudioPlayer');
                player.src = ttsUrl + "&t=" + Date.now();
                player.play().catch(() => {});
            }

            addLogEntry(speakerRole, originalText, translatedText, srcLang, targetLang);
        }

        function addLogEntry(role, original, translated, srcLang, targetLang) {
            const feed = document.getElementById('conversationFeed');
            const empty = document.getElementById('emptyFeedText');
            if (empty) empty.remove();

            const item = document.createElement('div');
            item.className = 'log-item ' + (role === 'PATIENT' ? 'patient' : 'doctor');
            item.innerHTML = `
                <div style="display:flex; justify-content:space-between; font-weight:700; margin-bottom:4px;">
                    <span>${role === 'PATIENT' ? '🗣️ Patient → Doctor' : '👨‍⚕️ Doctor → Patient'} (${srcLang.toUpperCase()} → ${targetLang.toUpperCase()})</span>
                    <span style="color:#64748b; font-size:0.72rem;">🔒 Encrypted in DB</span>
                </div>
                <div style="color:#475569;"><strong>Original:</strong> ${original}</div>
                <div style="color:#0f172a; font-weight:600; margin-top:2px;"><strong>Translated:</strong> ${translated}</div>
            `;
            feed.prepend(item);
        }

        // =========================================================================
        // MODULE 5 & 6: AUTHORISED RETRIEVAL OF ENCRYPTED PATIENT HISTORY
        // =========================================================================
        async function fetchEncryptedHistory() {
            const patientId = document.getElementById('patientId').value || 'PT-101';
            const staffPin = document.getElementById('staffPinInput').value;

            try {
                const res = await fetch('/api/history', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ patient_id: patientId, staff_pin: staffPin })
                });
                const data = await res.json();
                if (!data.success) {
                    showAlert(data.error, true);
                    return;
                }

                const feed = document.getElementById('conversationFeed');
                feed.innerHTML = '';
                if (data.records.length === 0) {
                    feed.innerHTML = `<div style="text-align:center; color:#94a3b8; margin-top:40px;">No stored records found for ${patientId}</div>`;
                    return;
                }

                showAlert(`Decrypted ${data.records.length} medical record(s) for Patient ${patientId} using Authorised Staff PIN.`);
                data.records.reverse().forEach(r => {
                    addLogEntry(r.speaker_role, r.original_text, r.translated_text, r.source_language, r.target_language);
                });
            } catch (err) {
                showAlert("Error loading history from database.", true);
            }
        }