import React, { useEffect, useRef, useState } from 'react';
import { api } from '../api.js';
import '../copilot.css';

/** The host owns context and editor refresh only. The panel lives in Faustus. */
export default function FaustusCopilot({ deckId, lang, onChanged }) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState('');
  const container = useRef(null);
  const current = useRef({ deckId, lang, onChanged });
  const editorSelection = useRef(null);
  current.current = { deckId, lang, onChanged };

  useEffect(() => {
    editorSelection.current = null;
    const capture = event => {
      const field = event.target;
      if (!field?.closest?.('main') || !['TEXTAREA', 'INPUT'].includes(field.tagName)) return;
      const start = field.selectionStart;
      const end = field.selectionEnd;
      editorSelection.current = start !== end ? { kind: 'text', text: field.value.slice(start, end),
        field: field.getAttribute('aria-label') || field.name || field.id, start, end,
        deck_id: deckId, slide_id: new URLSearchParams(window.location.hash.split('?')[1] || '').get('slide') } : null;
    };
    for (const name of ['select', 'keyup', 'mouseup', 'focusout']) document.addEventListener(name, capture, true);
    return () => { for (const name of ['select', 'keyup', 'mouseup', 'focusout']) document.removeEventListener(name, capture, true); };
  }, [deckId]);

  useEffect(() => {
    if (!open) return;
    let disposed = false;
    let panel;
    async function mount() {
      try {
        const response = await fetch('/api/copilot/info');
        if (!response.ok) throw new Error(await response.text());
        const info = await response.json();
        await import(/* @vite-ignore */ info.panel_url);
        if (disposed) return;
        panel = document.createElement('faustus-chat');
        panel.server = window.location.origin;
        panel.locale = current.current.lang;
        panel.theme = 'auto';
        panel.onOpenSettings = () => window.open(info.settings_url, '_blank', 'noopener');
        panel.fetch = async (input, init = {}) => {
          const request = new Request(input, init);
          const url = new URL(request.url);
          const envelope = { path: url.pathname + url.search, method: request.method, headers: {} };
          for (const name of ['X-Faustus-Client-Version', 'X-Odysseus-Run-Id']) {
            const value = request.headers.get(name);
            if (value) envelope.headers[name] = value;
          }
          if (request.method !== 'GET') {
            const bytes = new Uint8Array(await request.arrayBuffer());
            const type = request.headers.get('Content-Type') || '';
            if (type.startsWith('application/json')) envelope.body = JSON.parse(new TextDecoder().decode(bytes));
            else { envelope.content_type = type; envelope.raw_body = btoa(Array.from(bytes, byte => String.fromCharCode(byte)).join('')); }
          }
          return fetch('/api/copilot/proxy', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(envelope), signal: request.signal });
        };
        panel.contextProvider = async () => {
          const { deckId: id, lang: locale } = current.current;
          const origin = { app_id: info.app_id, app_name: info.app_name, data_space_id: info.data_space_id, surface: 'editor', tool_server_id: info.tool_server_id };
          if (!id) return { origin, view: { locale } };
          const result = await api.deck(id);
          const deck = result.deck || result;
          const hash = window.location.hash.split('?')[1] || '';
          const selected = new URLSearchParams(hash).get('slide');
          const slide = deck.slides?.find(item => item.id === selected) || deck.slides?.[0];
          const editor = { deckId: id };
          window.dispatchEvent(new CustomEvent('cicero:context-request', { detail: editor }));
          return { origin, project: { external_project_id: id, title: deck.title },
            active_objects: slide ? [{ app_id: 'cicero', data_space_id: info.data_space_id, kind: 'slide', object_id: slide.id, title: slide.title, revision: slide.revision }] : [],
            selection: window.getSelection()?.toString() ? { kind: 'text', text: window.getSelection().toString() } :
              editorSelection.current?.deck_id === id && (!editorSelection.current.slide_id || editorSelection.current.slide_id === slide?.id) ? editorSelection.current : null,
            view: { locale, deck_id: id, slide_id: slide?.id, ...editor.editor, ...editor.slideEditor } };
        };
        const storageKey = 'cicero-faustus-' + info.data_space_id + '-' + (deckId || 'app');
        panel.session = localStorage.getItem(storageKey);
        panel.addEventListener('faustus:session-change', event => {
          if (event.detail.sessionId) localStorage.setItem(storageKey, event.detail.sessionId);
          else localStorage.removeItem(storageKey);
        });
        panel.addEventListener('faustus:turn-end', () => {
          current.current.onChanged?.();
          window.dispatchEvent(new Event('cicero:copilot-updated'));
        });
        container.current.replaceChildren(panel);
        await panel.loadHistory();
        setError('');
      } catch (problem) { if (!disposed) setError(String(problem.message || problem)); }
    }
    void mount();
    return () => { disposed = true; panel?.remove(); };
  }, [open, deckId]);

  return <>
    <button className="btn btn-sm cicero-copilot-toggle" type="button" aria-expanded={open} onClick={() => setOpen(!open)}>Faustus</button>
    {open && <aside className="cicero-copilot" aria-label="Faustus">
      <header><strong>Faustus · Cicero</strong><button className="btn btn-sm" type="button" onClick={() => setOpen(false)} aria-label={lang === 'es' ? 'Cerrar Faustus' : 'Close Faustus'}>×</button></header>
      {error && <p role="alert">{error}</p>}
      <div ref={container} className="cicero-copilot-content" />
    </aside>}
  </>;
}
