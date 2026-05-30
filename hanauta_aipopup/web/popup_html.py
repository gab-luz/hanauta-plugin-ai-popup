# -*- coding: utf-8 -*-

from __future__ import annotations

import html

from .popup_css import POPUP_CSS
from .popup_js import POPUP_JS
from ..i18n import tr

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
        <div class="logo" aria-hidden="true">◉</div>
        <div class="title-wrap">
          <div style="display:flex; align-items:center; gap:8px;">
            <div class="title">Hanauta AI</div>
            <div class="info-pop" title="Info">
              <div class="info-dot" aria-label="Information"><img class="icon-svg" id="infoIcon" alt="" /></div>
              <div class="info-tip" id="infoTip"><div class="tip-title">Loaded Backends</div><div class="tip-line">Loading...</div></div>
            </div>
          </div>
          <div class="status" id="headerStatus"></div>
        </div>
      </div>
      <div class="actions">
        <button class="icon-btn" id="modelsBtn" title="Start/Stop backends" aria-label="Start/Stop backends"><img class="icon-svg" id="modelsIcon" alt="" /></button>
        <button class="icon-btn" id="voiceBtn" title="__I18N_VOICE_MODE__" aria-label="__I18N_VOICE_MODE__"><img class="icon-svg" id="voiceIcon" alt="" /></button>
        <button class="icon-btn" id="settingsBtn" title="__I18N_SETTINGS__" aria-label="__I18N_SETTINGS__"><img class="icon-svg" id="settingsIcon" alt="" /></button>
        <button class="icon-btn" id="charactersBtn" title="__I18N_CHARACTERS__" aria-label="__I18N_CHARACTERS__"><img class="icon-svg" id="charactersIcon" alt="" /></button>
        <button class="icon-btn" id="closeBtn" title="__I18N_CLOSE__" aria-label="__I18N_CLOSE__"><img class="icon-svg" id="closeIcon" alt="" /></button>
      </div>
    </div>
    <div class="body">
      <div class="chat-page" id="chatPage">
        <div class="backend-row" id="backendRow"></div>
        <div class="conversation" id="conversation"></div>
        <div class="composer">
          <div class="attachment-tray" id="attachmentTray" hidden></div>
          <textarea id="composerInput" placeholder="__I18N_COMPOSER_PLACEHOLDER__"></textarea>
          <div class="slash-menu" id="slashMenu" hidden></div>
          <div class="composer-row">
            <div class="provider" id="providerLabel"></div>
            <button class="send-btn secondary" id="attachBtn" title="__I18N_ADD_ATTACHMENTS__" aria-label="__I18N_ADD_ATTACHMENTS__"><img class="icon-svg btn-icon" id="attachIcon" alt="" /></button>
            <button class="send-btn secondary" id="sttBtn" title="__I18N_DICTATE__" aria-label="__I18N_DICTATE__"><img class="icon-svg btn-icon" id="sttIcon" alt="" /></button>
            <button class="send-btn secondary" id="archiveBtn" title="__I18N_ARCHIVE_CHAT__" aria-label="__I18N_ARCHIVE_CHAT__"><img class="icon-svg btn-icon" id="archiveIcon" alt="" /></button>
            <button class="send-btn secondary" id="exportBtn" title="__I18N_EXPORT_CHAT__" aria-label="__I18N_EXPORT_CHAT__"><img class="icon-svg btn-icon" id="exportIcon" alt="" /></button>
            <button class="send-btn secondary" id="clearBtn" title="__I18N_CLEAR_CHAT__" aria-label="__I18N_CLEAR_CHAT__"><img class="icon-svg btn-icon" id="clearIcon" alt="" /></button>
            <button class="send-btn" id="sendBtn" title="__I18N_SEND_MESSAGE__" aria-label="__I18N_SEND_MESSAGE__"><img class="icon-svg btn-icon" id="sendIcon" alt="" /></button>
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
            <div class="voice-pill">__I18N_HANDSFREE_VOICE_MODE__</div>
            <div class="voice-name" id="voiceName"></div>
            <div class="voice-status" id="voiceStatus"></div>
            <div class="voice-sub">__I18N_VOICE_SUB__</div>
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
            <div class="value" id="voiceStatusNote">__I18N_VOICE_READY__</div>
          </div>
          <div class="voice-controls">
            <button class="voice-stop" id="voiceStopBtn">__I18N_RETURN_TO_CHAT__</button>
          </div>
        </div>
      </div>
      <div class="modal" id="modelModal" hidden>
        <div class="sheet" role="dialog" aria-modal="true" aria-label="__I18N_VOICE_BACKENDS__">
          <div class="sheet-head">
            <div style="flex:1; min-width:0">
              <div class="sheet-title">__I18N_VOICE_BACKENDS__</div>
              <div class="sheet-sub" id="modelModalSub">__I18N_MODELS_SUB_DEFAULT__</div>
              <div class="sheet-sub-note" id="modelModalSubNote">Only 1 ASR, 1 TTS and 1 LLM can be selected at the same time.</div>
            </div>
            <button class="icon-btn" id="modelModalCloseBtn" title="Close" aria-label="Close"><img class="icon-svg" id="modalCloseIcon" alt="" /></button>
          </div>
          <div class="sheet-body">
            <div class="sheet-warn" id="modelWarn" hidden></div>
            <div id="modelBackendList"></div>
          </div>
          <div class="sheet-actions">
            <button class="sheet-btn" id="modelsRefreshBtn">__I18N_REFRESH__</button>
            <button class="sheet-btn primary" id="modelsStartBtn">__I18N_START_SELECTED__</button>
            <button class="sheet-btn danger" id="modelsStopBtn">__I18N_STOP_LOADED__</button>
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
    def _js_escape(value: str) -> str:
        return (
            str(value)
            .replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
        )
    translations = {
        "__I18N_VOICE_MODE__": tr("chat.voice_mode", "Voice mode"),
        "__I18N_SETTINGS__": tr("chat.settings", "Settings"),
        "__I18N_CHARACTERS__": tr("chat.characters", "Characters"),
        "__I18N_CLOSE__": tr("chat.close", "Close"),
        "__I18N_COMPOSER_PLACEHOLDER__": tr("chat.composer.placeholder", "Message the model... Enter to send"),
        "__I18N_ADD_ATTACHMENTS__": tr("chat.attachments.add", "Add attachments"),
        "__I18N_DICTATE__": tr("chat.dictate", "Dictate (speech to text)"),
        "__I18N_ARCHIVE_CHAT__": tr("chat.archive", "Archive chat"),
        "__I18N_EXPORT_CHAT__": tr("chat.export", "Export chat"),
        "__I18N_CLEAR_CHAT__": tr("chat.clear", "Clear chat"),
        "__I18N_SEND_MESSAGE__": tr("chat.send", "Send message"),
        "__I18N_HANDSFREE_VOICE_MODE__": tr("chat.voice.handsfree", "Hands-free Voice Mode"),
        "__I18N_VOICE_SUB__": tr("chat.voice.sub", "Stay in the conversation. Start talking anytime."),
        "__I18N_VOICE_READY__": tr("chat.voice.ready", "Voice mode is ready."),
        "__I18N_RETURN_TO_CHAT__": tr("chat.voice.return", "Return to chat"),
        "__I18N_VOICE_BACKENDS__": tr("chat.voice.backends", "Backends"),
        "__I18N_MODELS_SUB_DEFAULT__": tr("chat.voice.models_sub_default", "Start and stop your active backends."),
        "__I18N_REFRESH__": tr("chat.refresh", "Refresh"),
        "__I18N_START_SELECTED__": tr("chat.start_selected", "Start Selected"),
        "__I18N_STOP_LOADED__": tr("chat.stop_loaded", "Stop Loaded"),
    }
    js_translations = {
        "__I18N_MODELS_SUB_DEFAULT__": tr("chat.voice.models_sub_default", "Start and stop your active backends."),
        "__I18N_ASSISTANT_NAME__": tr("chat.assistant_name", "Hanauta AI"),
        "__I18N_EMPTY_TITLE__": tr("chat.empty.title", "Start a conversation"),
        "__I18N_EMPTY_COPY__": tr("chat.empty.copy", "Type a message below. Enter sends and Shift+Enter adds a new line."),
        "__I18N_YOU_SHORT__": tr("chat.you.short", "Y"),
        "__I18N_AI_SHORT__": tr("chat.ai.short", "AI"),
        "__I18N_YOU__": tr("chat.you", "You"),
        "__I18N_VOICE__": tr("chat.voice", "Voice"),
        "__I18N_ATTACHMENT__": tr("chat.attachment", "Attachment"),
        "__I18N_REMOVE_ATTACHMENT__": tr("chat.attachment.remove", "Remove attachment"),
        "__I18N_BINARY_ATTACHMENT_NOTE__": tr("chat.attachment.binary_note", "Binary or unsupported file selected."),
        "__I18N_NOT_CONFIGURED__": tr("chat.not_configured", "Not configured"),
        "__I18N_LOADED_BACKENDS__": tr("chat.loaded_backends", "Loaded Backends"),
        "__I18N_NO_INFO__": tr("chat.no_info", "No info yet."),
        "__I18N_START_ANYWAY__": tr("chat.start_anyway", "Start Anyway"),
        "__I18N_START_SELECTED__": tr("chat.start_selected", "Start Selected"),
        "__I18N_CONFIGURED__": tr("chat.configured", "Configured"),
        "__I18N_LOADED__": tr("chat.loaded", "loaded"),
        "__I18N_MODELS_SUB_OPENING_VOICE__": tr("chat.voice.models_sub_opening_voice", "Select which backends to warm up. Voice mode opens automatically when ready."),
        "__I18N_MODELS_SUB_SELECT_TO_STOP__": tr("chat.voice.models_sub_select_to_stop", "Select which started backends you want to stop."),
        "__I18N_REVIEW_ATTACHMENTS__": tr("chat.review_attachments", "Please review the attached content."),
        "__I18N_NOW__": tr("chat.now", "now"),
    }
    popup_js = POPUP_JS
    for key, value in js_translations.items():
        popup_js = popup_js.replace(key, _js_escape(str(value)))
    popup_html = _TEMPLATE
    for key, value in translations.items():
        popup_html = popup_html.replace(key, html.escape(str(value), quote=True))
    return (
        popup_html.replace("__POPUP_CSS__", POPUP_CSS)
        .replace("__POPUP_THEME_CSS__", theme_block)
        .replace("__POPUP_JS__", popup_js)
    )


WEB_POPUP_HTML = render_popup_html()
