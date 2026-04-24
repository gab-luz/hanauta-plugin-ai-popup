# -*- coding: utf-8 -*-

from __future__ import annotations

from .popup_css import POPUP_CSS
from .popup_js import POPUP_JS

_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Hanauta AI</title>
  <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
  <style>
__POPUP_CSS__
__POPUP_THEME_CSS__
  </style>
</head>
<body>
  <!-- Material Symbols (MD3) ligature icons: we rely on system-installed fonts. -->
  <div class="window">
    <div class="topbar">
      <div class="brand">
        <div class="logo">◉</div>
        <div class="title-wrap">
          <div style="display:flex; align-items:center; gap:8px;">
            <div class="title">Hanauta AI</div>
            <div class="info-pop" title="Info">
              <div class="info-dot" aria-label="Information">i</div>
              <div class="info-tip" id="infoTip"><div class="tip-title">Loaded Backends</div><div class="tip-line">Loading...</div></div>
            </div>
          </div>
          <div class="status" id="headerStatus"></div>
        </div>
      </div>
      <div class="actions">
        <button class="icon-btn" id="modelsBtn" title="Start/Stop voice backends" aria-label="Start/Stop models"><span class="md3-icon" id="modelsIcon" aria-hidden="true">play_arrow</span></button>
        <button class="icon-btn" id="voiceBtn" title="Voice mode" aria-label="Voice mode"><span class="md3-icon" id="voiceIcon" aria-hidden="true">mic</span></button>
        <button class="icon-btn" id="settingsBtn" title="Settings" aria-label="Settings"><span class="md3-icon" aria-hidden="true">settings</span></button>
        <button class="icon-btn" id="charactersBtn" title="Characters" aria-label="Characters"><span class="md3-icon" aria-hidden="true">person</span></button>
        <button class="icon-btn" id="closeBtn" title="Close" aria-label="Close"><span class="md3-icon" aria-hidden="true">close</span></button>
      </div>
    </div>
    <div class="body">
      <div class="chat-page" id="chatPage">
        <div class="backend-row" id="backendRow"></div>
        <div class="conversation" id="conversation"></div>
        <div class="composer">
          <div class="attachment-tray" id="attachmentTray" hidden></div>
          <textarea id="composerInput" placeholder="Message the model... Enter to send"></textarea>
          <div class="composer-row">
            <div class="provider" id="providerLabel"></div>
            <input type="file" id="attachmentInput" multiple hidden />
            <button class="send-btn secondary" id="attachBtn" title="Add attachments" aria-label="Add attachments"><span class="md3-icon btn-icon" aria-hidden="true">attach_file</span></button>
            <button class="send-btn secondary" id="sttBtn" title="Dictate (speech to text)" aria-label="Dictate"><span class="md3-icon btn-icon" aria-hidden="true">mic</span></button>
            <button class="send-btn secondary" id="archiveBtn" title="Archive chat" aria-label="Archive chat"><span class="md3-icon btn-icon" aria-hidden="true">archive</span></button>
            <button class="send-btn secondary" id="exportBtn" title="Export chat" aria-label="Export chat"><span class="md3-icon btn-icon" aria-hidden="true">download</span></button>
            <button class="send-btn secondary" id="clearBtn" title="Clear chat" aria-label="Clear chat"><span class="md3-icon btn-icon" aria-hidden="true">delete_sweep</span></button>
            <button class="send-btn" id="sendBtn" title="Send message" aria-label="Send message"><span class="md3-icon btn-icon" aria-hidden="true">send</span></button>
          </div>
        </div>
      </div>
      <div class="voice-page" id="voicePage" hidden>
        <div class="voice-shell">
          <div class="voice-topbar">
            <div class="voice-topbar-left">
              <button class="voice-nav-btn" id="voiceBackBtn">← Back</button>
            </div>
            <div class="voice-topbar-right">
              <button class="voice-stop-btn-top" id="voiceStopTopBtn">Stop</button>
            </div>
          </div>
          <div class="voice-top">
            <div class="voice-pill">Hands-free Voice Mode</div>
            <div class="voice-name" id="voiceName"></div>
            <div class="voice-status" id="voiceStatus"></div>
            <div class="voice-sub">Stay in the conversation. Start talking anytime.</div>
            <div class="orb-scene">
              <div class="orb-wrap" id="orbWrap">
                <div class="orb-glow"></div>
                <div class="orb-aura"></div>
                <div class="orb-core"></div>
                <div class="orb-liquid"></div>
                <div class="orb-ring"></div>
                <div class="orb-ring-2"></div>
                <div class="orb-ring-3"></div>
                <div class="orb-glass"></div>
                <div class="orb-photo-border">
                  <div class="orb-photo" id="orbPhoto"></div>
                </div>
              </div>
            </div>
          </div>
          <div class="caption-stack">
            <div class="caption-card you" id="voiceYouCard">
              <div class="caption-head">
                <div class="caption-badge">YOU</div>
                <div class="caption-labels">
                  <div class="caption-name">You</div>
                  <div class="caption-meta">Speech to text</div>
                </div>
              </div>
              <div class="caption-text" id="voiceTranscript"></div>
            </div>
            <div class="caption-card ai" id="voiceAiCard">
              <div class="caption-head">
                <div class="caption-badge">AI</div>
                <div class="caption-labels">
                  <div class="caption-name" id="voiceAiName">Hanauta AI</div>
                  <div class="caption-meta">Spoken reply</div>
                </div>
              </div>
              <div class="caption-text" id="voiceCaption"></div>
            </div>
          </div>
          <div class="voice-card">
            <div class="label">Status</div>
            <div class="value" id="voiceStatusNote">Voice mode is ready.</div>
          </div>
          <div class="voice-controls">
            <button class="voice-stop" id="voiceStopBtn">Return to chat</button>
          </div>
        </div>
      </div>
      <div class="modal" id="modelModal" hidden>
        <div class="sheet" role="dialog" aria-modal="true" aria-label="Voice backends">
          <div class="sheet-head">
            <div style="flex:1; min-width:0">
              <div class="sheet-title">Voice Backends</div>
              <div class="sheet-sub" id="modelModalSub">Preload models for hands-free voice mode.</div>
            </div>
            <button class="icon-btn" id="modelModalCloseBtn" title="Close" aria-label="Close"><span class="md3-icon" aria-hidden="true">close</span></button>
          </div>
          <div class="sheet-body">
            <div class="sheet-warn" id="modelWarn" hidden></div>
            <label class="check-row">
              <input class="check" type="checkbox" id="modelCheckStt" />
              <div class="check-main">
                <div class="check-title">STT (Speech to Text)</div>
                <div class="check-note" id="modelNoteStt">Configured: <b>…</b></div>
              </div>
            </label>
            <label class="check-row">
              <input class="check" type="checkbox" id="modelCheckLlm" />
              <div class="check-main">
                <div class="check-title">LLM (Text Model)</div>
                <div class="check-note" id="modelNoteLlm">Configured: <b>…</b></div>
              </div>
            </label>
            <label class="check-row">
              <input class="check" type="checkbox" id="modelCheckTts" />
              <div class="check-main">
                <div class="check-title">TTS (Speech Output)</div>
                <div class="check-note" id="modelNoteTts">Configured: <b>…</b></div>
              </div>
            </label>
          </div>
          <div class="sheet-actions">
            <button class="sheet-btn" id="modelsRefreshBtn">Refresh</button>
            <button class="sheet-btn primary" id="modelsStartBtn">Start Selected</button>
            <button class="sheet-btn danger" id="modelsStopBtn">Stop Loaded</button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
__POPUP_JS__
  </script>
</body>
</html>
"""

def render_popup_html(theme_css: str = "") -> str:
    theme_block = (theme_css or "").strip()
    if theme_block:
        theme_block = "\n" + theme_block + "\n"
    return (
        _TEMPLATE.replace("__POPUP_CSS__", POPUP_CSS)
        .replace("__POPUP_THEME_CSS__", theme_block)
        .replace("__POPUP_JS__", POPUP_JS)
    )


WEB_POPUP_HTML = render_popup_html()
