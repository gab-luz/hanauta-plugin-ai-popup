# -*- coding: utf-8 -*-
"""end-4 "illogical-impulse" layout layer for the popup.

Ported from end-4/dots-hyprland (Quickshell, modules/ii/sidebarLeft):

* ``SidebarLeftContent.qml`` — 10px padding, toolbar row above one rounded
  ``colLayer1`` card that holds the page, ``Appearance.rounding.normal``.
* ``AiChat.qml`` — messages sit in a rounded, clipped area with a floating
  status pill (``colLayer2``, min 38px, centred, radius normal - padding);
  AI replies are plain text, user messages are toned; the input is one
  ``colLayer2`` card (min 45px) with the textarea and a 40x40 send button on
  the first row and a controls strip (model/tool indicators, commands) below.

Runtime values come from the same MD3 palette the app already injects, so the
wallpaper theme still drives every colour.
"""

POPUP_LAYOUT_CSS = r"""
    :root {
      --font: 'Rubik', 'Noto Sans', 'Cantarell', system-ui, -apple-system, sans-serif;
      --shell-pad: 10px;
      --round-sm: 8px;
      --round: 14px;
      --round-lg: 18px;
      --round-full: 999px;
      --layer1: rgba(255, 255, 255, 0.045);
      --layer2: rgba(255, 255, 255, 0.075);
      --layer3: rgba(255, 255, 255, 0.10);
      --outline: rgba(214, 195, 255, 0.12);
      --outline-strong: rgba(214, 195, 255, 0.22);
      --float-shadow: 0 12px 32px rgba(0, 0, 0, 0.42);
      --ease: cubic-bezier(0.2, 0, 0, 1);
    }

    /* ---- Shell: padded layer0 with a toolbar above the content card ----- */
    html, body { border-radius: var(--round-lg); }
    body {
      display: flex;
      flex-direction: column;
      padding: var(--shell-pad);
      background: var(--bg);
    }
    .window {
      flex: 1 1 auto;
      height: auto;
      min-height: 0;
      display: flex;
      flex-direction: column;
      gap: var(--shell-pad);
      padding: 0;
      border: 0;
      border-radius: var(--round-lg);
      background: transparent;
      box-shadow: none;
      overflow: visible;
    }

    .topbar {
      min-height: 42px;
      padding: 0 4px;
      gap: 8px;
      border: 0;
      background: transparent;
      box-shadow: none;
    }
    .topbar::after { display: none; }

    .brand { gap: 10px; }
    .brand .logo {
      width: 30px;
      height: 30px;
      border-radius: 10px;
      font-size: 13px;
      color: var(--accent);
      background: var(--layer2);
      border: 1px solid var(--outline);
      box-shadow: none;
    }
    .brand .title {
      font-size: 14px;
      font-weight: 600;
      letter-spacing: 0.1px;
    }
    .brand .status {
      margin-top: 1px;
      max-width: 300px;
      font-size: 11px;
      font-weight: 400;
      color: var(--text-dim);
      letter-spacing: 0.15px;
    }
    .info-dot {
      width: 20px;
      height: 20px;
      font-size: 12px;
      color: var(--text-dim);
      background: transparent;
      border: 1px solid var(--outline);
    }
    .info-tip {
      top: 24px;
      border-radius: var(--round);
      border: 1px solid var(--outline);
      background: var(--panel-2);
      backdrop-filter: blur(16px);
      box-shadow: var(--float-shadow);
    }

    .actions { gap: 2px; }
    .icon-btn {
      width: 36px;
      height: 36px;
      border-radius: var(--round-full);
      background: transparent;
      color: var(--text-mid);
    }
    .icon-btn:hover { transform: none; background: var(--layer2); color: var(--text); }
    .icon-btn:active { background: var(--layer3); }
    .icon-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }

    /* ---- The rounded page card (colLayer1) ----------------------------- */
    .body {
      flex: 1 1 auto;
      min-height: 0;
      border-radius: var(--round-lg);
      border: 1px solid var(--outline);
      background: var(--layer1);
      overflow: hidden;
    }
    .chat-page { position: relative; }

    /* ---- Floating status pill over the conversation --------------------- */
    .backend-row {
      position: absolute;
      top: 8px;
      left: 50%;
      transform: translateX(-50%);
      z-index: 4;
      width: max-content;
      max-width: calc(100% - 20px);
      height: 38px;
      align-items: center;
      gap: 4px;
      padding: 0 6px;
      border: 1px solid var(--outline);
      border-radius: 12px;
      background: var(--layer2);
      backdrop-filter: blur(14px);
      box-shadow: var(--float-shadow);
      overflow-x: auto;
      overflow-y: hidden;
      scrollbar-width: none;
      flex-wrap: nowrap;
    }
    .backend-row::-webkit-scrollbar { height: 0; }
    .backend-row:empty { display: none; }
    .backend-pill {
      flex: 0 0 auto;
      height: 26px;
      padding: 0 9px;
      gap: 5px;
      border: 0;
      border-radius: var(--round-sm);
      background: transparent;
      color: var(--text-mid);
      font-size: 11px;
      font-weight: 500;
      letter-spacing: 0.1px;
    }
    .backend-pill:hover { transform: none; background: var(--layer3); color: var(--text); }
    .backend-pill.active { background: var(--accent-soft); color: var(--text); }
    .backend-pill img { width: 14px; height: 14px; border-radius: 4px; }
    .backend-fallback-icon { font-size: 11px; }

    /* ---- Messages ------------------------------------------------------- */
    .conversation { padding: 56px 14px 8px; }
    .conversation:empty::before,
    .conversation.empty::before { padding: 24px 18px; }
    .message { max-width: 100%; margin: 6px 0; gap: 8px; align-items: flex-start; }
    .avatar {
      width: 26px;
      height: 26px;
      border-radius: var(--round-sm);
      border: 1px solid var(--outline);
      background: var(--layer2);
      color: var(--text-dim);
      font-size: 10px;
      font-weight: 600;
    }
    .message.you .avatar { background: var(--accent-soft); border-color: transparent; color: var(--accent); }

    .bubble {
      max-width: 88%;
      padding: 9px 12px 10px;
      border: 1px solid var(--outline);
      border-radius: var(--round);
      background: var(--layer2);
      box-shadow: none;
    }
    /* AI replies are plain text on the card, like AiChat.qml's delegate. */
    .bubble.ai {
      max-width: 100%;
      padding: 3px 0 0;
      border: 0;
      border-radius: 0;
      background: transparent;
    }
    .bubble.you {
      border-color: transparent;
      border-bottom-right-radius: 4px;
      background: var(--accent-soft);
    }
    .bubble.system {
      border-color: rgba(255, 212, 96, 0.20);
      border-bottom-left-radius: 4px;
      background: rgba(255, 212, 96, 0.10);
    }
    .meta {
      margin-bottom: 4px;
      font-size: 10.5px;
      font-weight: 500;
      letter-spacing: 0.2px;
      color: var(--text-dim);
    }
    .meta .name { font-weight: 600; color: var(--text-mid); }
    .meta .time { font-weight: 400; }
    .body-text { font-size: 13px; line-height: 1.55; }
    .body-text code {
      border-radius: 6px;
      border-color: var(--outline);
      background: var(--layer3);
    }
    .body-text pre {
      border-radius: var(--round-sm);
      border-color: var(--outline);
      background: var(--layer3);
    }
    .body-text img { border-radius: var(--round-sm); border-color: var(--outline); }
    .chips-wrap { gap: 4px; margin-top: 8px; }
    .chip-pill {
      padding: 2px 8px;
      border: 1px solid var(--outline);
      border-radius: var(--round-sm);
      background: var(--layer2);
      font-size: 10px;
      font-weight: 500;
    }
    .msg-remove {
      border-radius: var(--round-full);
      border-color: var(--outline-strong);
      background: var(--layer2);
      font-weight: 500;
    }
    .audio-card {
      border-radius: var(--round);
      border-color: var(--outline);
      background: var(--layer2);
    }
    .audio-play { border: 0; }

    .empty-state {
      max-width: 100%;
      margin: 6px 0 0;
      padding: 18px;
      border: 1px solid var(--outline);
      border-radius: var(--round);
      background: var(--layer2);
      box-shadow: none;
    }
    .empty-title { font-size: 14px; font-weight: 600; margin-bottom: 6px; }
    .empty-copy { font-size: 12px; font-weight: 400; line-height: 1.55; color: var(--text-mid); }
    .kbd {
      padding: 1px 6px;
      border-radius: 5px;
      border-color: var(--outline-strong);
      background: var(--layer3);
      font-size: 10.5px;
      font-weight: 500;
    }
    .pill {
      padding: 3px 9px;
      border-color: var(--outline-strong);
      background: var(--layer2);
      color: var(--text-mid);
      font-size: 10.5px;
      font-weight: 500;
    }

    /* ---- Input card: textarea + send, then the controls strip ---------- */
    .composer {
      margin: 8px;
      padding: 8px 8px 6px;
      border: 1px solid var(--outline);
      border-radius: var(--round);
      background: var(--layer2);
    }
    .input-row {
      display: flex;
      align-items: flex-end;
      gap: 6px;
    }
    .composer textarea {
      flex: 1 1 auto;
      min-height: 34px;
      max-height: 140px;
      padding: 8px 6px 6px;
      border: 0;
      border-radius: 0;
      background: transparent;
      font-size: 13px;
      font-weight: 400;
      line-height: 1.5;
    }
    .composer textarea::placeholder { color: var(--text-dim); }
    .composer-row {
      display: flex;
      align-items: center;
      gap: 2px;
      margin-top: 2px;
      padding: 0 2px;
    }
    .provider {
      flex: 0 1 auto;
      margin-right: auto;
      padding: 3px 8px;
      border-radius: 6px;
      background: var(--layer3);
      font-size: 10.5px;
      font-weight: 500;
      color: var(--text-mid);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 55%;
    }
    .send-btn {
      width: 40px;
      height: 40px;
      min-width: 40px;
      padding: 0;
      border-radius: var(--round-sm);
      background: var(--accent);
      color: #17121f;
      box-shadow: none;
    }
    .send-btn.secondary {
      width: 34px;
      height: 34px;
      min-width: 34px;
      border-radius: var(--round-sm);
      background: transparent;
      color: var(--text-mid);
    }
    .send-btn:hover { transform: none; filter: brightness(1.05); }
    .send-btn.secondary:hover { transform: none; background: var(--layer3); color: var(--text); filter: none; }
    .send-btn:active { transform: scale(0.96); }
    .send-btn:disabled { opacity: 0.45; filter: none; }
    .send-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
    .attachment-chip {
      min-height: 26px;
      border-radius: var(--round-sm);
      border-color: var(--outline);
      background: var(--layer3);
      font-weight: 500;
    }

    .slash-menu {
      left: 8px;
      right: 8px;
      bottom: 84px;
      border-radius: var(--round);
      border-color: var(--outline);
      background: var(--panel-2);
      backdrop-filter: blur(16px);
      box-shadow: var(--float-shadow);
    }
    .slash-row { padding: 9px 12px; }
    .slash-cmd { font-size: 12px; font-weight: 600; }
    .slash-desc { font-size: 11.5px; font-weight: 400; color: var(--text-mid); }

    /* ---- Voice page ---------------------------------------------------- */
    .voice-page { padding: 8px; }
    .voice-shell {
      padding: 14px;
      border: 1px solid var(--outline);
      border-radius: var(--round);
      background: transparent;
    }
    .voice-status { font-size: 24px; font-weight: 600; letter-spacing: -0.2px; }
    .voice-name { font-size: 14px; font-weight: 600; }
    .voice-sub { font-size: 12px; font-weight: 400; color: var(--text-dim); }
    .voice-pill {
      padding: 5px 10px;
      border: 1px solid var(--outline);
      border-radius: var(--round-sm);
      background: var(--layer2);
      font-size: 10.5px;
      font-weight: 500;
      letter-spacing: 0.2px;
      color: var(--text-mid);
    }
    .caption-stack { gap: 6px; }
    .caption-card {
      padding: 12px;
      border: 1px solid var(--outline);
      border-radius: var(--round);
      background: var(--layer2);
      box-shadow: none;
    }
    .caption-card::after { display: none; }
    .caption-badge {
      width: 26px;
      height: 26px;
      border-radius: var(--round-sm);
      border: 1px solid var(--outline);
      background: var(--layer3);
      font-size: 10px;
      font-weight: 600;
    }
    .caption-name { font-size: 12.5px; font-weight: 600; }
    .caption-meta { font-size: 11px; font-weight: 400; color: var(--text-dim); }
    .caption-text { font-size: 13px; font-weight: 400; line-height: 1.45; }
    .voice-card {
      padding: 12px;
      border: 1px solid var(--outline);
      border-radius: var(--round);
      background: var(--layer2);
    }
    .voice-nav-btn,
    .voice-stop-btn-top,
    .voice-stop,
    .sheet-btn {
      min-height: 36px;
      padding: 0 14px;
      border: 1px solid var(--outline);
      border-radius: var(--round-sm);
      background: var(--layer2);
      color: var(--text);
      font-size: 12px;
      font-weight: 500;
      letter-spacing: 0.1px;
      box-shadow: none;
    }
    .voice-stop-btn-top {
      border-color: rgba(255, 116, 152, 0.28);
      background: rgba(255, 90, 126, 0.14);
      color: #ffd3de;
    }
    .voice-stop-btn-top::before { display: none; }
    .voice-nav-btn:hover,
    .voice-stop-btn-top:hover,
    .voice-stop:hover,
    .sheet-btn:hover {
      transform: none;
      background: var(--layer3);
      border-color: var(--outline-strong);
    }
    .voice-stop-btn-top:hover { background: rgba(255, 90, 126, 0.22); }

    /* ---- Dialog sheet -------------------------------------------------- */
    .modal { background: rgba(0, 0, 0, 0.38); backdrop-filter: blur(3px); }
    .sheet {
      width: min(560px, 100%);
      border: 1px solid var(--outline);
      border-radius: var(--round-lg);
      background: var(--panel);
      box-shadow: var(--float-shadow);
    }
    .sheet-head { padding: 14px 16px 10px; border-bottom: 1px solid var(--outline); }
    .sheet-title { font-size: 14px; font-weight: 600; }
    .sheet-sub { margin-top: 3px; font-size: 11.5px; font-weight: 400; color: var(--text-mid); }
    .sheet-sub-note { font-size: 11px; font-weight: 400; color: var(--text-dim); }
    .sheet-body { padding: 10px 16px; gap: 6px; }
    .check-row {
      padding: 11px;
      border-color: var(--outline);
      border-radius: var(--round-sm);
      background: transparent;
    }
    .check-row:hover { background: var(--layer2); }
    .check-title { font-size: 12px; font-weight: 600; }
    .check-note { font-size: 11.5px; font-weight: 400; color: var(--text-mid); }
    .sheet-actions { padding: 10px 16px 14px; border-top: 0; gap: 6px; }
    .sheet-btn.primary { background: var(--accent); border-color: transparent; color: #17121f; font-weight: 600; }
    .sheet-btn.danger { background: rgba(255, 90, 126, 0.14); border-color: transparent; color: #ffd3de; }

    /* ---- Scrollbars ----------------------------------------------------- */
    .conversation::-webkit-scrollbar,
    .voice-page::-webkit-scrollbar { width: 6px; height: 6px; }
    .conversation::-webkit-scrollbar-thumb,
    .voice-page::-webkit-scrollbar-thumb {
      background: var(--outline-strong);
      border: 1px solid transparent;
      background-clip: padding-box;
      border-radius: var(--round-full);
    }
    .conversation::-webkit-scrollbar-thumb:hover,
    .voice-page::-webkit-scrollbar-thumb:hover { background: var(--accent); background-clip: padding-box; }
    .conversation::-webkit-scrollbar-track,
    .voice-page::-webkit-scrollbar-track { background: transparent; }

    /* ---- Small windows --------------------------------------------------- */
    @media (max-width: 540px) {
      body { padding: 0; }
      .window { gap: 6px; }
      .body { border-radius: 0; border: 0; }
      .topbar { padding: 0 6px; }
      .brand .status { max-width: 170px; }
      .conversation { padding: 52px 10px 6px; }
      .composer { margin: 6px; }
      .bubble { max-width: 92%; }
      .orb-scene { width: 240px; height: 240px; }
    }
"""
