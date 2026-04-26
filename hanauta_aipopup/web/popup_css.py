# -*- coding: utf-8 -*-

POPUP_CSS = r"""
    :root {
      color-scheme: dark;
      --bg: #0f0d18;
      --panel: rgba(24, 20, 36, 0.96);
      --panel-2: rgba(33, 28, 48, 0.86);
      --panel-3: rgba(255,255,255,0.04);
      --card: rgba(255,255,255,0.05);
      --card-2: rgba(255,255,255,0.07);
      --text: rgba(255,255,255,0.92);
      --text-mid: rgba(255,255,255,0.68);
      --text-dim: rgba(255,255,255,0.52);
      --accent: rgba(196, 181, 253, 0.95);
      --accent-2: rgba(125, 211, 252, 0.92);
      --accent-soft: rgba(196, 181, 253, 0.16);
      --accent-soft-hover: rgba(196, 181, 253, 0.22);
      --ok: rgba(57, 255, 136, 0.92);
      --warn: rgba(255, 212, 96, 0.92);
      --bad: rgba(255, 92, 130, 0.92);
      --border: rgba(214,195,255,.12);
      --border-2: rgba(214,195,255,.08);
      --shadow: rgba(0,0,0,0.35);
      --shadow-2: rgba(0,0,0,0.55);
      --you-bg: rgba(125,211,252,0.10);
      --you-border: rgba(125,211,252,0.22);
      --radius: 22px;
      --radius-2: 18px;
      --radius-3: 14px;
      --font: system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, 'Noto Sans', sans-serif;
    }

    * { box-sizing: border-box; }
    html, body {
      height: 100%;
      border-radius: 28px;
      overflow: hidden;
    }
    body {
      margin: 0;
      font-family: var(--font);
      background: radial-gradient(circle at 50% 8%, rgba(186,160,255,0.10), transparent 26%),
                  radial-gradient(circle at 18% 30%, rgba(125, 211, 252, 0.08), transparent 24%),
                  linear-gradient(180deg, rgba(16, 12, 26, 0.98), rgba(10, 8, 18, 0.98));
      color: var(--text);
      overflow: hidden;
    }

    /* Material Design 3 icon ligatures (Material Symbols). */
    .md3-icon {
      font-family: "Material Symbols Outlined", "Material Symbols Rounded", "Material Icons", var(--font);
      font-weight: 400;
      font-style: normal;
      font-size: 20px;
      line-height: 1;
      letter-spacing: normal;
      text-transform: none;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      white-space: nowrap;
      word-wrap: normal;
      direction: ltr;
      -webkit-font-feature-settings: "liga";
      -webkit-font-smoothing: antialiased;
      font-variation-settings: "FILL" 0, "wght" 360, "GRAD" 0, "opsz" 20;
      user-select: none;
    }

    .window {
      display: flex;
      flex-direction: column;
      height: 100%;
      padding: 0;
      gap: 0;
      border-radius: 28px;
      overflow: hidden;
      background: var(--bg);
    }

    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 10px 12px;
      flex-wrap: nowrap;
      border-radius: 0;
      border: 0;
      border-bottom: 1px solid rgba(214,195,255,.10);
      background:
        radial-gradient(circle at 20% 20%, rgba(125,211,252,0.08), transparent 28%),
        radial-gradient(circle at 80% 10%, rgba(196,181,253,0.09), transparent 28%),
        linear-gradient(180deg, rgba(22,18,35,0.96) 0%, rgba(12,10,20,0.98) 100%);
      box-shadow: none;
      position: relative;
      overflow: hidden;
    }

    .topbar::after {
      content: "";
      position: absolute;
      inset: -60px;
      background:
        radial-gradient(circle at 40% 20%, rgba(255,255,255,0.08), transparent 44%),
        radial-gradient(circle at 70% 50%, rgba(196,181,253,0.12), transparent 52%);
      filter: blur(10px);
      opacity: 0.65;
      pointer-events: none;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 0;
      flex: 1 1 auto;
      position: relative;
      z-index: 1;
    }
    .brand .logo {
      width: 42px;
      height: 42px;
      border-radius: 12px;
      display: grid;
      place-items: center;
      font-weight: 900;
      color: var(--accent);
      background: rgba(255,255,255,0.04);
      border: 1px solid rgba(214,195,255,.12);
      box-shadow: inset 0 1px 0 rgba(255,255,255,.10);
    }
    .brand .title-wrap { min-width: 0; }
    .brand .title { font-size: 14px; font-weight: 950; line-height: 1.05; letter-spacing: 0; }
    .brand .status {
      display: block;
      margin-top: 4px;
      font-size: 11px;
      font-weight: 750;
      color: var(--text-dim);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 340px;
    }

    .info-pop {
      position: relative;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      margin-left: 8px;
    }
    .info-dot {
      width: 28px;
      height: 28px;
      border-radius: 999px;
      display: grid;
      place-items: center;
      font-weight: 900;
      font-size: 19px;
      color: rgba(255,255,255,0.82);
      background: rgba(255,255,255,0.06);
      border: 1px solid rgba(214,195,255,.14);
      cursor: default;
      user-select: none;
    }
    .info-tip {
      position: absolute;
      top: 26px;
      left: 0;
      min-width: 240px;
      max-width: 340px;
      padding: 10px 12px;
      border-radius: 14px;
      border: 1px solid rgba(214,195,255,.12);
      background: rgba(12, 10, 20, 0.96);
      box-shadow: 0 18px 40px rgba(0,0,0,0.45);
      opacity: 0;
      transform: translateY(-6px);
      pointer-events: none;
      transition: opacity .16s ease, transform .16s ease;
      z-index: 5;
    }
    .info-pop:hover .info-tip { opacity: 1; transform: translateY(0); pointer-events: auto; }
    .tip-title { font-weight: 900; font-size: 12px; color: rgba(255,255,255,0.86); margin-bottom: 6px; }
    .tip-line { font-weight: 650; font-size: 12px; color: rgba(255,255,255,0.62); }

    .actions {
      display: flex;
      align-items: center;
      gap: 8px;
      position: relative;
      z-index: 1;
      flex: 0 0 auto;
    }
    .icon-btn {
      width: 36px;
      height: 36px;
      border-radius: 12px;
      border: 0;
      background: transparent;
      color: rgba(255,255,255,0.90);
      cursor: pointer;
      font-weight: 900;
      appearance: none;
      transition: transform .16s ease, background .16s ease, border-color .16s ease, box-shadow .16s ease;
      box-shadow: none;
    }
    .icon-btn .md3-icon { font-size: 21px; }
    .icon-btn:hover {
      transform: translateY(-1px);
      background: rgba(255,255,255,0.05);
    }
    .icon-btn.magic-ready {
      box-shadow: 0 0 0 1px rgba(57,255,136,.22);
    }
    .icon-btn:focus-visible {
      outline: 1px solid rgba(196,181,253,.45);
      outline-offset: 2px;
    }

    .body {
      flex: 1;
      min-height: 0;
      border-radius: 0;
      border: 0;
      background: transparent;
      overflow: hidden;
    }

    .chat-page {
      display: flex;
      flex-direction: column;
      height: 100%;
      padding: 0;
      gap: 0;
    }

    .backend-row {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      padding: 10px 12px;
      border-bottom: 1px solid rgba(214,195,255,.08);
    }
    .backend-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 10px;
      border-radius: 999px;
      border: 1px solid var(--border-2);
      background: var(--card-2);
      cursor: pointer;
      user-select: none;
      transition: transform .16s ease, background .16s ease, border-color .16s ease;
      font-weight: 850;
      font-size: 12px;
      color: rgba(255,255,255,0.86);
    }
    .backend-pill:hover { transform: translateY(-1px); border-color: rgba(214,195,255,.22); }
    .backend-pill.active { background: var(--accent-soft); border-color: var(--border); color: rgba(255,255,255,0.94); }
    .backend-pill img { width: 16px; height: 16px; border-radius: 4px; }

    .conversation {
      flex: 1;
      min-height: 0;
      overflow-y: auto;
      overflow-x: hidden;
      padding: 14px 12px 12px 12px;
    }

    .conversation:empty::before,
    .conversation.empty::before {
      content: "Start a conversation";
      display: block;
      text-align: center;
      padding: 40px 20px;
      font-size: 14px;
      font-weight: 600;
      color: rgba(255,255,255,0.36);
    }

    .empty-state {
      margin: 14px auto 0 auto;
      max-width: 520px;
      padding: 18px 16px;
      border-radius: 18px;
      border: 1px dashed var(--border);
      background: rgba(255,255,255,0.03);
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.06);
      text-align: left;
    }
    .empty-title {
      font-size: 14px;
      font-weight: 950;
      color: var(--text);
      margin-bottom: 6px;
    }
    .empty-copy {
      font-size: 12px;
      font-weight: 700;
      line-height: 1.55;
      color: var(--text-mid);
    }
    .empty-row { margin-top: 12px; display: flex; gap: 8px; flex-wrap: wrap; }
    .kbd {
      display: inline-block;
      padding: 1px 6px;
      border-radius: 8px;
      border: 1px solid var(--border-2);
      background: rgba(255,255,255,0.04);
      color: var(--text);
      font-weight: 900;
      font-size: 11px;
      letter-spacing: 0;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      padding: 5px 10px;
      border-radius: 999px;
      border: 1px solid var(--border-2);
      background: rgba(255,255,255,0.04);
      color: var(--text-mid);
      font-weight: 850;
      font-size: 11px;
    }

    .message {
      display: flex;
      gap: 10px;
      margin: 10px 2px;
      align-items: flex-end;
      justify-content: flex-start;
      width: 100%;
    }
    .message.you { justify-content: flex-end; }
    .message.you .avatar { order: 2; }
    .message.you .bubble { order: 1; }
    .message.ai { justify-content: flex-start; }
    .avatar {
      width: 28px;
      height: 28px;
      border-radius: 12px;
      display: grid;
      place-items: center;
      font-weight: 900;
      background: var(--card-2);
      border: 1px solid var(--border-2);
      color: rgba(255,255,255,0.86);
      flex: 0 0 auto;
      overflow: hidden;
    }
    .message.you .avatar {
      background: var(--you-bg);
      border-color: var(--you-border);
      color: var(--accent-2);
    }
    .avatar.has-photo {
      color: transparent;
      border: 0;
      background-size: cover;
      background-position: center;
      box-shadow: 0 0 0 1px rgba(214,195,255,.10);
    }
    .bubble {
      max-width: min(78%, 420px);
      border-radius: 18px;
      border: 1px solid var(--border-2);
      background: var(--card);
      padding: 10px 12px 11px 12px;
      box-shadow: 0 10px 22px rgba(0,0,0,0.14);
      overflow: hidden;
    }
    .bubble.ai {
      border-bottom-left-radius: 6px;
    }
    .bubble.you {
      background: var(--you-bg);
      border-color: var(--you-border);
      border-bottom-right-radius: 6px;
    }
    .chips-wrap { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
    .chip-pill {
      display: inline-flex;
      align-items: center;
      padding: 3px 8px;
      border-radius: 999px;
      border: 1px solid rgba(214,195,255,.16);
      background: rgba(255,255,255,0.04);
      font-size: 10px;
      font-weight: 800;
      color: rgba(255,255,255,0.64);
    }
    .meta {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 6px;
      color: rgba(255,255,255,0.60);
      font-weight: 800;
      font-size: 11px;
    }
    .meta .name { color: rgba(255,255,255,0.78); }
    .meta .time { color: rgba(255,255,255,0.48); font-weight: 750; }
    .body-text {
      font-size: 13px;
      line-height: 1.55;
      font-weight: 400;
      color: rgba(255,255,255,0.90);
      word-break: break-word;
    }
    .body-text p {
      margin: 0;
    }
    .body-text p + p, .body-text p + ul, .body-text p + ol,
    .body-text ul + p, .body-text ol + p, .body-text h1 + p,
    .body-text h2 + p, .body-text h3 + p {
      margin-top: 8px;
    }
    .body-text strong, .body-text b {
      font-weight: 700;
      color: rgba(255,255,255,1.0);
    }
    .body-text em, .body-text i {
      font-style: italic;
      color: rgba(255,255,255,0.85);
    }
    .body-text h1, .body-text h2, .body-text h3 {
      font-weight: 700;
      color: rgba(255,255,255,1.0);
      margin: 10px 0 4px 0;
      line-height: 1.3;
    }
    .body-text h1 { font-size: 16px; }
    .body-text h2 { font-size: 14px; }
    .body-text h3 { font-size: 13px; }
    .body-text a { color: var(--accent); text-decoration: none; }
    .body-text a:hover { text-decoration: underline; }
    .body-text code {
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
      font-size: 12px;
      padding: 2px 6px;
      border-radius: 10px;
      background: rgba(255,255,255,0.06);
      border: 1px solid rgba(214,195,255,.10);
    }
    .body-text pre {
      margin: 10px 0 0 0;
      padding: 10px 12px;
      border-radius: 16px;
      background: rgba(255,255,255,0.05);
      border: 1px solid rgba(214,195,255,.10);
      overflow-x: auto;
    }
    .body-text pre code { border: 0; background: transparent; padding: 0; }
    .body-text ul, .body-text ol { margin: 6px 0 0 20px; padding: 0; }
    .body-text li { margin: 3px 0; }
    .body-text img {
      display: block;
      max-width: 100%;
      border-radius: 16px;
      margin-top: 10px;
      border: 1px solid rgba(214,195,255,.10);
    }

    .audio-card {
      margin-top: 10px;
      width: 100%;
      border: 1px solid rgba(214,195,255,.14);
      background: rgba(255,255,255,0.05);
      color: var(--text);
      border-radius: 16px;
      padding: 10px 12px;
      display: flex;
      align-items: center;
      gap: 12px;
      cursor: pointer;
      user-select: none;
    }
    .audio-card:hover {
      background: rgba(255,255,255,0.07);
    }
    .audio-play {
      width: 34px;
      height: 34px;
      border-radius: 999px;
      display: grid;
      place-items: center;
      background: var(--accent);
      border: 1px solid rgba(255,255,255,0.14);
      color: rgba(12, 10, 20, 0.96);
      flex: 0 0 auto;
    }
    .audio-play .md3-icon { font-size: 20px; }
    .audio-card.is-playing .audio-play {
      background: rgba(196,181,253,0.98);
      border-color: rgba(196,181,253,0.42);
    }
    .audio-wave {
      display: flex;
      align-items: center;
      gap: 2px;
      height: 24px;
      flex: 1 1 auto;
    }
    .audio-wave span {
      width: 2px;
      background: rgba(214,195,255,0.32);
      border-radius: 1px;
      transition: height 0.1s ease;
    }
    .audio-wave span.active {
      background: rgba(196,181,253,0.92);
    }
    .audio-meta {
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 2px;
      flex: 0 0 auto;
      min-width: 54px;
    }
    .audio-duration {
      font-size: 11px;
      font-weight: 900;
      color: var(--text);
      opacity: 0.86;
    }
    .audio-label {
      font-size: 10px;
      font-weight: 800;
      color: var(--text-dim);
    }

    .message.pending .bubble { opacity: 0.6; }
    .message.pending .bubble::after {
      content: "";
      display: inline-block;
      width: 8px;
      height: 8px;
      margin-left: 8px;
      border-radius: 50%;
      background: var(--accent);
      animation: pendingDot 1.0s ease-in-out infinite;
    }
    .message.pending .bubble::before {
      content: "Thinking...";
      font-size: 11px;
      color: var(--text-dim);
      font-weight: 700;
    }
    @keyframes pendingDot { 0%,100% { opacity: 0.3; } 50% { opacity: 1.0; } }

    .composer {
      border-radius: 0;
      border: 0;
      background: rgba(255,255,255,.04);
      padding: 10px 12px 12px 12px;
      border-top: 1px solid rgba(214,195,255,.08);
      position: relative;
    }
    .attachment-tray {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 8px;
    }
    .attachment-chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      min-height: 28px;
      max-width: 100%;
      padding: 0 8px;
      border-radius: 999px;
      border: 1px solid rgba(214,195,255,.14);
      background: rgba(255,255,255,.05);
      color: var(--text);
      font-size: 11px;
      font-weight: 800;
    }
    .attachment-chip .attachment-name {
      max-width: 220px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .attachment-remove {
      border: 0;
      background: transparent;
      color: var(--text-dim);
      cursor: pointer;
      font-size: 16px;
      line-height: 1;
      padding: 0;
    }
    .composer textarea {
      width: 100%;
      min-height: 46px;
      max-height: 140px;
      resize: none;
      border: 0;
      background: rgba(255,255,255,.04);
      color: var(--text);
      border-radius: 20px;
      padding: 12px 14px;
      font: inherit;
      font-weight: 500;
      outline: none;
      overflow-x: hidden;
    }
    .composer-row { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
    .provider { flex: 1; font-size: 12px; font-weight: 600; color: var(--text-dim); }
    .send-btn {
      min-width: 36px;
      height: 36px;
      padding: 0 10px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      border: 0;
      border-radius: 12px;
      appearance: none;
      background: rgba(198,180,255,.16);
      color: #fff;
      font-weight: 800;
      font-size: 15px;
      cursor: pointer;
      transition: transform .16s ease, background .16s ease, box-shadow .16s ease;
    }
    .send-btn.secondary { background: transparent; color: rgba(255,255,255,0.86); }
    .send-btn .btn-icon {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      line-height: 1;
      transform: translateY(-0.5px);
    }
    .send-btn:hover { transform: translateY(-1px); background: rgba(198,180,255,.22); }
    .send-btn.secondary:hover { background: rgba(255,255,255,.05); }
    .send-btn:active { transform: translateY(0px); }
    .send-btn:focus-visible {
      outline: 1px solid rgba(196,181,253,.45);
      outline-offset: 2px;
    }

    .slash-menu {
      position: absolute;
      left: 12px;
      right: 12px;
      bottom: 74px;
      border-radius: 16px;
      border: 1px solid rgba(214,195,255,.14);
      background: rgba(10, 8, 18, 0.96);
      box-shadow: 0 18px 50px rgba(0,0,0,0.45);
      overflow: hidden;
      max-height: 240px;
    }
    .slash-row {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 12px;
      cursor: pointer;
      user-select: none;
    }
    .slash-row:hover,
    .slash-row.active {
      background: rgba(255,255,255,0.06);
    }
    .slash-left { min-width: 0; flex: 1; }
    .slash-cmd { font-weight: 950; font-size: 12px; color: rgba(255,255,255,0.92); }
    .slash-desc { font-weight: 700; font-size: 12px; color: rgba(255,255,255,0.60); margin-top: 2px; }

    .voice-page {
      flex: 1;
      min-height: 0;
      padding: 16px;
      overflow-y: auto;
      overflow-x: hidden;
    }
    .voice-page[hidden],
    .chat-page[hidden] {
      display: none !important;
    }
    .voice-shell {
      min-height: 100%;
      border-radius: 26px;
      border: 1px solid rgba(214,195,255,.10);
      background:
        radial-gradient(circle at 50% 8%, rgba(186,160,255,0.09), transparent 22%),
        linear-gradient(180deg, rgba(22,18,35,0.96) 0%, rgba(12,10,20,0.98) 100%);
      padding: 18px;
      position: relative;
      overflow: hidden;
    }
    .voice-topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 10px;
    }
    .voice-topbar-left,
    .voice-topbar-right {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .voice-nav-btn,
    .voice-stop-btn-top {
      min-height: 40px;
      padding: 0 14px;
      border-radius: 999px;
      border: 1px solid rgba(214,195,255,.14);
      color: var(--text);
      cursor: pointer;
      font-weight: 900;
      transition: transform .16s ease, background .16s ease, border-color .16s ease, box-shadow .16s ease;
    }
    .voice-nav-btn {
      background: linear-gradient(180deg, rgba(255,255,255,.08), rgba(255,255,255,.04));
      box-shadow: inset 0 1px 0 rgba(255,255,255,.10);
    }
    .voice-stop-btn-top {
      position: relative;
      background: linear-gradient(180deg, rgba(255, 90, 126, .34), rgba(255, 90, 126, .16));
      border-color: rgba(255, 116, 152, .34);
      box-shadow:
        inset 0 1px 0 rgba(255,255,255,.14),
        0 16px 34px rgba(255, 90, 126, .18),
        0 0 0 1px rgba(255, 90, 126, .12);
    }
    .voice-stop-btn-top::before {
      content: '';
      position: absolute;
      inset: -3px;
      border-radius: 999px;
      background: radial-gradient(circle at 30% 20%, rgba(255,255,255,.20), transparent 46%),
                  radial-gradient(circle at 70% 70%, rgba(255, 90, 126, .26), transparent 56%);
      opacity: .55;
      pointer-events: none;
      filter: blur(6px);
      transition: opacity .2s ease;
    }
    .voice-stop-btn-top:hover::before { opacity: .85; }
    .voice-nav-btn:hover,
    .voice-stop-btn-top:hover {
      transform: translateY(-1px);
      border-color: rgba(214,195,255,.24);
    }
    .voice-stop-btn-top:hover {
      border-color: rgba(255, 116, 152, .46);
      box-shadow:
        inset 0 1px 0 rgba(255,255,255,.16),
        0 18px 40px rgba(255, 90, 126, .24),
        0 0 0 1px rgba(255, 90, 126, .18);
    }
    .voice-stop-btn-top:active { transform: translateY(0px); }

    .voice-top { text-align: center; }
    .voice-pill { display: inline-flex; padding: 8px 12px; border-radius: 999px; background: rgba(255,255,255,.04); border: 1px solid rgba(214,195,255,.12); font-size: 11px; font-weight: 700; color: #ddd6fe; }
    .voice-name { margin-top: 16px; font-size: 15px; font-weight: 800; }
    .voice-status { margin-top: 8px; font-size: 30px; font-weight: 800; }
    .voice-sub { margin-top: 8px; font-size: 13px; font-weight: 500; color: var(--text-dim); }
    .orb-scene { position: relative; margin: 22px auto 14px auto; width: 330px; height: 330px; }
    .orb-wrap, .orb-glow, .orb-aura, .orb-core, .orb-liquid, .orb-glass, .orb-ring, .orb-ring-2, .orb-ring-3, .orb-photo-border, .orb-photo {
      position: absolute; inset: 0; border-radius: 50%;
    }
    .orb-wrap.speaking { animation: scenePulse 2.6s ease-in-out infinite; }
    .orb-wrap.listening { animation: sceneFloat 3.0s ease-in-out infinite; }
    .orb-wrap.emotion-angry { animation: sceneAngry 1.1s ease-in-out infinite; }
    .orb-wrap.emotion-happy { animation: sceneHappy 2.2s ease-in-out infinite; }
    .orb-wrap.emotion-sad { animation: sceneSad 3.2s ease-in-out infinite; }
    .orb-wrap.emotion-excited { animation: sceneExcited 1.3s ease-in-out infinite; }
    .orb-wrap.emotion-calm { animation: sceneCalm 3.8s ease-in-out infinite; }
    .orb-wrap.emotion-playful,
    .orb-wrap.emotion-teasing,
    .orb-wrap.emotion-flirty { animation: scenePlayful 1.9s ease-in-out infinite; }
    .orb-wrap.emotion-serious { animation: sceneSerious 2.7s ease-in-out infinite; }
    .orb-wrap.emotion-embarrassed,
    .orb-wrap.emotion-shy { animation: sceneShy 2.4s ease-in-out infinite; }
    .orb-wrap.emotion-affectionate { animation: sceneAffectionate 2.6s ease-in-out infinite; }
    .orb-glow { inset: -16%; background: radial-gradient(circle at 50% 50%, rgba(196,181,253,0.30), rgba(129,140,248,0.16) 34%, transparent 68%); filter: blur(30px); animation: glowPulse 3.1s ease-in-out infinite; }
    .orb-aura { inset: -7%; background: radial-gradient(circle at 50% 50%, rgba(255,255,255,0.08), transparent 58%), conic-gradient(from 180deg, rgba(125,211,252,0.14), rgba(192,132,252,0.12), rgba(196,181,253,0.18), rgba(125,211,252,0.14)); animation: auraDrift 5.5s ease-in-out infinite; }
    .orb-core { background: radial-gradient(circle at 32% 24%, rgba(255,255,255,0.94) 0 6%, rgba(255,255,255,0.18) 10%, transparent 18%), radial-gradient(circle at 68% 70%, rgba(191,219,254,0.12), transparent 20%), radial-gradient(circle at 28% 72%, rgba(125,211,252,0.22), transparent 30%), radial-gradient(circle at 72% 34%, rgba(192,132,252,0.24), transparent 28%), linear-gradient(145deg, rgba(17,24,39,0.12), rgba(9,14,30,0.46)), conic-gradient(from 220deg at 50% 50%, #9de4ff, #a471ff, #7fb4ff, #7de2e8, #9de4ff); box-shadow: inset -26px -36px 70px rgba(0,0,0,0.44), inset 10px 16px 46px rgba(255,255,255,0.08), 0 0 0 1px rgba(255,255,255,0.06); overflow: hidden; animation: coreMorph 3.1s ease-in-out infinite; }
    .orb-liquid { inset: 5%; background: radial-gradient(circle at 30% 30%, rgba(255,255,255,0.14), transparent 20%), radial-gradient(circle at 64% 44%, rgba(255,255,255,0.08), transparent 22%), conic-gradient(from 120deg, rgba(125,211,252,0.16), rgba(127,180,255,0.08), rgba(192,132,252,0.16), rgba(125,211,252,0.16)); mix-blend-mode: screen; opacity: 0.95; filter: blur(12px); animation: liquidDrift 4.7s ease-in-out infinite; }
    .orb-glass { inset: 6%; background: linear-gradient(145deg, rgba(255,255,255,0.22), rgba(255,255,255,0.02) 34%, rgba(255,255,255,0.08) 58%, rgba(255,255,255,0.04) 100%), radial-gradient(circle at 32% 20%, rgba(255,255,255,0.62), rgba(255,255,255,0.14) 16%, transparent 28%); mix-blend-mode: screen; pointer-events: none; }
    .orb-ring, .orb-ring-2, .orb-ring-3 { border: 1px solid rgba(255,255,255,0.16); }
    .orb-ring { inset: -4%; transform: rotateX(76deg); opacity: 0.55; }
    .orb-ring-2 { inset: 4%; transform: rotateY(76deg); opacity: 0.4; }
    .orb-ring-3 { inset: 16%; transform: rotateX(84deg); opacity: 0.3; }
    .orb-photo-border { inset: 28%; background: linear-gradient(145deg, rgba(255,255,255,0.24), rgba(255,255,255,0.08)); padding: 1px; box-shadow: 0 16px 40px rgba(0,0,0,0.28); }
    .orb-photo { inset: 1px; overflow: hidden; background: radial-gradient(circle at 35% 24%, rgba(255,255,255,0.10), transparent 16%), linear-gradient(180deg, rgba(255,255,255,0.12), rgba(255,255,255,0.03)), rgba(9, 14, 30, 0.92); display: flex; align-items: center; justify-content: center; backdrop-filter: blur(10px); }
    .orb-photo img { width: 100%; height: 100%; object-fit: cover; display: block; }

    @keyframes glowPulse { 0%,100% { transform: scale(0.92); opacity: 0.55; } 50% { transform: scale(1.14); opacity: 0.96; } }
    @keyframes auraDrift { 0%,100% { transform: rotate(0deg); opacity: 0.88; } 50% { transform: rotate(24deg); opacity: 0.96; } }
    @keyframes coreMorph { 0%,100% { transform: scale(1); filter: saturate(1.0); } 50% { transform: scale(1.02); filter: saturate(1.06); } }
    @keyframes liquidDrift { 0%,100% { transform: translate(0,0) rotate(0deg); } 50% { transform: translate(3px,-4px) rotate(14deg); } }
    @keyframes scenePulse { 0%,100% { transform: translateY(0) scale(1); } 40% { transform: translateY(-6px) scale(1.03); } 70% { transform: translateY(2px) scale(0.99); } }
    @keyframes sceneFloat { 0%,100% { transform: translateY(0) scale(1); } 50% { transform: translateY(-8px) scale(1.01); } }
    @keyframes sceneAngry { 0%,100% { transform: translateX(0) rotate(0deg) scale(1.01); } 20% { transform: translateX(-2px) rotate(-0.6deg) scale(1.03); } 40% { transform: translateX(2px) rotate(0.7deg) scale(1.02); } 60% { transform: translateX(-1px) rotate(-0.3deg) scale(1.04); } 80% { transform: translateX(1px) rotate(0.4deg) scale(1.02); } }
    @keyframes sceneHappy { 0%,100% { transform: translateY(0) scale(1); } 40% { transform: translateY(-10px) scale(1.03); } 70% { transform: translateY(2px) scale(1.01); } }
    @keyframes sceneSad { 0%,100% { transform: translateY(1px) scale(0.99); } 50% { transform: translateY(-3px) scale(1.0); } }
    @keyframes sceneExcited { 0%,100% { transform: translateY(0) scale(1); } 25% { transform: translateY(-10px) scale(1.04); } 50% { transform: translateY(2px) scale(0.99); } 75% { transform: translateY(-7px) scale(1.03); } }
    @keyframes sceneCalm { 0%,100% { transform: translateY(0) scale(1); } 50% { transform: translateY(-5px) scale(1.01); } }
    @keyframes scenePlayful { 0%,100% { transform: translateY(0) rotate(0deg) scale(1); } 30% { transform: translateY(-6px) rotate(-0.6deg) scale(1.03); } 60% { transform: translateY(2px) rotate(0.7deg) scale(1.01); } }
    @keyframes sceneSerious { 0%,100% { transform: translateY(0) scale(1.01); } 50% { transform: translateY(-4px) scale(1.01); } }
    @keyframes sceneShy { 0%,100% { transform: translateY(1px) rotate(0deg) scale(1); } 50% { transform: translateY(-6px) rotate(-0.4deg) scale(1.02); } }
    @keyframes sceneAffectionate { 0%,100% { transform: translateY(0) scale(1.02); } 50% { transform: translateY(-7px) scale(1.04); } }

    .caption-stack { display: grid; gap: 10px; margin-top: 8px; }
    .caption-card {
      border-radius: 18px;
      border: 1px solid rgba(214,195,255,.10);
      background: rgba(255,255,255,0.04);
      padding: 12px;
      box-shadow: 0 16px 40px rgba(0,0,0,0.20);
      overflow: hidden;
      position: relative;
    }
    .caption-card::after {
      content: "";
      position: absolute;
      inset: -120px;
      background: radial-gradient(circle at 30% 20%, rgba(255,255,255,0.07), transparent 46%);
      opacity: 0.6;
      filter: blur(14px);
      pointer-events: none;
    }
    .caption-head { display: flex; gap: 10px; align-items: center; position: relative; z-index: 1; }
    .caption-badge {
      width: 30px;
      height: 30px;
      border-radius: 12px;
      display: grid;
      place-items: center;
      font-weight: 950;
      background: rgba(255,255,255,0.05);
      border: 1px solid rgba(214,195,255,.12);
      color: rgba(255,255,255,0.86);
    }
    .caption-card.you .caption-badge { color: rgba(125,211,252,0.95); }
    .caption-card.ai .caption-badge { color: rgba(196,181,253,0.95); }
    .caption-labels { min-width: 0; }
    .caption-name { font-weight: 950; font-size: 13px; }
    .caption-meta { font-weight: 700; font-size: 12px; color: rgba(255,255,255,0.56); }
    .caption-text {
      margin-top: 10px;
      font-weight: 650;
      font-size: 13px;
      line-height: 1.35;
      color: rgba(255,255,255,0.92);
      white-space: pre-wrap;
      word-break: break-word;
      position: relative;
      z-index: 1;
    }
    .caption-card.idle .caption-text { color: rgba(255,255,255,0.42); }
    .word-hl {
      display: inline-block;
      padding: 0 6px;
      margin: 0 1px;
      border-radius: 999px;
      background: rgba(125, 211, 252, 0.18);
      border: 1px solid rgba(125, 211, 252, 0.32);
      box-shadow: 0 10px 24px rgba(125, 211, 252, 0.14);
      color: rgba(255,255,255,0.96);
      font-weight: 900;
    }

    .voice-card {
      margin-top: 10px;
      border-radius: 18px;
      border: 1px solid rgba(214,195,255,.10);
      background: rgba(255,255,255,0.03);
      padding: 12px;
    }
    .voice-card .label { font-size: 11px; font-weight: 900; color: rgba(255,255,255,0.54); }
    .voice-card .value { margin-top: 6px; font-size: 12px; font-weight: 750; color: rgba(255,255,255,0.80); }

    .voice-controls { margin-top: 10px; display: flex; justify-content: center; }
    .voice-stop {
      min-height: 44px;
      padding: 0 16px;
      border-radius: 999px;
      border: 1px solid rgba(214,195,255,.14);
      background: rgba(255,255,255,0.05);
      color: rgba(255,255,255,0.88);
      font-weight: 900;
      cursor: pointer;
      transition: transform .16s ease, background .16s ease, border-color .16s ease;
    }
    .voice-stop:hover { transform: translateY(-1px); border-color: rgba(214,195,255,.24); background: rgba(255,255,255,0.07); }

    .modal[hidden] { display: none !important; }
    .modal {
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,0.55);
      display: grid;
      place-items: center;
      padding: 18px;
    }
    .sheet {
      width: min(520px, 100%);
      border-radius: 20px;
      border: 1px solid rgba(214,195,255,.14);
      background: rgba(10, 8, 18, 0.96);
      box-shadow: 0 28px 80px rgba(0,0,0,0.65);
      overflow: hidden;
    }
    .sheet-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 12px 12px; border-bottom: 1px solid rgba(214,195,255,.10); }
    .sheet-title { font-weight: 950; font-size: 13px; }
    .sheet-sub { font-weight: 700; font-size: 12px; color: rgba(255,255,255,0.56); margin-top: 2px; }
    .sheet-body { padding: 12px; display: grid; gap: 10px; }
    .sheet-warn { padding: 10px 12px; border-radius: 16px; background: rgba(255, 212, 96, 0.08); border: 1px solid rgba(255, 212, 96, 0.18); color: rgba(255, 235, 170, 0.92); font-weight: 750; }
    .check-row { display: flex; gap: 10px; align-items: center; padding: 10px 12px; border-radius: 16px; border: 1px solid rgba(214,195,255,.10); background: rgba(255,255,255,0.03); cursor: pointer; }
    .check { width: 18px; height: 18px; accent-color: rgba(196,181,253,0.95); }
    .check-main { min-width: 0; }
    .check-title { font-weight: 950; font-size: 12px; }
    .check-note { font-weight: 700; font-size: 12px; color: rgba(255,255,255,0.60); margin-top: 2px; }
    .sheet-actions { display: flex; gap: 10px; padding: 12px; border-top: 1px solid rgba(214,195,255,.10); justify-content: flex-end; }
    .sheet-btn {
      min-height: 40px;
      padding: 0 14px;
      border-radius: 999px;
      border: 1px solid rgba(214,195,255,.14);
      background: rgba(255,255,255,0.05);
      color: rgba(255,255,255,0.88);
      font-weight: 900;
      cursor: pointer;
      transition: transform .16s ease, background .16s ease, border-color .16s ease;
    }
    .sheet-btn:hover { transform: translateY(-1px); border-color: rgba(214,195,255,.24); background: rgba(255,255,255,0.07); }
    .sheet-btn.primary { background: rgba(196,181,253,.18); border-color: rgba(196,181,253,.28); }
    .sheet-btn.danger { background: rgba(255, 90, 126, 0.14); border-color: rgba(255, 90, 126, 0.26); }

    /* Scrollbars */
    .conversation::-webkit-scrollbar,
    .voice-page::-webkit-scrollbar { width: 12px; height: 12px; }
    .conversation::-webkit-scrollbar-thumb,
    .voice-page::-webkit-scrollbar-thumb { background: rgba(196,181,253,0.72); border-radius: 999px; border: 3px solid rgba(0,0,0,0); background-clip: padding-box; }
    .conversation::-webkit-scrollbar-track,
    .voice-page::-webkit-scrollbar-track { background: rgba(255,255,255,0.03); border-radius: 999px; }
"""
