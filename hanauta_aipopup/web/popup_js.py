# -*- coding: utf-8 -*-

POPUP_JS = r"""
    let bridge = null;
    let state = {};
    let lastDraftId = 0;

    function esc(s) {
      const map = {"&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"};
      return String(s || '').replace(/[&<>\"']/g, function(c) {
        return map[c] || c;
      });
    }

    function renderBackends(backends) {
      const row = document.getElementById('backendRow');
      if (!row) return;
      row.innerHTML = '';
      (backends || []).forEach((b) => {
        const pill = document.createElement('div');
        pill.className = 'backend-pill' + (b.active ? ' active' : '');
        pill.onclick = () => selectBackend(b.key);
        if (b.icon) {
          const img = document.createElement('img');
          img.src = b.icon;
          pill.appendChild(img);
        }
        const span = document.createElement('span');
        span.textContent = b.label || b.key;
        pill.appendChild(span);
        row.appendChild(pill);
      });
    }

    function renderMessages(messages) {
      const convo = document.getElementById('conversation');
      if (!convo) return;
      convo.innerHTML = '';
      (messages || []).forEach((m) => {
        const outer = document.createElement('div');
        outer.className = 'message ' + (m.role === 'user' ? 'you' : 'ai');
        const avatar = document.createElement('div');
        avatar.className = 'avatar';
        avatar.textContent = (m.role === 'user') ? 'Y' : 'AI';
        const bubble = document.createElement('div');
        bubble.className = 'bubble ' + ((m.role === 'user') ? 'you' : 'ai');
        const meta = document.createElement('div');
        meta.className = 'meta';
        const name = document.createElement('div');
        name.className = 'name';
        name.textContent = m.title || ((m.role === 'user') ? 'You' : 'Hanauta AI');
        const time = document.createElement('div');
        time.className = 'time';
        time.textContent = m.time || '';
        meta.appendChild(name);
        meta.appendChild(time);
        const body = document.createElement('div');
        body.className = 'body-text';
        body.textContent = m.text || '';
        bubble.appendChild(meta);
        bubble.appendChild(body);
        outer.appendChild(avatar);
        outer.appendChild(bubble);
        convo.appendChild(outer);
      });
      convo.scrollTop = convo.scrollHeight;
    }

    function renderVoice(voice) {
      const name = document.getElementById('voiceName');
      const status = document.getElementById('voiceStatus');
      const note = document.getElementById('voiceStatusNote');
      const you = document.getElementById('voiceTranscript');
      const ai = document.getElementById('voiceCaption');
      const orb = document.getElementById('orbWrap');
      const photo = document.getElementById('orbPhoto');
      const aiName = document.getElementById('voiceAiName');
      if (name) name.textContent = voice && voice.character_name ? String(voice.character_name) : '';
      if (aiName) aiName.textContent = voice && voice.ai_name ? String(voice.ai_name) : 'Hanauta AI';
      if (status) status.textContent = voice && voice.status ? String(voice.status) : '';
      if (note) note.textContent = voice && voice.note ? String(voice.note) : '';
      function hlLastWord(text) {
        const raw = String(text || '');
        const trimmed = raw.trim();
        if (!trimmed) return '';
        const m = trimmed.match(/^(.*?)(\\S+)\\s*$/);
        if (!m) return esc(trimmed);
        const head = m[1] || '';
        const last = m[2] || '';
        return esc(head) + '<span class=\"word-hl\">' + esc(last) + '</span>';
      }
      if (you) {
        const t = voice && voice.transcript ? String(voice.transcript) : '';
        // Best-effort "now speaking" highlight: emphasize the last word we have so far.
        // (True timestamp karaoke needs word-level timestamps from the STT backend.)
        you.innerHTML = t ? hlLastWord(t) : '';
      }
      if (ai) ai.textContent = voice && voice.response ? String(voice.response) : '';
      const speaking = !!(voice && voice.speaking);
      const listening = !!(voice && voice.listening);
      const emotion = voice && voice.emotion ? String(voice.emotion) : 'neutral';
      if (orb) {
        orb.classList.toggle('speaking', speaking);
        orb.classList.toggle('listening', listening);
        orb.className = orb.className.replace(/\bemotion-[a-z0-9_-]+\b/g, '').trim();
        if (emotion && emotion !== 'neutral') orb.classList.add('emotion-' + emotion);
      }
      if (photo) {
        const url = voice && voice.character_photo ? String(voice.character_photo) : '';
        photo.innerHTML = url ? `<img src="${esc(url)}" alt="character"/>` : '';
      }
      document.getElementById('voiceAiCard').classList.toggle('idle', !(voice && voice.response));
      document.getElementById('voiceYouCard').classList.toggle('idle', !(voice && voice.transcript));
    }

    function _fmtModelLine(info) {
      if (!info) return 'Not configured';
      const bits = [];
      if (info.backend) bits.push(String(info.backend));
      if (info.model) bits.push(String(info.model));
      if (info.device) bits.push(String(info.device));
      return bits.join(' • ') || 'Not configured';
    }

    function renderInfoTip(info) {
      const tip = document.getElementById('infoTip');
      if (!tip) return;
      const lines = (info && Array.isArray(info.lines)) ? info.lines : [];
      const title = (info && info.title) ? String(info.title) : 'Loaded Backends';
      const body = lines.length ? lines.map((l) => `<div class="tip-line">${esc(String(l))}</div>`).join('') :
        '<div class="tip-line">No info yet.</div>';
      tip.innerHTML = `<div class="tip-title">${esc(title)}</div>${body}`;
    }

    function _modelModalSelection() {
      return {
        stt: !!document.getElementById('modelCheckStt')?.checked,
        llm: !!document.getElementById('modelCheckLlm')?.checked,
        tts: !!document.getElementById('modelCheckTts')?.checked,
      };
    }

    function openModelModal(open) {
      const modal = document.getElementById('modelModal');
      if (!modal) return;
      modal.hidden = !open;
    }

    function renderModelLauncher(models, voice) {
      const btn = document.getElementById('modelsBtn');
      if (!btn) return;
      const active = !!(models && models.active);
      const ready = !!(voice && voice.stack_ready);
      btn.textContent = active ? '■' : '▶';
      btn.classList.toggle('magic-ready', ready);

      const warnBox = document.getElementById('modelWarn');
      if (warnBox) {
        const warn = models && models.warning ? String(models.warning) : '';
        warnBox.hidden = !warn;
        warnBox.textContent = warn;
      }
      const busy = !!(models && models.busy);
      const startBtn = document.getElementById('modelsStartBtn');
      const stopBtn = document.getElementById('modelsStopBtn');
      if (startBtn) {
        startBtn.disabled = busy;
        startBtn.textContent = (models && models.needs_confirm) ? 'Start Anyway' : 'Start Selected';
      }
      if (stopBtn) stopBtn.disabled = busy || !active;

      const noteStt = document.getElementById('modelNoteStt');
      const noteLlm = document.getElementById('modelNoteLlm');
      const noteTts = document.getElementById('modelNoteTts');
      if (noteStt) noteStt.innerHTML = `Configured: <b>${esc(_fmtModelLine(models && models.stt))}</b>` + ((models && models.stt && models.stt.loaded) ? ' <span style="color:rgba(57,255,136,.92); font-weight:950">loaded</span>' : '');
      if (noteLlm) noteLlm.innerHTML = `Configured: <b>${esc(_fmtModelLine(models && models.llm))}</b>` + ((models && models.llm && models.llm.loaded) ? ' <span style="color:rgba(57,255,136,.92); font-weight:950">loaded</span>' : '');
      if (noteTts) noteTts.innerHTML = `Configured: <b>${esc(_fmtModelLine(models && models.tts))}</b>` + ((models && models.tts && models.tts.loaded) ? ' <span style="color:rgba(57,255,136,.92); font-weight:950">loaded</span>' : '');

      if (models && models.selection) {
        const sel = models.selection;
        const cStt = document.getElementById('modelCheckStt');
        const cLlm = document.getElementById('modelCheckLlm');
        const cTts = document.getElementById('modelCheckTts');
        if (cStt) cStt.checked = !!sel.stt;
        if (cLlm) cLlm.checked = !!sel.llm;
        if (cTts) cTts.checked = !!sel.tts;
      }
    }

    function render(payload) {
      state = payload || {};
      const inVoice = state.mode === 'voice';
      const windowEl = document.querySelector('.window');
      if (windowEl) windowEl.classList.toggle('voice-active', inVoice);
      document.getElementById('headerStatus').textContent = state.header_status || '';
      document.getElementById('providerLabel').textContent = state.provider_label || '';
      renderBackends(state.backends || []);
      renderMessages(state.messages || []);
      renderVoice(state.voice || {});
      renderInfoTip(state.info || {});
      renderModelLauncher(state.models || {}, state.voice || {});
      document.getElementById('chatPage').hidden = inVoice;
      document.getElementById('voicePage').hidden = !inVoice;
      document.getElementById('voiceBtn').textContent = inVoice ? '■' : '🎙';
      document.getElementById('voiceBtn').classList.toggle('magic-ready', !!(state.voice && state.voice.stack_ready));

      try {
        const draft = state.draft || {};
        const did = Number(draft.id || 0);
        const text = String(draft.text || '');
        if (!inVoice && did && did !== lastDraftId && text) {
          const el = document.getElementById('composerInput');
          if (el && (!el.value || !el.value.trim())) {
            el.value = text;
            el.focus();
            lastDraftId = did;
            if (bridge && bridge.ackDraft) bridge.ackDraft(did);
          }
        }
      } catch (_err) {}
    }

    function sendNow() {
      const el = document.getElementById('composerInput');
      const text = (el.value || '').trim();
      if (!text || !bridge || !bridge.sendPrompt) return;
      bridge.sendPrompt(text);
      el.value = '';
    }
    function selectBackend(key) { if (bridge && bridge.selectBackend) bridge.selectBackend(key); }
    function toggleAudio(path) { if (bridge && bridge.toggleAudio) bridge.toggleAudio(path); }

    document.getElementById('sendBtn').addEventListener('click', sendNow);
    document.getElementById('sttBtn').addEventListener('click', () => bridge && bridge.transcribeOnce && bridge.transcribeOnce());
    document.getElementById('clearBtn').addEventListener('click', () => bridge && bridge.clearChat && bridge.clearChat());
    document.getElementById('archiveBtn').addEventListener('click', () => bridge && bridge.archiveChat && bridge.archiveChat());
    document.getElementById('exportBtn').addEventListener('click', () => bridge && bridge.exportChat && bridge.exportChat());
    document.getElementById('settingsBtn').addEventListener('click', () => bridge && bridge.openSettings && bridge.openSettings());
    document.getElementById('charactersBtn').addEventListener('click', () => bridge && bridge.openCharacters && bridge.openCharacters());
    document.getElementById('voiceBtn').addEventListener('click', () => bridge && bridge.toggleVoiceMode && bridge.toggleVoiceMode());
    document.getElementById('modelsBtn').addEventListener('click', () => {
      const active = !!(state && state.models && state.models.active);
      if (active) {
        if (bridge && bridge.stopVoiceModels) bridge.stopVoiceModels();
        return;
      }
      openModelModal(true);
    });
    document.getElementById('modelModalCloseBtn').addEventListener('click', () => openModelModal(false));
    document.getElementById('modelsRefreshBtn').addEventListener('click', () => bridge && bridge.refreshState && bridge.refreshState());
    document.getElementById('modelsStartBtn').addEventListener('click', () => {
      const sel = _modelModalSelection();
      if (!bridge || !bridge.startVoiceModels) return;
      bridge.startVoiceModels(JSON.stringify(sel));
    });
    document.getElementById('modelsStopBtn').addEventListener('click', () => bridge && bridge.stopVoiceModels && bridge.stopVoiceModels());
    document.getElementById('modelModal').addEventListener('click', (ev) => {
      if (ev.target && ev.target.id === 'modelModal') openModelModal(false);
    });
    document.getElementById('voiceStopBtn').addEventListener('click', () => bridge && bridge.toggleVoiceMode && bridge.toggleVoiceMode());
    document.getElementById('voiceStopTopBtn').addEventListener('click', () => bridge && bridge.toggleVoiceMode && bridge.toggleVoiceMode());
    document.getElementById('voiceBackBtn').addEventListener('click', () => bridge && bridge.toggleVoiceMode && bridge.toggleVoiceMode());
    document.getElementById('closeBtn').addEventListener('click', () => bridge && bridge.closeWindow && bridge.closeWindow());
    document.getElementById('composerInput').addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendNow();
      }
    });

    new QWebChannel(qt.webChannelTransport, function(channel) {
      bridge = channel.objects.bridge;
      bridge.stateChanged.connect(function(raw) {
        try { render(JSON.parse(raw)); } catch (_err) {}
      });
      if (bridge && bridge.jsReady) bridge.jsReady();
    });
"""
