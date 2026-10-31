# -*- coding: utf-8 -*-
"""Material Design 3 layout layer, ported from Hanauta Nest (PyQt6 reference).

The Nest reference builds the screen as a vertical stack of separate rounded
cards with a 10px gutter, rather than one full-bleed surface:

    header card   -> brand tile (48dp, primary container) + title + icon buttons
    model card    -> 48dp tile, model name, status pill
    chat card     -> message list with 20dp bubbles
    composer card -> input row (attach + editor + send) and 48dp action buttons

Values taken from ``hanauta_nest.py``: radius 30/24/20/17, 48dp icon buttons,
17px title, 13px body, 11px muted, 10px gaps. Colours stay on the app's injected
MD3 palette so the wallpaper theme still drives them.

Selectors are unchanged from the previous layout layer so every bridge slot and
JS-rendered element keeps working.
"""

POPUP_LAYOUT_CSS = r"""
    :root {
      --font: 'Rubik', 'Noto Sans', 'Cantarell', system-ui, -apple-system, sans-serif;
      --shell-pad: 10px;
      --gap: 10px;
      /* MD3 shape scale used by the Nest reference. */
      --round-xs: 8px;
      --round-sm: 12px;
      --round-md: 16px;
      --round: 20px;
      --round-lg: 24px;
      --round-xl: 30px;
      --round-full: 999px;
      /* Surface containers: surface / raised / hover, as in the reference. */
      --layer1: rgba(255, 255, 255, 0.055);
      --layer2: rgba(255, 255, 255, 0.09);
      --layer3: rgba(255, 255, 255, 0.13);
      --outline: rgba(255, 255, 255, 0.10);
      --outline-strong: rgba(255, 255, 255, 0.18);
      --float-shadow: 0 10px 30px rgba(0, 0, 0, 0.38);
      --ease: cubic-bezier(0.2, 0, 0, 1);
    }

    /* ---- Shell: 10px gutter, one card per section ---------------------- */
    html, body { border-radius: var(--round-xl); }
    body {
      display: block;
      padding: var(--shell-pad);
      background: var(--bg);
    }
    .window {
      display: flex;
      flex-direction: column;
      gap: var(--gap);
      height: 100%;
      padding: 0;
      border: 0;
      border-radius: var(--round-xl);
      background: transparent;
      box-shadow: none;
      overflow: hidden;
    }

    /* ---- Header card --------------------------------------------------- */
    .topbar {
      flex: 0 0 auto;
      min-height: 68px;
      padding: 10px 12px;
      gap: 10px;
      border: 1px solid var(--outline);
      border-radius: var(--round-lg);
      background: var(--layer1);
      box-shadow: none;
    }
    .topbar::after { display: none; }

    .brand { gap: 12px; }
    .brand .logo {
      width: 48px;
      height: 48px;
      border-radius: var(--round-lg);
      font-size: 19px;
      color: #1f1730;
      background: var(--accent);
      border: 0;
      box-shadow: none;
    }
    .brand .title {
      font-size: 17px;
      font-weight: 600;
      letter-spacing: 0.15px;
    }
    .brand .status {
      margin-top: 2px;
      max-width: 260px;
      font-size: 11px;
      font-weight: 400;
      letter-spacing: 0.4px;
      color: var(--text-mid);
    }
    .info-dot {
      width: 22px;
      height: 22px;
      font-size: 12px;
      color: var(--text-mid);
      background: var(--layer2);
      border: 0;
    }
    .info-tip {
      top: 26px;
      border-radius: var(--round-md);
      border: 1px solid var(--outline);
      background: var(--panel-2);
      backdrop-filter: blur(16px);
      box-shadow: var(--float-shadow);
    }

    .actions { gap: 6px; }
    .icon-btn {
      width: 48px;
      height: 48px;
      border-radius: 17px;
      background: var(--layer2);
      color: var(--text);
    }
    .icon-btn:hover { transform: none; background: var(--layer3); }
    .icon-btn:active { background: var(--layer3); }
    .icon-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }

    /* ---- Page stack ---------------------------------------------------- */
    .body {
      flex: 1 1 auto;
      min-height: 0;
      border: 0;
      border-radius: 0;
      /* The theme tints .body directly; each section is its own card here. */
      background: transparent !important;
      overflow: visible;
    }
    .chat-page {
      position: relative;
      display: flex;
      flex-direction: column;
      gap: var(--gap);
      height: 100%;
      min-height: 0;
    }

    /* ---- Model card ---------------------------------------------------- */
    .backend-row {
      position: static;
      transform: none;
      flex: 0 0 auto;
      width: auto;
      max-width: none;
      height: auto;
      min-height: 64px;
      padding: 10px 12px;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
      border: 1px solid var(--outline);
      border-radius: var(--round-lg);
      background: var(--layer1);
      box-shadow: none;
      overflow: visible;
      scrollbar-width: auto;
    }
    .backend-row::-webkit-scrollbar { height: 6px; }
    .backend-row:empty { display: none; }
    .backend-pill {
      flex: 0 0 auto;
      height: 36px;
      padding: 0 14px;
      gap: 8px;
      border: 0;
      border-radius: var(--round-xs);
      background: var(--layer2);
      color: var(--text);
      font-size: 12px;
      font-weight: 500;
      letter-spacing: 0.2px;
    }
    .backend-pill:hover { transform: none; background: var(--layer3); }
    .backend-pill.active { background: var(--accent-soft); color: var(--text); }
    .backend-pill img { width: 18px; height: 18px; border-radius: 6px; }
    .backend-fallback-icon { font-size: 13px; }

    /* ---- Chat card ----------------------------------------------------- */
    .conversation {
      flex: 1 1 auto;
      min-height: 0;
      padding: 14px;
      border: 1px solid var(--outline);
      border-radius: var(--round-lg);
      background: var(--layer1);
      overflow-y: auto;
      overflow-x: hidden;
    }
    .conversation:empty::before,
    .conversation.empty::before { padding: 20px 12px; }

    .message {
      max-width: 100%;
      margin: 8px 0;
      gap: 10px;
      align-items: flex-start;
    }
    .avatar {
      width: 32px;
      height: 32px;
      border-radius: var(--round-md);
      border: 0;
      background: var(--layer2);
      color: var(--text-mid);
      font-size: 11px;
      font-weight: 600;
    }
    .message.you .avatar { background: var(--accent-soft); color: var(--accent); }

    .bubble {
      max-width: 86%;
      padding: 12px 14px;
      border: 0;
      border-radius: var(--round);
      background: var(--layer2);
      box-shadow: none;
    }
    /* Assistant text sits directly on the chat card, as in the reference. */
    .bubble.ai {
      max-width: 100%;
      padding: 2px 0 0;
      border: 0;
      border-radius: 0;
      background: transparent;
    }
    .bubble.you {
      border: 0;
      border-radius: var(--round);
      background: var(--accent-soft);
    }
    .bubble.system {
      border: 0;
      border-radius: var(--round);
      background: rgba(255, 212, 96, 0.12);
    }
    .meta {
      margin-bottom: 5px;
      font-size: 11px;
      font-weight: 500;
      letter-spacing: 0.4px;
      color: var(--text-dim);
    }
    .meta .name { font-weight: 600; color: var(--text-mid); }
    .meta .time { font-weight: 400; }
    .body-text {
      font-size: 13px;
      line-height: 1.5;
      letter-spacing: 0.15px;
    }
    .body-text code {
      border-radius: var(--round-xs);
      border: 0;
      background: var(--layer3);
    }
    .body-text pre {
      border-radius: var(--round-sm);
      border: 0;
      background: var(--layer3);
    }
    .body-text img { border-radius: var(--round-md); border: 0; }
    .chips-wrap { gap: 6px; margin-top: 10px; }
    .chip-pill {
      padding: 3px 9px;
      border: 0;
      border-radius: var(--round-xs);
      background: var(--layer3);
      font-size: 10.5px;
      font-weight: 500;
    }
    .msg-remove {
      border: 0;
      border-radius: var(--round-full);
      background: var(--layer3);
      font-weight: 500;
    }
    .audio-card {
      border: 0;
      border-radius: var(--round-md);
      background: var(--layer2);
    }
    .audio-play { border: 0; }

    .empty-state {
      max-width: 100%;
      margin: 4px 0 0;
      padding: 18px;
      border: 0;
      border-radius: var(--round);
      background: var(--layer2);
      box-shadow: none;
    }
    .empty-title { font-size: 15px; font-weight: 600; margin-bottom: 6px; }
    .empty-copy { font-size: 12px; font-weight: 400; line-height: 1.55; color: var(--text-mid); }
    .kbd {
      padding: 1px 7px;
      border: 0;
      border-radius: var(--round-xs);
      background: var(--layer3);
      font-size: 11px;
      font-weight: 500;
    }
    .pill {
      padding: 4px 10px;
      border: 0;
      border-radius: var(--round-xs);
      background: var(--layer3);
      color: var(--text-mid);
      font-size: 11px;
      font-weight: 500;
    }

    /* ---- Composer card -------------------------------------------------- */
    .composer {
      flex: 0 0 auto;
      margin: 0;
      padding: 10px;
      border: 1px solid var(--outline);
      border-radius: var(--round-lg);
      background: var(--layer1);
    }
    .input-row {
      display: flex;
      align-items: flex-end;
      gap: 6px;
    }
    .composer textarea {
      flex: 1 1 auto;
      min-height: 44px;
      max-height: 140px;
      padding: 12px 10px;
      border: 0;
      border-radius: var(--round-md);
      background: var(--layer2);
      font-size: 13px;
      font-weight: 400;
      letter-spacing: 0.15px;
      line-height: 1.5;
    }
    .composer textarea::placeholder { color: var(--text-dim); }
    .composer-row {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-top: 8px;
      padding: 0;
    }
    .provider {
      flex: 0 1 auto;
      margin-right: auto;
      padding: 5px 10px;
      border-radius: var(--round-xs);
      background: var(--layer3);
      font-size: 11px;
      font-weight: 500;
      letter-spacing: 0.4px;
      color: var(--text-mid);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 55%;
    }
    /* Reference: 48dp action buttons, 17dp corners, primary send. */
    .send-btn {
      width: 48px;
      height: 48px;
      min-width: 48px;
      padding: 0;
      border: 0;
      border-radius: 17px;
      background: var(--accent);
      color: #1f1730;
      box-shadow: none;
    }
    .send-btn.secondary {
      width: 48px;
      height: 48px;
      min-width: 48px;
      border-radius: 17px;
      background: var(--layer2);
      color: var(--text);
    }
    .send-btn:hover { transform: none; filter: brightness(1.05); }
    .send-btn.secondary:hover { transform: none; background: var(--layer3); filter: none; }
    .send-btn:active { transform: scale(0.96); }
    .send-btn:disabled { opacity: 0.45; filter: none; }
    .send-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
    .attachment-chip {
      min-height: 30px;
      padding: 0 10px;
      border: 0;
      border-radius: var(--round-xs);
      background: var(--layer3);
      font-weight: 500;
    }

    .slash-menu {
      left: 0;
      right: 0;
      bottom: 96px;
      border: 1px solid var(--outline);
      border-radius: var(--round-lg);
      background: var(--panel-2);
      backdrop-filter: blur(16px);
      box-shadow: var(--float-shadow);
    }
    .slash-row { padding: 10px 14px; }
    .slash-cmd { font-size: 12.5px; font-weight: 600; }
    .slash-desc { font-size: 12px; font-weight: 400; color: var(--text-mid); }

    /* ---- Voice page ----------------------------------------------------- */
    .voice-page { padding: 0; }
    .voice-shell {
      padding: 14px;
      border: 1px solid var(--outline);
      border-radius: var(--round-lg);
      background: var(--layer1);
    }
    .voice-status { font-size: 24px; font-weight: 600; letter-spacing: -0.2px; }
    .voice-name { font-size: 15px; font-weight: 600; }
    .voice-sub { font-size: 12px; font-weight: 400; color: var(--text-dim); }
    .voice-pill {
      padding: 6px 12px;
      border: 0;
      border-radius: var(--round-xs);
      background: var(--layer3);
      font-size: 11px;
      font-weight: 500;
      letter-spacing: 0.4px;
      color: var(--text-mid);
    }
    .caption-stack { gap: 8px; }
    .caption-card {
      padding: 12px;
      border: 1px solid var(--outline);
      border-radius: var(--round);
      background: var(--layer2);
      box-shadow: none;
    }
    .caption-card::after { display: none; }
    .caption-badge {
      width: 32px;
      height: 32px;
      border-radius: var(--round-md);
      border: 0;
      background: var(--layer3);
      font-size: 11px;
      font-weight: 600;
    }
    .caption-name { font-size: 13px; font-weight: 600; }
    .caption-meta { font-size: 11px; font-weight: 400; color: var(--text-dim); }
    .caption-text { font-size: 13px; font-weight: 400; line-height: 1.5; }
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
      min-height: 48px;
      padding: 0 18px;
      border: 0;
      border-radius: 17px;
      background: var(--layer2);
      color: var(--text);
      font-size: 13px;
      font-weight: 500;
      letter-spacing: 0.1px;
      box-shadow: none;
    }
    .voice-stop-btn-top {
      background: rgba(255, 90, 126, 0.16);
      color: #ffd3de;
    }
    .voice-stop-btn-top::before { display: none; }
    .voice-nav-btn:hover,
    .voice-stop-btn-top:hover,
    .voice-stop:hover,
    .sheet-btn:hover {
      transform: none;
      background: var(--layer3);
    }
    .voice-stop-btn-top:hover { background: rgba(255, 90, 126, 0.24); }

    /* ---- Dialog sheet ---------------------------------------------------- */
    .modal { background: rgba(0, 0, 0, 0.38); backdrop-filter: blur(3px); }
    .sheet {
      width: min(560px, 100%);
      border: 0;
      border-radius: var(--round-xl);
      background: var(--panel);
      box-shadow: var(--float-shadow);
    }
    .sheet-head { padding: 16px 16px 10px; border-bottom: 1px solid var(--outline); }
    .sheet-title { font-size: 16px; font-weight: 600; }
    .sheet-sub { margin-top: 3px; font-size: 12px; font-weight: 400; color: var(--text-mid); }
    .sheet-sub-note { font-size: 11px; font-weight: 400; color: var(--text-dim); }
    .sheet-body { padding: 10px 16px; gap: 8px; }
    .check-row {
      padding: 12px;
      border: 0;
      border-radius: var(--round-md);
      background: var(--layer2);
    }
    .check-row:hover { background: var(--layer3); }
    .check-title { font-size: 13px; font-weight: 600; }
    .check-note { font-size: 12px; font-weight: 400; color: var(--text-mid); }
    .sheet-actions { padding: 12px 16px 16px; border-top: 0; gap: 8px; }
    .sheet-btn { min-height: 40px; padding: 0 18px; }
    .sheet-btn.primary { background: var(--accent); color: #1f1730; font-weight: 600; }
    .sheet-btn.danger { background: rgba(255, 90, 126, 0.16); color: #ffd3de; }

    /* ---- Scrollbars: 5px, transparent track ----------------------------- */
    .conversation::-webkit-scrollbar,
    .voice-page::-webkit-scrollbar { width: 5px; height: 5px; }
    .conversation::-webkit-scrollbar-thumb,
    .voice-page::-webkit-scrollbar-thumb {
      background: var(--outline-strong);
      border: 0;
      border-radius: var(--round-full);
    }
    .conversation::-webkit-scrollbar-thumb:hover,
    .voice-page::-webkit-scrollbar-thumb:hover { background: var(--accent); }
    .conversation::-webkit-scrollbar-track,
    .voice-page::-webkit-scrollbar-track { background: transparent; }

    /* ---- Small windows ---------------------------------------------------- */
    @media (max-width: 540px) {
      body { padding: 6px; }
      .window { gap: 6px; }
      .topbar { min-height: 60px; padding: 8px 10px; }
      .brand .status { max-width: 150px; }
      .brand .logo { width: 44px; height: 44px; }
      .icon-btn { width: 44px; height: 44px; }
      .conversation { padding: 10px; }
      .bubble { max-width: 92%; }
      .send-btn, .send-btn.secondary { width: 44px; height: 44px; min-width: 44px; }
      .orb-scene { width: 240px; height: 240px; }
    }
"""
