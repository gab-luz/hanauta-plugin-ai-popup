# -*- coding: utf-8 -*-

# NOTE: Keep the HTML as a standalone module so agents and humans don't have to scroll through
# a giant mixed Python+HTML file when changing backend logic.

WEB_POPUP_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Hanauta AI</title>
  <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
  <style>
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
      --ok: rgba(57, 255, 136, 0.92);
      --warn: rgba(255, 212, 96, 0.92);
      --bad: rgba(255, 92, 130, 0.92);
      --border: rgba(214,195,255,.12);
      --border-2: rgba(214,195,255,.08);
      --shadow: rgba(0,0,0,0.35);
      --shadow-2: rgba(0,0,0,0.55);
      --radius: 22px;
      --radius-2: 18px;
      --radius-3: 14px;
      --font: system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, 'Noto Sans', sans-serif;
    }

    * { box-sizing: border-box; }
    html, body { height: 100%; }
    body {
      margin: 0;
      font-family: var(--font);
      background: radial-gradient(circle at 50% 8%, rgba(186,160,255,0.10), transparent 26%),
                  radial-gradient(circle at 18% 30%, rgba(125, 211, 252, 0.08), transparent 24%),
                  linear-gradient(180deg, rgba(16, 12, 26, 0.98), rgba(10, 8, 18, 0.98));
      color: var(--text);
      overflow: hidden;
    }

    .window {
      display: flex;
      flex-direction: column;
      height: 100%;
      padding: 12px;
      gap: 12px;
    }

    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 12px 12px;
      border-radius: 26px;
      border: 1px solid rgba(214,195,255,.10);
      background:
        radial-gradient(circle at 20% 20%, rgba(125,211,252,0.08), transparent 28%),
        radial-gradient(circle at 80% 10%, rgba(196,181,253,0.09), transparent 28%),
        linear-gradient(180deg, rgba(22,18,35,0.96) 0%, rgba(12,10,20,0.98) 100%);
      box-shadow: 0 16px 46px rgba(0,0,0,.24);
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
    .brand .title { font-size: 15px; font-weight: 900; line-height: 1.15; }
    .brand .status { font-size: 12px; font-weight: 700; color: var(--text-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 260px; }

    .info-pop {
      position: relative;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      margin-left: 8px;
    }
    .info-dot {
      width: 18px;
      height: 18px;
      border-radius: 999px;
      display: grid;
      place-items: center;
      font-weight: 900;
      font-size: 12px;
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
    }
    .icon-btn {
      width: 38px;
      height: 38px;
      border-radius: 14px;
      border: 1px solid rgba(214,195,255,.12);
      background: rgba(255,255,255,0.04);
      color: rgba(255,255,255,0.90);
      cursor: pointer;
      font-weight: 900;
      transition: transform .16s ease, background .16s ease, border-color .16s ease, box-shadow .16s ease;
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.08);
    }
    .icon-btn:hover {
      transform: translateY(-1px);
      background: rgba(255,255,255,0.06);
      border-color: rgba(214,195,255,.22);
    }
    .icon-btn.magic-ready {
      border-color: rgba(57,255,136,.55);
      box-shadow: 0 0 0 2px rgba(57,255,136,.14), inset 0 1px 0 rgba(255,255,255,0.10);
    }

    .body {
      flex: 1;
      min-height: 0;
      border-radius: 26px;
      border: 1px solid rgba(214,195,255,.10);
      background: rgba(9, 8, 16, 0.42);
      overflow: hidden;
    }

    .chat-page {
      display: flex;
      flex-direction: column;
      height: 100%;
      padding: 12px;
      gap: 12px;
    }

    .backend-row {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }
    .backend-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 10px;
      border-radius: 999px;
      border: 1px solid rgba(214,195,255,.12);
      background: rgba(255,255,255,0.04);
      cursor: pointer;
      user-select: none;
      transition: transform .16s ease, background .16s ease, border-color .16s ease;
      font-weight: 850;
      font-size: 12px;
      color: rgba(255,255,255,0.86);
    }
    .backend-pill:hover { transform: translateY(-1px); border-color: rgba(214,195,255,.22); }
    .backend-pill.active { background: rgba(196,181,253,.16); border-color: rgba(196,181,253,.38); color: rgba(255,255,255,0.94); }
    .backend-pill img { width: 16px; height: 16px; border-radius: 4px; }

    .conversation {
      flex: 1;
      min-height: 0;
      overflow-y: auto;
      overflow-x: hidden;
      padding-right: 4px;
    }

    .message {
      display: flex;
      gap: 10px;
      margin: 10px 2px;
      align-items: flex-start;
    }
    .message.you { flex-direction: row-reverse; }
    .avatar {
      width: 34px;
      height: 34px;
      border-radius: 12px;
      display: grid;
      place-items: center;
      font-weight: 900;
      background: rgba(255,255,255,0.04);
      border: 1px solid rgba(214,195,255,.12);
      color: rgba(255,255,255,0.86);
      flex: 0 0 auto;
    }
    .bubble {
      max-width: 88%;
      border-radius: 18px;
      border: 1px solid rgba(214,195,255,.10);
      background: rgba(255,255,255,0.04);
      padding: 10px 12px;
      box-shadow: 0 12px 26px rgba(0,0,0,0.18);
      overflow: hidden;
    }
    .bubble.you { background: rgba(125,211,252,0.10); border-color: rgba(125,211,252,0.20); }
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
      line-height: 1.45;
      font-weight: 560;
      color: rgba(255,255,255,0.90);
      white-space: pre-wrap;
      word-break: break-word;
    }

    .composer {
      border-radius: 22px;
      border: 0;
      background: rgba(255,255,255,.04);
      padding: 12px;
    }
    .composer textarea {
      width: 100%;
      min-height: 76px;
      resize: none;
      border: 0;
      background: rgba(255,255,255,.04);
      color: var(--text);
      border-radius: 18px;
      padding: 12px 14px;
      font: inherit;
      font-weight: 500;
      outline: none;
      overflow-x: hidden;
    }
    .composer-row { display: flex; align-items: center; gap: 10px; margin-top: 10px; }
    .provider { flex: 1; font-size: 12px; font-weight: 600; color: var(--text-dim); }
    .send-btn {
      min-width: 40px;
      height: 40px;
      padding: 0 12px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      background: rgba(198,180,255,.18);
      color: #fff;
      font-weight: 800;
      font-size: 15px;
    }
    .send-btn.secondary { background: rgba(255,255,255,.06); color: var(--text); }
    .send-btn .btn-icon {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      line-height: 1;
      transform: translateY(-0.5px);
    }

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
  </style>
</head>
<body>
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
        <button class="icon-btn" id="modelsBtn" title="Start/Stop voice backends" aria-label="Start/Stop models">▶</button>
        <button class="icon-btn" id="voiceBtn" title="Voice mode">🎙</button>
        <button class="icon-btn" id="settingsBtn" title="Settings">⚙</button>
        <button class="icon-btn" id="charactersBtn" title="Characters">☺</button>
        <button class="icon-btn" id="closeBtn" title="Close">✕</button>
      </div>
    </div>
    <div class="body">
      <div class="chat-page" id="chatPage">
        <div class="backend-row" id="backendRow"></div>
        <div class="conversation" id="conversation"></div>
        <div class="composer">
          <textarea id="composerInput" placeholder="Message the model... Enter to send"></textarea>
          <div class="composer-row">
            <div class="provider" id="providerLabel"></div>
            <button class="send-btn secondary" id="sttBtn" title="Dictate (speech to text)" aria-label="Dictate"><span class="btn-icon">🎤</span></button>
            <button class="send-btn secondary" id="archiveBtn" title="Archive chat" aria-label="Archive chat"><span class="btn-icon">🗄</span></button>
            <button class="send-btn secondary" id="exportBtn" title="Export chat" aria-label="Export chat"><span class="btn-icon">⤴</span></button>
            <button class="send-btn secondary" id="clearBtn" title="Clear chat" aria-label="Clear chat"><span class="btn-icon">🧹</span></button>
            <button class="send-btn" id="sendBtn" title="Send message" aria-label="Send message"><span class="btn-icon">➤</span></button>
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
            <button class="icon-btn" id="modelModalCloseBtn" title="Close">✕</button>
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
    let bridge = null;
    let state = {};
    let lastDraftId = 0;

    function esc(s) {
      return String(s || '').replace(/[&<>\"']/g, function(c) {
        return ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c] || c);
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
  </script>
</body>
</html>
"""
