from __future__ import annotations

import html
import json
import math
import os
import struct
import sys
import tempfile
import wave
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, QUrl, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QCursor
from PyQt6.QtWidgets import QApplication, QFileDialog, QWidget, QVBoxLayout
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView


HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Floating AI Window</title>
  <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
  <style>
    :root {
      color-scheme: dark;
      --bg-0: rgba(16, 14, 23, 0.76);
      --bg-1: rgba(30, 27, 46, 0.92);
      --bg-2: rgba(35, 32, 46, 0.92);
      --bg-3: rgba(255, 255, 255, 0.06);
      --bg-4: rgba(255, 255, 255, 0.10);
      --text-0: #f3eef7;
      --text-1: rgba(243, 238, 247, 0.82);
      --text-2: rgba(243, 238, 247, 0.58);
      --outline: rgba(255, 255, 255, 0.08);
      --outline-2: rgba(208, 188, 255, 0.24);
      --primary: #d0bcff;
      --primary-2: #381e72;
      --surface-bubble: rgba(255,255,255,0.07);
      --assistant-bubble: rgba(45, 41, 59, 0.96);
      --success: #98f5c7;
      --danger: #ffb4ab;
      --shadow: 0 26px 60px rgba(0,0,0,.42);
      --radius-window: 24px;
      --radius-bubble: 20px;
      --radius-chip: 999px;
      --font-sans: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      --font-mono: "JetBrains Mono", ui-monospace, SFMono-Regular, monospace;
      --font-display: Outfit, var(--font-sans);
    }

    * { box-sizing: border-box; }
    html, body {
      margin: 0;
      padding: 0;
      width: 100%;
      height: 100%;
      background: transparent;
      overflow: hidden;
      font-family: var(--font-sans);
      color: var(--text-0);
      user-select: none;
    }

    body {
      display: flex;
      align-items: center;
      justify-content: center;
      background:
        radial-gradient(circle at top left, rgba(208,188,255,.10), transparent 34%),
        radial-gradient(circle at bottom right, rgba(239,184,200,.08), transparent 28%),
        transparent;
      padding: 14px;
    }

    .window {
      width: min(100%, 640px);
      height: min(100%, 760px);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      border-radius: var(--radius-window);
      background: linear-gradient(180deg, rgba(38,35,51,.78), rgba(24,22,32,.88));
      border: 1px solid var(--outline);
      box-shadow: var(--shadow);
      backdrop-filter: blur(28px) saturate(145%);
      -webkit-backdrop-filter: blur(28px) saturate(145%);
    }

    .window::before {
      content: "";
      position: absolute;
      inset: 16px;
      pointer-events: none;
      border-radius: calc(var(--radius-window) - 10px);
      border: 1px solid rgba(255,255,255,0.02);
    }

    .header {
      position: relative;
      z-index: 3;
      padding: 10px 14px 8px 14px;
      border-bottom: 1px solid var(--outline);
      background: linear-gradient(180deg, rgba(255,255,255,.03), rgba(255,255,255,.01));
    }

    .titlebar {
      display: flex;
      align-items: center;
      gap: 12px;
      padding-bottom: 10px;
    }

    .drag-region {
      flex: 1;
      min-height: 26px;
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 0 10px;
      border-radius: 999px;
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.04);
      cursor: grab;
      overflow: hidden;
    }

    .drag-region:active { cursor: grabbing; }

    .window-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: linear-gradient(180deg, rgba(255,255,255,.38), rgba(255,255,255,.08));
      box-shadow: 0 0 0 1px rgba(255,255,255,.08) inset;
      flex: 0 0 auto;
    }

    .window-title {
      font-family: var(--font-display);
      font-weight: 700;
      letter-spacing: .01em;
      font-size: 13px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      color: rgba(255,255,255,.90);
    }

    .window-subtitle {
      font-size: 11px;
      color: var(--text-2);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .controls {
      display: flex;
      gap: 8px;
      flex: 0 0 auto;
    }

    .icon-btn, .tab-btn, .composer-btn, .chip-btn {
      border: none;
      outline: none;
      cursor: pointer;
      color: var(--text-0);
      transition: transform .14s ease, background .14s ease, color .14s ease, opacity .14s ease;
    }

    .icon-btn:hover, .tab-btn:hover, .composer-btn:hover, .chip-btn:hover {
      transform: translateY(-1px);
    }

    .icon-btn {
      width: 34px;
      height: 34px;
      border-radius: 999px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background: rgba(255,255,255,.05);
      border: 1px solid rgba(255,255,255,.05);
      color: rgba(255,255,255,.88);
      font-size: 15px;
    }

    .icon-btn[data-active="true"] {
      background: rgba(208,188,255,.20);
      color: var(--primary);
      border-color: rgba(208,188,255,.22);
    }

    .tab-row {
      display: flex;
      gap: 8px;
    }

    .tab-btn {
      flex: 1;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      min-height: 42px;
      border-radius: 14px;
      background: rgba(255,255,255,.03);
      border: 1px solid rgba(255,255,255,.04);
      font-size: 13px;
      font-weight: 600;
      color: rgba(255,255,255,.66);
    }

    .tab-btn.active {
      background: rgba(255,255,255,.06);
      color: rgba(255,255,255,.94);
      border-color: rgba(255,255,255,.06);
    }

    .material {
      font-size: 16px;
      opacity: .90;
    }

    .messages {
      flex: 1;
      overflow-y: auto;
      padding: 18px 18px 20px 18px;
      display: flex;
      flex-direction: column;
      gap: 18px;
      user-select: text;
      scroll-behavior: smooth;
    }

    .messages::-webkit-scrollbar {
      width: 6px;
      height: 6px;
    }
    .messages::-webkit-scrollbar-thumb {
      background: rgba(255,255,255,.12);
      border-radius: 999px;
    }

    .message-wrap {
      display: flex;
      flex-direction: column;
      gap: 7px;
    }

    .message-wrap.user {
      align-items: flex-end;
    }

    .message-wrap.assistant,
    .message-wrap.audio {
      align-items: stretch;
    }

    .meta-strip {
      display: inline-flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
      align-self: flex-end;
      font-size: 11px;
      color: var(--text-2);
      background: rgba(255,255,255,.06);
      padding: 8px 12px;
      border-radius: 14px 14px 4px 14px;
      border: 1px solid rgba(255,255,255,.04);
      max-width: 92%;
    }

    .bubble {
      position: relative;
      border-radius: var(--radius-bubble);
      border: 1px solid rgba(255,255,255,.05);
      overflow: hidden;
    }

    .user .bubble {
      max-width: min(88%, 680px);
      background: linear-gradient(180deg, rgba(255,255,255,.09), rgba(255,255,255,.06));
      border-top-right-radius: 7px;
      padding: 14px 16px;
    }

    .assistant .bubble,
    .audio .bubble {
      width: 100%;
      background: linear-gradient(180deg, rgba(48,44,64,.97), rgba(33,30,45,.97));
      box-shadow: inset 0 1px 0 rgba(255,255,255,.02);
    }

    .bubble-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 12px 14px 10px 14px;
      border-bottom: 1px solid rgba(255,255,255,.06);
      font-size: 12px;
    }

    .bubble-author {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-weight: 700;
      color: var(--primary);
    }

    .bubble-author.user-label {
      color: rgba(255,255,255,.86);
    }

    .bubble-actions {
      display: inline-flex;
      gap: 6px;
      opacity: .65;
    }

    .bubble-action {
      width: 28px;
      height: 28px;
      border-radius: 999px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background: rgba(255,255,255,.04);
      border: 1px solid rgba(255,255,255,.04);
      cursor: pointer;
      font-size: 13px;
      color: rgba(255,255,255,.84);
    }

    .bubble-body {
      padding: 14px 16px 16px 16px;
      font-size: 14px;
      line-height: 1.6;
      color: var(--text-1);
      overflow-wrap: anywhere;
    }

    .bubble-body strong { color: #ffffff; }
    .bubble-body code,
    .bubble-body pre {
      font-family: var(--font-mono);
      border-radius: 12px;
    }
    .bubble-body code {
      font-size: 12px;
      background: rgba(255,255,255,.07);
      padding: 2px 6px;
      border: 1px solid rgba(255,255,255,.06);
    }
    .bubble-body pre {
      white-space: pre-wrap;
      padding: 12px;
      background: rgba(0,0,0,.22);
      border: 1px solid rgba(255,255,255,.05);
      margin: 12px 0;
      overflow: auto;
    }
    .bubble-body h1, .bubble-body h2, .bubble-body h3, .bubble-body h4 {
      color: #ffffff;
      margin: 14px 0 8px 0;
      line-height: 1.25;
    }
    .bubble-body h4 { font-size: 17px; }
    .bubble-body p:first-child { margin-top: 0; }
    .bubble-body p:last-child { margin-bottom: 0; }
    .bubble-body a {
      color: var(--primary);
      text-decoration: none;
    }
    .bubble-body ul, .bubble-body ol {
      margin: 8px 0;
      padding-left: 22px;
    }
    .bubble-body blockquote {
      margin: 12px 0;
      padding-left: 14px;
      border-left: 3px solid rgba(208,188,255,.45);
      color: rgba(255,255,255,.74);
    }

    .chip-row {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      padding: 0 16px 14px 16px;
    }

    .chip-btn {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      min-height: 30px;
      padding: 0 10px;
      border-radius: 10px;
      background: rgba(255,255,255,.05);
      border: 1px solid rgba(255,255,255,.05);
      color: rgba(255,255,255,.84);
      font-size: 11px;
    }

    .chip-dot {
      width: 14px;
      height: 14px;
      border-radius: 50%;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      color: #101010;
      font-size: 10px;
      font-weight: 700;
      background: white;
      flex: 0 0 auto;
    }

    .query-row {
      padding: 0 16px 14px 16px;
    }

    .query-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 9px 12px;
      border-radius: 12px;
      background: rgba(0,0,0,.22);
      border: 1px solid rgba(255,255,255,.04);
      color: rgba(255,255,255,.68);
      font-size: 12px;
    }

    .audio-content {
      padding: 14px 16px 16px 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .audio-top {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .audio-play {
      width: 42px;
      height: 42px;
      flex: 0 0 auto;
      border-radius: 999px;
      border: 1px solid rgba(208,188,255,.22);
      background: rgba(208,188,255,.14);
      color: var(--primary);
      font-size: 18px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: transform .14s ease, background .14s ease;
    }

    .audio-play:hover {
      transform: translateY(-1px) scale(1.02);
      background: rgba(208,188,255,.18);
    }

    .audio-meta {
      display: flex;
      flex-direction: column;
      gap: 2px;
      min-width: 0;
    }

    .audio-title {
      font-weight: 700;
      color: rgba(255,255,255,.96);
      font-size: 13px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .audio-subtitle {
      color: var(--text-2);
      font-size: 11px;
    }

    .wave-wrap {
      position: relative;
      height: 56px;
      width: 100%;
      border-radius: 14px;
      background: rgba(0,0,0,.18);
      border: 1px solid rgba(255,255,255,.04);
      overflow: hidden;
    }

    canvas.waveform {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      display: block;
    }

    .audio-times {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      font-size: 11px;
      color: var(--text-2);
      font-family: var(--font-mono);
    }

    .composer {
      border-top: 1px solid var(--outline);
      padding: 14px;
      background: linear-gradient(180deg, rgba(35,32,46,.98), rgba(27,24,37,.98));
    }

    .composer-main {
      display: flex;
      align-items: flex-end;
      gap: 10px;
      background: rgba(17, 16, 24, 0.86);
      border: 1px solid rgba(255,255,255,.05);
      border-radius: 18px;
      padding: 10px;
      box-shadow: inset 0 1px 0 rgba(255,255,255,.02);
    }

    .composer-btn {
      width: 38px;
      height: 38px;
      border-radius: 14px;
      background: rgba(255,255,255,.05);
      border: 1px solid rgba(255,255,255,.04);
      color: rgba(255,255,255,.86);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 16px;
      flex: 0 0 auto;
    }

    .composer-btn.send {
      background: rgba(208,188,255,.16);
      border-color: rgba(208,188,255,.20);
      color: var(--primary);
    }

    .composer-input {
      min-height: 22px;
      max-height: 130px;
      overflow-y: auto;
      resize: none;
      width: 100%;
      background: transparent;
      border: none;
      outline: none;
      color: rgba(255,255,255,.96);
      font-size: 14px;
      line-height: 1.45;
      padding: 8px 2px;
      font-family: var(--font-sans);
    }

    .composer-input::placeholder {
      color: rgba(255,255,255,.26);
    }

    .composer-footer {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      padding: 8px 6px 0 6px;
      font-size: 11px;
      color: var(--text-2);
      font-family: var(--font-mono);
      flex-wrap: wrap;
    }

    .footer-group {
      display: flex;
      gap: 12px;
      align-items: center;
      flex-wrap: wrap;
    }

    .footer-pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      cursor: default;
    }

    .status-toast {
      position: absolute;
      right: 20px;
      top: 74px;
      z-index: 20;
      background: rgba(0,0,0,.42);
      border: 1px solid rgba(255,255,255,.08);
      color: rgba(255,255,255,.92);
      border-radius: 999px;
      padding: 9px 12px;
      font-size: 12px;
      backdrop-filter: blur(18px);
      -webkit-backdrop-filter: blur(18px);
      opacity: 0;
      transform: translateY(-8px);
      pointer-events: none;
      transition: opacity .18s ease, transform .18s ease;
    }

    .status-toast.show {
      opacity: 1;
      transform: translateY(0);
    }

    @media (max-width: 720px) {
      body { padding: 8px; }
      .window { width: 100%; height: 100%; }
      .messages { padding: 14px; }
      .composer { padding: 10px; }
    }
  </style>
</head>
<body>
  <div class="window">
    <div class="header">
      <div class="titlebar">
        <div class="drag-region" id="dragRegion" title="Drag window">
          <span class="window-dot"></span>
          <span class="window-dot"></span>
          <div style="min-width:0;display:flex;flex-direction:column;gap:1px;overflow:hidden;">
            <div class="window-title">Hanauta AI Window</div>
            <div class="window-subtitle">Floating chat for i3 • HTML + styled replies + voice clips</div>
          </div>
        </div>
        <div class="controls">
          <button class="icon-btn" id="pinBtn" title="Toggle always on top">📌</button>
          <button class="icon-btn" id="minBtn" title="Minimize">—</button>
          <button class="icon-btn" id="closeBtn" title="Close">✕</button>
        </div>
      </div>
      <div class="tab-row">
        <button class="tab-btn active"><span class="material">✦</span> Intelligence</button>
        <button class="tab-btn"><span class="material">◌</span> Anime</button>
      </div>
    </div>

    <div id="toast" class="status-toast">Copied</div>
    <div class="messages" id="messages"></div>

    <div class="composer">
      <div class="composer-main">
        <button class="composer-btn" id="audioPickBtn" title="Attach audio clip">🎙</button>
        <textarea id="composerInput" class="composer-input" rows="1" placeholder='Message the model… “/” for commands'></textarea>
        <button class="composer-btn send" id="sendBtn" title="Send">↑</button>
      </div>
      <div class="composer-footer">
        <div class="footer-group">
          <span class="footer-pill">✦ Demo bridge</span>
          <span class="footer-pill">⌕ Rich HTML</span>
          <span class="footer-pill">♪ Waveform audio</span>
        </div>
        <div class="footer-group">
          <span>/clear</span>
          <span>Ctrl+L</span>
        </div>
      </div>
    </div>
  </div>

  <script>
    let bridge = null;
    let toastTimer = null;
    let audioContext = null;

    const messagesEl = document.getElementById('messages');
    const inputEl = document.getElementById('composerInput');
    const sendBtn = document.getElementById('sendBtn');
    const audioPickBtn = document.getElementById('audioPickBtn');
    const toastEl = document.getElementById('toast');
    const pinBtn = document.getElementById('pinBtn');

    function escapeHtml(value) {
      return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }

    function plainTextToHtml(value) {
      return escapeHtml(value).replace(/\n/g, '<br>');
    }

    function showToast(text) {
      toastEl.textContent = text;
      toastEl.classList.add('show');
      if (toastTimer) clearTimeout(toastTimer);
      toastTimer = setTimeout(() => toastEl.classList.remove('show'), 1400);
    }

    function autoresizeTextarea() {
      inputEl.style.height = 'auto';
      inputEl.style.height = Math.min(inputEl.scrollHeight, 130) + 'px';
    }

    function scrollToBottom() {
      messagesEl.scrollTop = messagesEl.scrollHeight + 1000;
    }

    function formatClock(seconds) {
      const total = Math.max(0, Math.floor(seconds || 0));
      const mins = Math.floor(total / 60);
      const secs = total % 60;
      return `${mins}:${String(secs).padStart(2, '0')}`;
    }

    function createMetaStrip(meta) {
      if (!meta || (!meta.version && !meta.temperature && !meta.tokens && !meta.extra)) {
        return '';
      }
      const parts = [];
      if (meta.version) parts.push(`<span>🔑 ${escapeHtml(meta.version)}</span>`);
      if (meta.temperature !== undefined && meta.temperature !== null) parts.push(`<span>🌡 ${escapeHtml(meta.temperature)}</span>`);
      if (meta.tokens) parts.push(`<span>🪙 ${escapeHtml(meta.tokens)}</span>`);
      if (meta.extra) parts.push(`<span>${escapeHtml(meta.extra)}</span>`);
      return `<div class="meta-strip">${parts.join('')}</div>`;
    }

    function sourceLabelToChip(source) {
      const label = source.label || source;
      const initial = String(label).trim().charAt(0).toUpperCase() || '•';
      return `<button class="chip-btn" type="button"><span class="chip-dot">${escapeHtml(initial)}</span><span>${escapeHtml(label)}</span></button>`;
    }

    function attachBubbleActions(container, payload) {
      container.querySelectorAll('[data-action="copy"]').forEach((btn) => {
        btn.addEventListener('click', async () => {
          const raw = payload.copy_text || payload.text || payload.title || '';
          try {
            await navigator.clipboard.writeText(raw);
            if (bridge && bridge.notifyCopied) bridge.notifyCopied();
            else showToast('Copied');
          } catch (_) {
            showToast('Clipboard unavailable');
          }
        });
      });
    }

    function appendUserMessage(payload) {
      const wrap = document.createElement('div');
      wrap.className = 'message-wrap user';
      wrap.innerHTML = `
        ${createMetaStrip(payload.meta)}
        <div class="bubble">
          <div class="bubble-header">
            <span class="bubble-author user-label">👤 ${escapeHtml(payload.author || 'You')}</span>
            <div class="bubble-actions">
              <button class="bubble-action" type="button" data-action="copy" title="Copy">⧉</button>
            </div>
          </div>
          <div class="bubble-body">${payload.html ? payload.html : plainTextToHtml(payload.text || '')}</div>
        </div>
      `;
      messagesEl.appendChild(wrap);
      attachBubbleActions(wrap, payload);
      scrollToBottom();
    }

    function appendAssistantMessage(payload) {
      const wrap = document.createElement('div');
      wrap.className = 'message-wrap assistant';
      const sourceRow = (payload.sources && payload.sources.length)
        ? `<div class="chip-row">${payload.sources.map(sourceLabelToChip).join('')}</div>`
        : '';
      const queryRow = payload.query
        ? `<div class="query-row"><div class="query-pill">⌕ ${escapeHtml(payload.query)}</div></div>`
        : '';

      wrap.innerHTML = `
        <div class="bubble">
          <div class="bubble-header">
            <span class="bubble-author">✦ ${escapeHtml(payload.author || 'Assistant')}</span>
            <div class="bubble-actions">
              <button class="bubble-action" type="button" data-action="copy" title="Copy">⧉</button>
            </div>
          </div>
          <div class="bubble-body">${payload.html ? payload.html : plainTextToHtml(payload.text || '')}</div>
          ${sourceRow}
          ${queryRow}
        </div>
      `;
      messagesEl.appendChild(wrap);
      attachBubbleActions(wrap, payload);
      scrollToBottom();
    }

    function drawWaveform(canvas, bars, progress) {
      const ratio = window.devicePixelRatio || 1;
      const width = canvas.clientWidth;
      const height = canvas.clientHeight;
      if (width <= 0 || height <= 0) return;
      canvas.width = Math.floor(width * ratio);
      canvas.height = Math.floor(height * ratio);
      const ctx = canvas.getContext('2d');
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      ctx.clearRect(0, 0, width, height);

      const count = Math.max(16, bars.length || 0);
      const gap = 2;
      const barWidth = Math.max(2, Math.floor((width - (count - 1) * gap) / count));
      const totalDrawnWidth = count * barWidth + (count - 1) * gap;
      const startX = Math.max(0, Math.floor((width - totalDrawnWidth) / 2));
      const center = height / 2;
      const progressX = width * Math.max(0, Math.min(1, progress || 0));

      for (let i = 0; i < count; i++) {
        const amp = bars.length ? bars[Math.min(i, bars.length - 1)] : 0.35;
        const x = startX + i * (barWidth + gap);
        const h = Math.max(4, amp * (height - 12));
        const y = center - h / 2;
        const passed = (x + barWidth / 2) <= progressX;
        ctx.fillStyle = passed ? 'rgba(208,188,255,0.95)' : 'rgba(255,255,255,0.25)';
        const radius = Math.min(3, barWidth / 2, h / 2);
        roundRect(ctx, x, y, barWidth, h, radius);
        ctx.fill();
      }
    }

    function roundRect(ctx, x, y, width, height, radius) {
      ctx.beginPath();
      ctx.moveTo(x + radius, y);
      ctx.arcTo(x + width, y, x + width, y + height, radius);
      ctx.arcTo(x + width, y + height, x, y + height, radius);
      ctx.arcTo(x, y + height, x, y, radius);
      ctx.arcTo(x, y, x + width, y, radius);
      ctx.closePath();
    }

    async function buildWaveformData(url, points = 56) {
      try {
        if (!audioContext) {
          audioContext = new (window.AudioContext || window.webkitAudioContext)();
        }
        const response = await fetch(url);
        const arrayBuffer = await response.arrayBuffer();
        const audioBuffer = await audioContext.decodeAudioData(arrayBuffer.slice(0));
        const raw = audioBuffer.getChannelData(0);
        const blockSize = Math.floor(raw.length / points) || 1;
        const filtered = [];
        for (let i = 0; i < points; i++) {
          const start = i * blockSize;
          const end = Math.min(start + blockSize, raw.length);
          let sum = 0;
          for (let j = start; j < end; j++) sum += Math.abs(raw[j]);
          filtered.push(sum / Math.max(1, end - start));
        }
        const max = Math.max(...filtered, 0.001);
        return filtered.map(v => Math.max(0.12, Math.min(1, v / max)));
      } catch (_) {
        return Array.from({ length: points }, (_, i) => {
          const seed = (Math.sin(i * 1.7) + 1) / 2;
          return 0.18 + seed * 0.58;
        });
      }
    }

    function appendAudioMessage(payload) {
      const wrap = document.createElement('div');
      wrap.className = 'message-wrap audio';
      const title = payload.title || 'Audio clip';
      const author = payload.author || 'Assistant voice';
      const audioId = `audio_${Math.random().toString(16).slice(2)}`;
      wrap.innerHTML = `
        <div class="bubble">
          <div class="bubble-header">
            <span class="bubble-author">♪ ${escapeHtml(author)}</span>
            <div class="bubble-actions">
              <button class="bubble-action" type="button" data-action="copy" title="Copy label">⧉</button>
            </div>
          </div>
          <div class="audio-content">
            <div class="audio-top">
              <button class="audio-play" type="button" data-role="play">▶</button>
              <div class="audio-meta">
                <div class="audio-title">${escapeHtml(title)}</div>
                <div class="audio-subtitle">${escapeHtml(payload.subtitle || 'Waveform preview')}</div>
              </div>
            </div>
            <div class="wave-wrap">
              <canvas class="waveform"></canvas>
            </div>
            <div class="audio-times">
              <span data-role="current">0:00</span>
              <span data-role="duration">${formatClock(payload.duration || 0)}</span>
            </div>
            <audio id="${audioId}" preload="metadata" src="${escapeHtml(payload.audio_url || '')}"></audio>
          </div>
        </div>
      `;
      messagesEl.appendChild(wrap);
      attachBubbleActions(wrap, { copy_text: title });
      scrollToBottom();

      const canvas = wrap.querySelector('canvas.waveform');
      const playBtn = wrap.querySelector('[data-role="play"]');
      const currentEl = wrap.querySelector('[data-role="current"]');
      const durationEl = wrap.querySelector('[data-role="duration"]');
      const audio = wrap.querySelector('audio');
      let bars = Array.from({ length: 56 }, () => 0.25);
      let rafId = null;

      function render() {
        const progress = audio.duration ? (audio.currentTime / audio.duration) : 0;
        drawWaveform(canvas, bars, progress);
        currentEl.textContent = formatClock(audio.currentTime);
        if (!Number.isNaN(audio.duration) && Number.isFinite(audio.duration)) {
          durationEl.textContent = formatClock(audio.duration);
        }
        if (!audio.paused && !audio.ended) {
          rafId = requestAnimationFrame(render);
        }
      }

      function stopFrame() {
        if (rafId) {
          cancelAnimationFrame(rafId);
          rafId = null;
        }
      }

      playBtn.addEventListener('click', async () => {
        try {
          if (audio.paused) {
            await audio.play();
            playBtn.textContent = '❚❚';
            stopFrame();
            render();
          } else {
            audio.pause();
          }
        } catch (_) {
          showToast('Could not play audio');
        }
      });

      audio.addEventListener('pause', () => {
        playBtn.textContent = '▶';
        stopFrame();
        render();
      });

      audio.addEventListener('ended', () => {
        playBtn.textContent = '↺';
        stopFrame();
        render();
      });

      audio.addEventListener('loadedmetadata', () => {
        render();
      });

      window.addEventListener('resize', render);

      buildWaveformData(payload.audio_url || '').then((data) => {
        bars = data;
        render();
      });

      render();
    }

    function appendPayload(payload) {
      if (!payload || typeof payload !== 'object') return;
      if (payload.kind === 'user') appendUserMessage(payload);
      else if (payload.kind === 'assistant') appendAssistantMessage(payload);
      else if (payload.kind === 'audio') appendAudioMessage(payload);
      else if (payload.kind === 'clear') messagesEl.innerHTML = '';
    }

    function sendPrompt() {
      const text = inputEl.value.trim();
      if (!text) return;
      if (bridge && bridge.submitPrompt) {
        bridge.submitPrompt(text);
      }
      inputEl.value = '';
      autoresizeTextarea();
    }

    function setupButtons() {
      sendBtn.addEventListener('click', sendPrompt);
      audioPickBtn.addEventListener('click', () => bridge && bridge.pickAudioClip && bridge.pickAudioClip());
      document.getElementById('closeBtn').addEventListener('click', () => bridge && bridge.closeWindow && bridge.closeWindow());
      document.getElementById('minBtn').addEventListener('click', () => bridge && bridge.minimizeWindow && bridge.minimizeWindow());
      pinBtn.addEventListener('click', () => bridge && bridge.togglePinned && bridge.togglePinned());
      document.getElementById('dragRegion').addEventListener('mousedown', (event) => {
        if (event.button === 0 && bridge && bridge.startWindowDrag) bridge.startWindowDrag();
      });

      inputEl.addEventListener('input', autoresizeTextarea);
      inputEl.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
          event.preventDefault();
          sendPrompt();
        }
      });

      document.addEventListener('keydown', (event) => {
        if (event.ctrlKey && event.key.toLowerCase() === 'l') {
          event.preventDefault();
          if (bridge && bridge.clearMessages) bridge.clearMessages();
        }
      });
    }

    function connectChannel() {
      new QWebChannel(qt.webChannelTransport, function(channel) {
        bridge = channel.objects.bridge;
        bridge.payload.connect(function(raw) {
          try {
            appendPayload(JSON.parse(raw));
          } catch (err) {
            console.error('Bad payload from Python', err, raw);
          }
        });
        bridge.pinStateChanged.connect(function(active) {
          pinBtn.dataset.active = active ? 'true' : 'false';
          showToast(active ? 'Pinned on top' : 'Pin disabled');
        });
        bridge.requestFocus.connect(function() {
          inputEl.focus();
        });
        bridge.showToast.connect(function(text) {
          showToast(text);
        });
        bridge.jsReady();
      });
    }

    setupButtons();
    autoresizeTextarea();
    connectChannel();
  </script>
</body>
</html>
"""


class ChatBridge(QObject):
    payload = pyqtSignal(str)
    pinStateChanged = pyqtSignal(bool)
    requestFocus = pyqtSignal()
    showToast = pyqtSignal(str)

    def __init__(self, window: "FloatingAIWindow") -> None:
        super().__init__(window)
        self.window = window
        self.pinned = True

    def emit_payload(self, data: dict) -> None:
        self.payload.emit(json.dumps(data, ensure_ascii=False))

    @pyqtSlot()
    def jsReady(self) -> None:
        self.seed_demo_messages()
        self.requestFocus.emit()
        self.pinStateChanged.emit(self.pinned)

    @pyqtSlot(str)
    def submitPrompt(self, text: str) -> None:
        clean = text.strip()
        if not clean:
            return

        if clean == "/clear":
            self.clearMessages()
            return

        self.emit_payload(
            {
                "kind": "user",
                "author": "end",
                "text": clean,
                "meta": {
                    "version": "1.0",
                    "temperature": "0.3",
                    "tokens": len(clean.split()) * 7 + 12,
                },
                "copy_text": clean,
            }
        )

        QTimer.singleShot(120, lambda: self.answer_prompt(clean))

    def answer_prompt(self, text: str) -> None:
        escaped = html.escape(text)
        rich_html = f"""
            <p><strong>Got it.</strong> This window is already using a Python↔QtWebEngine bridge, so you can now swap this fake answer for your real model call.</p>
            <h4>What this UI supports</h4>
            <ul>
              <li><strong>Trusted rich HTML</strong> in assistant messages.</li>
              <li><strong>Styled chat bubbles</strong> with chips, query pills, and copy actions.</li>
              <li><strong>Audio clips</strong> with a canvas waveform, progress fill, and duration.</li>
            </ul>
            <blockquote>Last prompt: <code>{escaped}</code></blockquote>
            <p>Wire your real inference call inside <code>answer_prompt()</code> and push the final HTML back through the bridge.</p>
        """
        self.emit_payload(
            {
                "kind": "assistant",
                "author": "Gemini 2.5 Flash style shell",
                "html": rich_html,
                "copy_text": f"What this UI supports... Last prompt: {text}",
                "sources": ["local bridge", "qtwebengine", "html renderer"],
                "query": text,
            }
        )

    @pyqtSlot()
    def clearMessages(self) -> None:
        self.emit_payload({"kind": "clear"})
        self.seed_demo_messages()
        self.showToast.emit("Chat cleared")

    @pyqtSlot()
    def pickAudioClip(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self.window,
            "Choose an audio clip",
            str(Path.home()),
            "Audio files (*.wav *.mp3 *.ogg *.opus *.m4a *.aac *.flac);;All files (*)",
        )
        if not filename:
            return
        self.emit_audio_message(
            filename, title=Path(filename).name, subtitle="Attached from local disk"
        )
        self.showToast.emit("Audio clip attached")

    def emit_audio_message(
        self, filename: str, title: str = "Audio clip", subtitle: str = "Voice note"
    ) -> None:
        url = QUrl.fromLocalFile(filename).toString()
        duration = 0.0
        try:
            if filename.lower().endswith(".wav"):
                with wave.open(filename, "rb") as wav_file:
                    frames = wav_file.getnframes()
                    rate = wav_file.getframerate() or 1
                    duration = frames / float(rate)
        except Exception:
            duration = 0.0

        self.emit_payload(
            {
                "kind": "audio",
                "author": "Voice clip",
                "title": title,
                "subtitle": subtitle,
                "audio_url": url,
                "duration": duration,
            }
        )

    def seed_demo_messages(self) -> None:
        self.emit_payload(
            {
                "kind": "user",
                "author": "end",
                "text": "what's the capital city of russia?",
                "meta": {"version": "1.0", "temperature": "0.4", "tokens": 884},
                "copy_text": "what's the capital city of russia?",
            }
        )

        self.emit_payload(
            {
                "kind": "assistant",
                "author": "Gemini 2.5 Flash",
                "html": """
                    <p>Hey there!<br>The capital city of Russia is <strong>Moscow</strong>.</p>
                    <h4>🇷🇺 More about Moscow</h4>
                    <ul>
                        <li>It is the <strong>largest city in Russia</strong> and one of the most populous metro areas in Europe.</li>
                        <li>Moscow sits on the <strong>Moskva River</strong>.</li>
                        <li>It is a huge hub for <strong>politics, economics, culture, and science</strong>.</li>
                        <li>Saint Petersburg served as capital for a time before Moscow returned in 1918.</li>
                    </ul>
                """,
                "copy_text": "The capital city of Russia is Moscow.",
                "sources": ["wikipedia.org", "britannica.com"],
                "query": "capital city of russia",
            }
        )

        demo_audio = ensure_demo_wav()
        self.emit_audio_message(
            demo_audio,
            title="Sample voice note",
            subtitle="Local WAV demo with generated waveform",
        )

    @pyqtSlot()
    def togglePinned(self) -> None:
        self.pinned = not self.pinned
        self.window.set_pinned(self.pinned)
        self.pinStateChanged.emit(self.pinned)

    @pyqtSlot()
    def minimizeWindow(self) -> None:
        self.window.showMinimized()

    @pyqtSlot()
    def closeWindow(self) -> None:
        self.window.close()

    @pyqtSlot()
    def startWindowDrag(self) -> None:
        self.window.begin_cursor_drag()

    @pyqtSlot()
    def notifyCopied(self) -> None:
        self.showToast.emit("Copied")


class FloatingAIWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._drag_offset = None

        self.setWindowTitle("hanauta-ai-window")
        self.setObjectName("hanauta-ai-window")
        self.resize(640, 760)
        self.setMinimumSize(380, 520)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Window
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.view = QWebEngineView(self)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.view.page().setBackgroundColor(QColor(0, 0, 0, 0))

        settings = self.view.settings()
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True
        )
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)

        self.channel = QWebChannel(self.view.page())
        self.bridge = ChatBridge(self)
        self.channel.registerObject("bridge", self.bridge)
        self.view.page().setWebChannel(self.channel)

        layout.addWidget(self.view)

        self._drag_timer = QTimer(self)
        self._drag_timer.setInterval(8)
        self._drag_timer.timeout.connect(self._drag_tick)

        base_url = QUrl.fromLocalFile(str(Path(tempfile.gettempdir())) + os.sep)
        self.view.setHtml(HTML_TEMPLATE, base_url)

    def begin_cursor_drag(self) -> None:
        self._drag_offset = QCursor.pos() - self.frameGeometry().topLeft()
        self._drag_timer.start()

    def _drag_tick(self) -> None:
        if not (QApplication.mouseButtons() & Qt.MouseButton.LeftButton):
            self._drag_timer.stop()
            return
        if self._drag_offset is None:
            self._drag_timer.stop()
            return
        self.move(QCursor.pos() - self._drag_offset)

    def set_pinned(self, active: bool) -> None:
        geom = self.geometry()
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Window
            | Qt.WindowType.Tool
        )
        if active:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()
        self.setGeometry(geom)


def ensure_demo_wav() -> str:
    path = Path(tempfile.gettempdir()) / "hanauta_ai_demo.wav"
    if path.exists() and path.stat().st_size > 0:
        return str(path)

    sample_rate = 24000
    duration_sec = 2.6
    total_frames = int(sample_rate * duration_sec)
    volume = 0.38

    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        for i in range(total_frames):
            t = i / sample_rate
            envelope = min(1.0, i / 1600.0) * min(1.0, (total_frames - i) / 2600.0)
            tone = (
                math.sin(2 * math.pi * 220 * t)
                + 0.45 * math.sin(2 * math.pi * 330 * t)
                + 0.25 * math.sin(2 * math.pi * 440 * t)
            )
            sample = int(max(-1.0, min(1.0, tone * volume * envelope)) * 32767)
            wav_file.writeframesraw(struct.pack("<h", sample))
        wav_file.writeframes(b"")

    return str(path)


import signal


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("hanauta-ai-window")

    def sigint_handler(signum, frame):
        app.quit()

    signal.signal(signal.SIGINT, sigint_handler)

    window = FloatingAIWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
