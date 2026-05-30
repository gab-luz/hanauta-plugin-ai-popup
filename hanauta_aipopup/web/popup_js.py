# -*- coding: utf-8 -*-

POPUP_JS = r"""
    let bridge = null;
    let state = {};
    let lastDraftId = 0;
    let attachments = [];
    let optimisticMessages = [];
    let slashMenuOpen = false;
    let slashActiveIndex = 0;
    let pendingVoiceOpen = false;
    let modelsStartPending = false;
    const MODEL_MODAL_SUB_DEFAULT = '__I18N_MODELS_SUB_DEFAULT__';

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
        } else {
          const fallback = document.createElement('span');
          fallback.className = 'backend-fallback-icon';
          fallback.textContent = '◉';
          pill.appendChild(fallback);
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
      const assistant = (state && state.assistant) ? state.assistant : {};
      const assistantName = assistant && assistant.name ? String(assistant.name) : '__I18N_ASSISTANT_NAME__';
      const assistantPhoto = assistant && assistant.avatar_url ? String(assistant.avatar_url) : '';
      const list = (messages || []);
      if (!list.length) {
        const empty = document.createElement('div');
        empty.className = 'empty-state';
        empty.innerHTML =
          `<div class="empty-title">__I18N_EMPTY_TITLE__</div>` +
          `<div class="empty-copy">__I18N_EMPTY_COPY__</div>` +
          `<div class="empty-row"><span class="pill">/voice</span><span class="pill">/image</span><span class="pill">/say</span></div>`;
        convo.appendChild(empty);
        return;
      }
      list.forEach((m) => {
        const outer = document.createElement('div');
        const isUser = (m.role === 'user');
        const eligibleAssistant = (!isUser);
        outer.className = 'message ' + (isUser ? 'you' : 'ai') + (m.pending ? ' pending' : '');
        const avatar = document.createElement('div');
        avatar.className = 'avatar';
        if (isUser) {
          avatar.textContent = '__I18N_YOU_SHORT__';
        } else if (eligibleAssistant && assistantPhoto) {
          avatar.classList.add('has-photo');
          avatar.style.backgroundImage = `url("${esc(assistantPhoto)}")`;
          avatar.textContent = '';
        } else {
          const fallback = eligibleAssistant ? assistantName : (m.title || '__I18N_AI_SHORT__');
          avatar.textContent = String(fallback || '__I18N_AI_SHORT__').trim().slice(0, 2).toUpperCase();
        }
        const bubble = document.createElement('div');
        bubble.className = 'bubble ' + (isUser ? 'you' : 'ai');
        const meta = document.createElement('div');
        meta.className = 'meta';
        const name = document.createElement('div');
        name.className = 'name';
        name.textContent = isUser ? '__I18N_YOU__' : (eligibleAssistant ? assistantName : (m.title || '__I18N_ASSISTANT_NAME__'));
        const time = document.createElement('div');
        time.className = 'time';
        time.textContent = m.timestamp_label || m.time || '';
        meta.appendChild(name);
        meta.appendChild(time);
        const body = document.createElement('div');
        body.className = 'body-text';
        if (m.body_html) {
          body.innerHTML = String(m.body_html);
          body.querySelectorAll('button[data-cmd]').forEach((btn) => {
            btn.addEventListener('click', (e) => {
              e.preventDefault();
              const cmd = btn.getAttribute('data-cmd');
              const cardId = btn.getAttribute('data-card-id') || m.id || '';
              if (cmd === 'launchKobold' && bridge && bridge.launchKobold) {
                bridge.launchKobold();
              } else if (cmd === 'selectBackendAndSay' && bridge && bridge.selectBackendAndSay) {
                const key = btn.getAttribute('data-key') || '';
                const text = btn.getAttribute('data-text') || '';
                const cardRoot = btn.closest('.body-text');
                const pinInput = cardRoot ? cardRoot.querySelector('input[data-role="set-active-backend"]') : null;
                const setActive = !!(pinInput && pinInput.checked);
                if (key && text) {
                  if (bridge.selectBackendAndSayWithOptions) {
                    bridge.selectBackendAndSayWithOptions(String(key), String(text), setActive);
                  } else {
                    bridge.selectBackendAndSay(String(key), String(text));
                  }
                }
              } else if (cmd === 'selectTtsForVoice' && bridge && bridge.selectTtsForVoice) {
                const key = btn.getAttribute('data-key') || '';
                if (key) bridge.selectTtsForVoice(String(key));
              } else if (cmd === 'dismiss' && bridge && bridge.dismissCard && cardId) {
                bridge.dismissCard(cardId);
              }
            });
          });
        } else {
          body.textContent = m.text || '';
        }
        bubble.appendChild(meta);
        bubble.appendChild(body);

        if (m.chips && m.chips.length > 0) {
          const chipsWrap = document.createElement('div');
          chipsWrap.className = 'chips-wrap';
          m.chips.forEach((chip) => {
            const chipSpan = document.createElement('span');
            chipSpan.className = 'chip-pill';
            chipSpan.textContent = chip;
            chipsWrap.appendChild(chipSpan);
          });
          bubble.appendChild(chipsWrap);
        }

        if (m.audio_path) {
          const playing = !!(m.is_active_audio && m.audio_playing);
          const card = document.createElement('button');
          card.className = 'audio-card' + (playing ? ' is-playing' : '');
          card.type = 'button';
          card.addEventListener('click', () => toggleAudio(String(m.audio_path)));

          const play = document.createElement('div');
          play.className = 'audio-play';
          const icon = document.createElement('span');
          icon.className = 'md3-icon';
          icon.textContent = playing ? '⏸' : '▶';
          play.appendChild(icon);

          const wave = document.createElement('div');
          wave.className = 'audio-wave';
          const samples = Array.isArray(m.audio_waveform) ? m.audio_waveform : [];
          const stub = [18, 26, 42, 58, 73, 54, 37, 24, 33, 49, 67, 54, 39, 28, 34, 51, 45, 30, 22, 36, 48, 41, 27, 22, 31, 44, 28, 18];
          const values = (samples && samples.length) ? samples : stub;
          const activeCut = Math.max(6, Math.min(values.length, playing ? 16 : 10));
          values.slice(0, 28).forEach((amp, idx) => {
            const bar = document.createElement('span');
            const a = Math.max(0, Math.min(100, Number(amp || 0)));
            const h = 6 + Math.round((a / 100.0) * 18);
            bar.style.height = h + 'px';
            if (idx < activeCut) bar.classList.add('active');
            wave.appendChild(bar);
          });

          const meta = document.createElement('div');
          meta.className = 'audio-meta';
          const dur = document.createElement('div');
          dur.className = 'audio-duration';
          dur.textContent = m.audio_duration || '';
          const lab = document.createElement('div');
          lab.className = 'audio-label';
          lab.textContent = '__I18N_VOICE__';
          meta.appendChild(dur);
          meta.appendChild(lab);

          card.appendChild(play);
          card.appendChild(wave);
          card.appendChild(meta);
          bubble.appendChild(card);
        }
        outer.appendChild(avatar);
        outer.appendChild(bubble);
        convo.appendChild(outer);
      });
      convo.scrollTop = convo.scrollHeight;
    }

    const SLASH_COMMANDS = [
      { cmd: '/say', snippet: '/say ', desc: 'Say text out loud (TTS)' },
      { cmd: '/speak', snippet: '/speak ', desc: 'Alias for /say' },
      { cmd: '/voice', snippet: '/voice', desc: 'Toggle voice mode' },
      { cmd: '/voice settings', snippet: '/voice settings', desc: 'Open voice settings' },
      { cmd: '/tts', snippet: '/tts', desc: 'Open TTS settings' },
      { cmd: '/image', snippet: '/image ', desc: 'Generate an image' },
      { cmd: '/clear', snippet: '/clear', desc: 'Clear chat' },
    ];

    function slashMatches(query) {
      const q = String(query || '').trim().toLowerCase();
      if (!q) return SLASH_COMMANDS;
      return SLASH_COMMANDS.filter((c) => c.cmd.toLowerCase().indexOf(q) !== -1);
    }

    function currentSlashQuery(value) {
      const raw = String(value || '');
      if (!raw.startsWith('/')) return '';
      const end = raw.indexOf('\n');
      const head = (end === -1 ? raw : raw.slice(0, end));
      if (head.indexOf(' ') !== -1) return head;
      return head;
    }

    function applySlashCommand(c) {
      const el = document.getElementById('composerInput');
      if (!el) return;
      el.value = c.snippet;
      el.focus();
      el.setSelectionRange(el.value.length, el.value.length);
      const menu = document.getElementById('slashMenu');
      if (menu) menu.hidden = true;
      slashMenuOpen = false;
      slashActiveIndex = 0;
    }

    function renderSlashMenu(list) {
      const menu = document.getElementById('slashMenu');
      if (!menu) return;
      if (!list || !list.length) {
        menu.hidden = true;
        slashMenuOpen = false;
        return;
      }
      menu.innerHTML = '';
      list.slice(0, 8).forEach((c, index) => {
        const row = document.createElement('div');
        row.className = 'slash-row' + (index === slashActiveIndex ? ' active' : '');
        const left = document.createElement('div');
        left.className = 'slash-left';
        const cmd = document.createElement('div');
        cmd.className = 'slash-cmd';
        cmd.textContent = c.cmd;
        const desc = document.createElement('div');
        desc.className = 'slash-desc';
        desc.textContent = c.desc || '';
        left.appendChild(cmd);
        left.appendChild(desc);
        row.appendChild(left);
        row.addEventListener('click', () => applySlashCommand(c));
        menu.appendChild(row);
      });
      menu.hidden = false;
      slashMenuOpen = true;
    }

    function updateSlashMenu() {
      const el = document.getElementById('composerInput');
      if (!el) return;
      const q = currentSlashQuery(el.value);
      if (!q.startsWith('/')) {
        const menu = document.getElementById('slashMenu');
        if (menu) menu.hidden = true;
        slashMenuOpen = false;
        slashActiveIndex = 0;
        return;
      }
      const list = slashMatches(q);
      if (slashActiveIndex >= list.length) slashActiveIndex = 0;
      renderSlashMenu(list);
    }

    function renderAttachments() {
      const tray = document.getElementById('attachmentTray');
      if (!tray) return;
      tray.innerHTML = '';
      tray.hidden = attachments.length === 0;
      attachments.forEach((attachment, index) => {
        const chip = document.createElement('div');
        chip.className = 'attachment-chip';
        const icon = document.createElement('span');
        icon.className = 'md3-icon';
        icon.textContent = attachment.kind === 'text' ? 'description' : 'attach_file';
        const name = document.createElement('span');
        name.className = 'attachment-name';
        name.textContent = attachment.name || '__I18N_ATTACHMENT__';
        const remove = document.createElement('button');
        remove.className = 'attachment-remove';
        remove.type = 'button';
        remove.title = '__I18N_REMOVE_ATTACHMENT__';
        remove.textContent = '×';
        remove.addEventListener('click', () => {
          attachments.splice(index, 1);
          renderAttachments();
        });
        chip.appendChild(icon);
        chip.appendChild(name);
        chip.appendChild(remove);
        tray.appendChild(chip);
      });
    }

    function attachmentPromptBlock() {
      if (!attachments.length) return '';
      const parts = attachments.map((attachment) => {
        const name = attachment.name || 'attachment';
        if (attachment.kind === 'text' && attachment.text) {
          return `File: ${name}\n${attachment.text}`;
        }
          return `File: ${name}\n${attachment.note || '__I18N_BINARY_ATTACHMENT_NOTE__'}`;
      });
      return `\n\n[Attachments]\n${parts.join('\n\n---\n')}`;
    }

    function addFiles(files) {
      const list = Array.from(files || []);
      if (!list.length) return;
      list.slice(0, 8).forEach((file) => {
        const item = {
          name: file.name || 'attachment',
          kind: 'file',
          note: `${file.type || 'unknown type'}, ${file.size || 0} bytes`,
        };
        attachments.push(item);
        const isText = /^text\//.test(file.type || '') || /\.(txt|md|json|csv|log|py|js|ts|css|html|xml|yaml|yml|toml)$/i.test(file.name || '');
        if (isText && file.size <= 256000) {
          const reader = new FileReader();
          reader.onload = () => {
            item.kind = 'text';
            item.text = String(reader.result || '').slice(0, 24000);
            renderAttachments();
          };
          reader.onerror = () => {
            item.note = 'Could not read this text file.';
            renderAttachments();
          };
          reader.readAsText(file);
        }
      });
      renderAttachments();
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
      const assistant = (state && state.assistant) ? state.assistant : {};
      const assistantName = assistant && assistant.name ? String(assistant.name) : '__I18N_ASSISTANT_NAME__';
      const assistantPhoto = assistant && assistant.avatar_url ? String(assistant.avatar_url) : '';
      const charName = voice && voice.character_name ? String(voice.character_name) : '';
      if (name) name.textContent = charName;
      if (aiName) aiName.textContent = charName || assistantName;
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
        const url = voice && voice.character_image_url ? String(voice.character_image_url) : (assistantPhoto || '');
        photo.innerHTML = url ? `<img src="${esc(url)}" alt="character"/>` : '';
      }
      document.getElementById('voiceAiCard').classList.toggle('idle', !(voice && voice.response));
      document.getElementById('voiceYouCard').classList.toggle('idle', !(voice && voice.transcript));
    }

    function _fmtModelLine(info) {
      if (!info) return '__I18N_NOT_CONFIGURED__';
      const bits = [];
      if (info.backend) bits.push(String(info.backend));
      if (info.model) bits.push(String(info.model));
      if (info.device) bits.push(String(info.device));
      return bits.join(' • ') || '__I18N_NOT_CONFIGURED__';
    }

    function renderInfoTip(info) {
      const tip = document.getElementById('infoTip');
      if (!tip) return;
      const lines = (info && Array.isArray(info.lines)) ? info.lines : [];
      const title = (info && info.title) ? String(info.title) : '__I18N_LOADED_BACKENDS__';
      const body = lines.length ? lines.map((l) => `<div class="tip-line">${esc(String(l))}</div>`).join('') :
        '<div class="tip-line">__I18N_NO_INFO__</div>';
      tip.innerHTML = `<div class="tip-title">${esc(title)}</div>${body}`;
    }

    function _modelModalSelection() {
      const keys = [];
      const backendOptions = {};
      document.querySelectorAll('#modelBackendList input.check[data-backend-key]').forEach((el) => {
        if (el.checked) keys.push(String(el.getAttribute('data-backend-key') || ''));
      });
      document.querySelectorAll('#modelBackendList select.check-variant[data-backend-key]').forEach((el) => {
        const key = String(el.getAttribute('data-backend-key') || '').trim();
        if (!key) return;
        const variant = String(el.value || '').trim();
        if (!variant) return;
        backendOptions[key] = Object.assign({}, backendOptions[key] || {}, { variant });
      });
      return { backend_keys: keys.filter(Boolean), backend_options: backendOptions };
    }

    function _backendSlotFromRow(item) {
      if (!item) return '';
      const s = String(item.slot || '').trim().toLowerCase();
      if (s) return s;
      const key = String(item.key || '').trim().toLowerCase();
      if (key === 'whisper' || key === 'parakeet') return 'asr';
      if (key === 'koboldcpp' || key === 'openai' || key === 'ollama' || key === 'lmstudio' || key === 'gemini' || key === 'mistral') return 'llm';
      if (key === 'kokorotts' || key === 'pockettts' || key === 'supertonic3' || key === 'kokoclone') return 'tts';
      return '';
    }

    function _enforceExclusiveChecks(changedInput) {
      if (!changedInput || !changedInput.checked) return;
      const changedSlot = String(changedInput.getAttribute('data-slot') || '').trim().toLowerCase();
      if (!changedSlot) return;
      document.querySelectorAll('#modelBackendList input.check[data-backend-key]').forEach((el) => {
        if (el === changedInput) return;
        const slot = String(el.getAttribute('data-slot') || '').trim().toLowerCase();
        if (slot && slot === changedSlot) el.checked = false;
      });
    }

    function _normalizeModelModalSelection() {
      const checks = Array.from(document.querySelectorAll('#modelBackendList input.check[data-backend-key]'));
      const keptBySlot = {};
      checks.forEach((el) => {
        if (!el.checked) return;
        const slot = String(el.getAttribute('data-slot') || '').trim().toLowerCase();
        if (!slot) return;
        if (!keptBySlot[slot]) {
          keptBySlot[slot] = el;
          return;
        }
        el.checked = false;
      });
    }

    function _updateModelModalSelectionHint() {
      const sub = document.getElementById('modelModalSub');
      if (!sub) return;
      const checks = Array.from(document.querySelectorAll('#modelBackendList input.check[data-backend-key]'));
      const picked = { asr: 0, tts: 0, llm: 0 };
      checks.forEach((el) => {
        if (!el.checked) return;
        const slot = String(el.getAttribute('data-slot') || '').trim().toLowerCase();
        if (slot === 'asr' || slot === 'tts' || slot === 'llm') picked[slot] += 1;
      });
      sub.textContent = `Selected: ASR ${picked.asr}/1 • TTS ${picked.tts}/1 • LLM ${picked.llm}/1`;
    }

    function openModelModal(open) {
      const modal = document.getElementById('modelModal');
      if (!modal) return;
      modal.hidden = !open;
      if (!open) {
        const sub = document.getElementById('modelModalSub');
        if (sub) sub.textContent = MODEL_MODAL_SUB_DEFAULT;
        pendingVoiceOpen = false;
      } else {
        const checks = Array.from(document.querySelectorAll('#modelBackendList input.check[data-backend-key]'));
        const anyChecked = checks.some((el) => !!el.checked);
        if (!anyChecked) {
          const taken = { asr: false, tts: false, llm: false };
          checks.forEach((el) => {
            const slot = String(el.getAttribute('data-slot') || '').trim().toLowerCase();
            if ((slot === 'asr' || slot === 'tts' || slot === 'llm') && !taken[slot]) {
              el.checked = true;
              taken[slot] = true;
            }
          });
        }
        _normalizeModelModalSelection();
        _updateModelModalSelectionHint();
      }
    }

    function renderModelLauncher(models, voice) {
      const btn = document.getElementById('modelsBtn');
      if (!btn) return;
      const active = !!(models && models.active);
      const ready = !!(voice && voice.stack_ready);
      const icons = (state && state.ui_icons) ? state.ui_icons : {};
      const icon = document.getElementById('modelsIcon');
      if (icon && (icons.models_stop || icons.models_play)) {
        icon.src = active ? String(icons.models_stop || icons.models_play || '') : String(icons.models_play || icons.models_stop || '');
      }
      btn.classList.toggle('magic-ready', ready);

      const warnBox = document.getElementById('modelWarn');
      if (warnBox) {
        const warn = models && models.warning ? String(models.warning) : '';
        warnBox.hidden = !warn;
        warnBox.textContent = warn;
      }
      const busy = !!(models && models.busy) || !!modelsStartPending;
      const startBtn = document.getElementById('modelsStartBtn');
      const stopBtn = document.getElementById('modelsStopBtn');
      if (startBtn) {
        startBtn.disabled = busy;
        startBtn.textContent = (models && models.needs_confirm) ? '__I18N_START_ANYWAY__' : '__I18N_START_SELECTED__';
      }
      if (stopBtn) stopBtn.disabled = busy || !active;

      const list = document.getElementById('modelBackendList');
      if (list) {
        const selected = new Set(
          Array.from(list.querySelectorAll('input.check[data-backend-key]:checked')).map((el) => String(el.getAttribute('data-backend-key') || ''))
        );
        const rows = Array.isArray(models && models.active_backends) ? models.active_backends : [];
        list.innerHTML = '';
        if (!rows.length) {
          const empty = document.createElement('div');
          empty.className = 'check-note';
          empty.textContent = '__I18N_NOT_CONFIGURED__';
          list.appendChild(empty);
        } else {
          rows.forEach((item) => {
            const key = String(item.key || '');
            const label = String(item.label || key || 'Backend');
            const loaded = !!item.loaded;
            const row = document.createElement('label');
            row.className = 'check-row';
            const input = document.createElement('input');
            input.className = 'check';
            input.type = 'checkbox';
            input.setAttribute('data-backend-key', key);
            input.setAttribute('data-slot', _backendSlotFromRow(item));
            input.checked = selected.has(key) || selected.size === 0;
            input.addEventListener('change', () => {
              _enforceExclusiveChecks(input);
              _normalizeModelModalSelection();
              _updateModelModalSelectionHint();
            });
            const main = document.createElement('div');
            main.className = 'check-main';
            const title = document.createElement('div');
            title.className = 'check-title';
            const desc = String(item.description || '').trim();
            title.textContent = desc ? `${label} (${desc})` : label;
            const note = document.createElement('div');
            note.className = 'check-note';
            note.innerHTML = loaded
              ? '<span style="color:rgba(57,255,136,.92); font-weight:950">__I18N_LOADED__</span>'
              : '__I18N_CONFIGURED__';
            main.appendChild(title);
            main.appendChild(note);
            const variants = Array.isArray(item.variants) ? item.variants : [];
            if (variants.length > 0) {
              const metaRow = document.createElement('div');
              metaRow.className = 'check-meta-row';
              const variantSelect = document.createElement('select');
              variantSelect.className = 'check-variant';
              variantSelect.setAttribute('data-backend-key', key);
              const selectedVariant = String(item.variant_selected || '').trim().toLowerCase();
              variants.forEach((v) => {
                const opt = document.createElement('option');
                opt.value = String(v.value || '');
                opt.textContent = String(v.label || v.value || '');
                if (selectedVariant && String(opt.value).toLowerCase() === selectedVariant) opt.selected = true;
                variantSelect.appendChild(opt);
              });
              metaRow.appendChild(variantSelect);
              main.appendChild(metaRow);
            }
            row.appendChild(input);
            row.appendChild(main);
            list.appendChild(row);
          });
          _normalizeModelModalSelection();
          _updateModelModalSelectionHint();
        }
      }
    }

    function handleVoiceClick() {
      const inVoice = state && state.mode === 'voice';
      if (inVoice) {
        if (bridge && bridge.toggleVoiceMode) bridge.toggleVoiceMode();
        return;
      }
      const models = state && state.models ? state.models : {};
      const active = !!(models && models.active);
      if (!active) {
        pendingVoiceOpen = true;
        const sub = document.getElementById('modelModalSub');
        if (sub) sub.textContent = '__I18N_MODELS_SUB_OPENING_VOICE__';
        openModelModal(true);
        return;
      }
      if (bridge && bridge.toggleVoiceMode) bridge.toggleVoiceMode();
    }

    function render(payload) {
      state = payload || {};
      const inVoice = state.mode === 'voice';
      const icons = state.ui_icons || {};
      const windowEl = document.querySelector('.window');
      if (windowEl) windowEl.classList.toggle('voice-active', inVoice);
      const settingsIcon = document.getElementById('settingsIcon');
      if (settingsIcon && icons.settings) settingsIcon.src = String(icons.settings);
      const closeIcon = document.getElementById('closeIcon');
      if (closeIcon && icons.close) closeIcon.src = String(icons.close);
      const modalCloseIcon = document.getElementById('modalCloseIcon');
      if (modalCloseIcon && icons.close) modalCloseIcon.src = String(icons.close);
      const charactersIcon = document.getElementById('charactersIcon');
      if (charactersIcon && icons.person) charactersIcon.src = String(icons.person);
      const infoIcon = document.getElementById('infoIcon');
      if (infoIcon && icons.info) infoIcon.src = String(icons.info);
      const attachIcon = document.getElementById('attachIcon');
      if (attachIcon && icons.attach_file) attachIcon.src = String(icons.attach_file);
      const sttIcon = document.getElementById('sttIcon');
      if (sttIcon && icons.voice_mic) sttIcon.src = String(icons.voice_mic);
      const archiveIcon = document.getElementById('archiveIcon');
      if (archiveIcon && icons.archive) archiveIcon.src = String(icons.archive);
      const exportIcon = document.getElementById('exportIcon');
      if (exportIcon && icons.download) exportIcon.src = String(icons.download);
      const clearIcon = document.getElementById('clearIcon');
      if (clearIcon && icons.delete_sweep) clearIcon.src = String(icons.delete_sweep);
      const sendIcon = document.getElementById('sendIcon');
      if (sendIcon && icons.send) sendIcon.src = String(icons.send);
      document.getElementById('headerStatus').textContent = state.header_status || '';
      document.getElementById('providerLabel').textContent = state.provider_label || '';
      renderBackends(state.backends || []);
      const serverMessages = state.messages || [];
      if (serverMessages.length) optimisticMessages = [];
      renderMessages(serverMessages.concat(optimisticMessages));
      renderVoice(state.voice || {});
      renderInfoTip(state.info || {});
      renderModelLauncher(state.models || {}, state.voice || {});
      if (!(state && state.models && state.models.busy)) {
        modelsStartPending = false;
      }
      document.getElementById('chatPage').hidden = inVoice;
      document.getElementById('voicePage').hidden = !inVoice;
      const voiceIcon = document.getElementById('voiceIcon');
      if (voiceIcon && (icons.voice_stop || icons.voice_mic)) {
        voiceIcon.src = inVoice ? String(icons.voice_stop || icons.voice_mic || '') : String(icons.voice_mic || icons.voice_stop || '');
      }
      document.getElementById('voiceBtn').classList.toggle('magic-ready', !!(state.voice && state.voice.stack_ready));

      // Auto-enter Voice Mode once models have finished warming up.
      try {
        const models = state && state.models ? state.models : {};
        const active = !!(models && models.active);
        const busy = !!(models && models.busy);
        if (pendingVoiceOpen && !inVoice && active && !busy) {
          pendingVoiceOpen = false;
          openModelModal(false);
          if (bridge && bridge.toggleVoiceMode) bridge.toggleVoiceMode();
        }
      } catch (_err) {}

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
      const extra = attachmentPromptBlock();
      if ((!text && !extra) || !bridge || !bridge.sendPrompt) return;
      const outgoing = (text || '__I18N_REVIEW_ATTACHMENTS__') + extra;
      optimisticMessages.push({
        role: 'user',
        title: '__I18N_YOU__',
        timestamp_label: '__I18N_NOW__',
        body_html: '<p>' + esc(outgoing).replace(/\n/g, '<br>') + '</p>',
      });
      renderMessages((state.messages || []).concat(optimisticMessages));
      bridge.sendPrompt(outgoing);
      el.value = '';
      attachments = [];
      renderAttachments();
    }
    function selectBackend(key) { if (bridge && bridge.selectBackend) bridge.selectBackend(key); }
    function toggleAudio(path) { if (bridge && bridge.toggleAudio) bridge.toggleAudio(path); }

    document.getElementById('sendBtn').addEventListener('click', sendNow);
    document.getElementById('attachBtn').addEventListener('click', () => {
      if (bridge && bridge.pickAttachments) bridge.pickAttachments();
    });
    document.getElementById('sttBtn').addEventListener('click', () => bridge && bridge.transcribeOnce && bridge.transcribeOnce());
    document.getElementById('clearBtn').addEventListener('click', () => bridge && bridge.clearChat && bridge.clearChat());
    document.getElementById('archiveBtn').addEventListener('click', () => bridge && bridge.archiveChat && bridge.archiveChat());
    document.getElementById('exportBtn').addEventListener('click', () => bridge && bridge.exportChat && bridge.exportChat());
    document.getElementById('settingsBtn').addEventListener('click', () => bridge && bridge.openSettings && bridge.openSettings());
    document.getElementById('charactersBtn').addEventListener('click', () => bridge && bridge.openCharacters && bridge.openCharacters());
    document.getElementById('voiceBtn').addEventListener('click', handleVoiceClick);
    document.getElementById('modelsBtn').addEventListener('click', () => {
      const active = !!(state && state.models && state.models.active);
      if (active) {
        const sub = document.getElementById('modelModalSub');
        if (sub) sub.textContent = '__I18N_MODELS_SUB_SELECT_TO_STOP__';
        openModelModal(true);
        return;
      }
      openModelModal(true);
    });
    document.getElementById('modelModalCloseBtn').addEventListener('click', () => openModelModal(false));
    document.getElementById('modelsRefreshBtn').addEventListener('click', () => bridge && bridge.refreshState && bridge.refreshState());
    document.getElementById('modelsStartBtn').addEventListener('click', () => {
      if (modelsStartPending) return;
      const sel = _modelModalSelection();
      if (!bridge || !bridge.startVoiceModels) return;
      modelsStartPending = true;
      const startBtn = document.getElementById('modelsStartBtn');
      if (startBtn) startBtn.disabled = true;
      bridge.startVoiceModels(JSON.stringify(sel));
    });
    document.getElementById('modelsStopBtn').addEventListener('click', () => {
      const sel = _modelModalSelection();
      if (!bridge) return;
      if (bridge.stopVoiceModelsWithSelection) {
        bridge.stopVoiceModelsWithSelection(JSON.stringify(sel));
      } else if (bridge.stopVoiceModels) {
        bridge.stopVoiceModels();
      }
    });
    document.getElementById('modelModal').addEventListener('click', (ev) => {
      if (ev.target && ev.target.id === 'modelModal') openModelModal(false);
    });
    document.getElementById('voiceStopBtn').addEventListener('click', () => bridge && bridge.toggleVoiceMode && bridge.toggleVoiceMode());
    document.getElementById('voiceStopTopBtn').addEventListener('click', () => bridge && bridge.toggleVoiceMode && bridge.toggleVoiceMode());
    document.getElementById('voiceBackBtn').addEventListener('click', () => bridge && bridge.toggleVoiceMode && bridge.toggleVoiceMode());
    document.getElementById('closeBtn').addEventListener('click', () => bridge && bridge.closeWindow && bridge.closeWindow());
    document.getElementById('composerInput').addEventListener('keydown', (event) => {
      if (slashMenuOpen) {
        if (event.key === 'ArrowDown') {
          event.preventDefault();
          slashActiveIndex = Math.min(slashActiveIndex + 1, 7);
          updateSlashMenu();
          return;
        }
        if (event.key === 'ArrowUp') {
          event.preventDefault();
          slashActiveIndex = Math.max(0, slashActiveIndex - 1);
          updateSlashMenu();
          return;
        }
        if (event.key === 'Enter' || event.key === 'Tab') {
          const el = document.getElementById('composerInput');
          const q = currentSlashQuery(el ? el.value : '');
          const list = slashMatches(q);
          if (list && list.length) {
            event.preventDefault();
            applySlashCommand(list[Math.max(0, Math.min(slashActiveIndex, list.length - 1))]);
            return;
          }
        }
        if (event.key === 'Escape') {
          const menu = document.getElementById('slashMenu');
          if (menu) menu.hidden = true;
          slashMenuOpen = false;
          slashActiveIndex = 0;
          return;
        }
      }
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendNow();
      }
    });
    document.getElementById('composerInput').addEventListener('input', updateSlashMenu);

    new QWebChannel(qt.webChannelTransport, function(channel) {
      bridge = channel.objects.bridge;
      bridge.stateChanged.connect(function(raw) {
        try { render(JSON.parse(raw)); } catch (_err) {}
      });
      if (bridge.attachmentsPicked) {
        bridge.attachmentsPicked.connect(function(raw) {
          try {
            const items = JSON.parse(raw || '[]');
            if (Array.isArray(items)) {
              attachments = attachments.concat(items);
              renderAttachments();
            }
          } catch (_err) {}
        });
      }
      if (bridge && bridge.jsReady) bridge.jsReady();
    });
"""
