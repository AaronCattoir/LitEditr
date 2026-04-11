import React, { useEffect, useRef, useState, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import { Markdown } from 'tiptap-markdown';
import Placeholder from '@tiptap/extension-placeholder';
import { Bold, Italic, Heading1, Heading2, List, ListOrdered, Quote } from 'lucide-react';
import { cn } from '../lib/utils';
import { splitOnSceneMarkers } from '../lib/manuscriptSerialize';
import type { EditorEvidenceHighlight } from '../lib/evidenceMapping';
import { EvidenceHighlight, EVIDENCE_HIGHLIGHT_UPDATE } from './extensions/evidenceHighlight';

/** Prefer HTML clipboard (e.g. Word) so block structure becomes line breaks; keeps paragraphs vs thin text/plain. */
function clipboardPlainTextPreservingLayout(event: ClipboardEvent | React.ClipboardEvent): string {
  const plain = event.clipboardData?.getData('text/plain') ?? '';
  const html = event.clipboardData?.getData('text/html');
  if (html?.trim() && typeof document !== 'undefined') {
    try {
      const div = document.createElement('div');
      div.innerHTML = html;
      const fromHtml = div.innerText ?? div.textContent ?? '';
      if (fromHtml.replace(/\s/g, '').length > 0) return fromHtml;
    } catch {
      /* fall through */
    }
  }
  return plain;
}

interface RichTextEditorProps {
  content: string;
  onChange?: (content: string) => void;
  editable?: boolean;
  onKeyDown?: (e: React.KeyboardEvent) => void;
  /** When paste text splits into multiple scenes (standalone marker lines), parent replaces sections. */
  onPasteSceneSplit?: (parts: string[]) => void;
  /** Non-persisted graph evidence highlights (Unicode offsets in `content`). */
  evidenceHighlights?: EditorEvidenceHighlight[];
  /** Fired when user clicks a highlighted range */
  onEvidenceHighlightClick?: (detail: { key: string; source: string }) => void;
}

export function RichTextEditor({
  content,
  onChange,
  editable = true,
  onKeyDown,
  onPasteSceneSplit,
  evidenceHighlights = [],
  onEvidenceHighlightClick,
}: RichTextEditorProps) {
  const pasteSplitRef = useRef(onPasteSceneSplit);
  pasteSplitRef.current = onPasteSceneSplit;

  const [bubble, setBubble] = useState<{
    left: number;
    top: number;
    title: string;
    body: string;
  } | null>(null);
  const bubbleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  const clearBubbleTimer = useCallback(() => {
    if (bubbleTimerRef.current) {
      clearTimeout(bubbleTimerRef.current);
      bubbleTimerRef.current = null;
    }
  }, []);

  const editor = useEditor({
    extensions: [
      StarterKit,
      Markdown,
      EvidenceHighlight,
      Placeholder.configure({
        placeholder: 'Write your thoughts here...',
        emptyEditorClass: 'is-editor-empty',
      }),
    ],
    content: content,
    editable: editable,
    onUpdate: ({ editor }) => {
      if (onChange) {
        const storage = editor.storage as unknown as { markdown?: { getMarkdown: () => string } };
        onChange(storage.markdown?.getMarkdown() ?? '');
      }
    },
    editorProps: {
      attributes: {
        class:
          'prose prose-lg max-w-none font-serif leading-relaxed focus:outline-none prose-headings:font-sans prose-headings:font-semibold prose-headings:tracking-tight prose-a:text-accent hover:prose-a:text-accent-hover min-h-[3rem]',
      },
      handlePaste: (_view, event) => {
        const fn = pasteSplitRef.current;
        if (!fn) return false;
        const text = clipboardPlainTextPreservingLayout(event);
        if (!text) return false;
        const parts = splitOnSceneMarkers(text);
        if (parts.length <= 1) return false;
        event.preventDefault();
        fn(parts);
        return true;
      },
      handleDOMEvents: {
        click: (_view, event) => {
          const t = event.target as HTMLElement | null;
          const el = t?.closest?.('[data-evidence-key]') as HTMLElement | null;
          if (!el || !onEvidenceHighlightClick) return false;
          const key = el.getAttribute('data-evidence-key');
          const source = el.getAttribute('data-evidence-source');
          if (key && source) onEvidenceHighlightClick({ key, source });
          return false;
        },
      },
    },
  });

  useEffect(() => {
    if (editor && editor.isEditable !== editable) {
      editor.setEditable(editable);
      if (editable) {
        setTimeout(() => editor.commands.focus('end'), 50);
      }
    }
  }, [editor, editable]);

  useEffect(() => {
    if (!editor) return;
    editor.view.dispatch(editor.state.tr.setMeta(EVIDENCE_HIGHLIGHT_UPDATE, evidenceHighlights));
  }, [editor, evidenceHighlights, content]);

  const showBubbleForElement = useCallback(
    (el: HTMLElement) => {
      const key = el.getAttribute('data-evidence-key');
      if (!key) return;
      const h = evidenceHighlights.find((x) => x.key === key);
      if (!h) return;
      const r = el.getBoundingClientRect();
      setBubble({
        left: r.left + r.width / 2,
        top: r.top - 8,
        title: h.bubbleTitle,
        body: h.bubbleBody,
      });
    },
    [evidenceHighlights],
  );

  const onEditorPointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (evidenceHighlights.length === 0) return;
      const t = e.target as HTMLElement | null;
      const el = t?.closest?.('[data-evidence-key]') as HTMLElement | null;
      // While editing, only show critic/advocate hover on highlighted spans (not on every move).
      if (editable && !el) {
        clearBubbleTimer();
        bubbleTimerRef.current = setTimeout(() => setBubble(null), 120);
        return;
      }
      clearBubbleTimer();
      if (!el) {
        bubbleTimerRef.current = setTimeout(() => setBubble(null), 120);
        return;
      }
      bubbleTimerRef.current = setTimeout(() => showBubbleForElement(el), 180);
    },
    [editable, evidenceHighlights.length, showBubbleForElement, clearBubbleTimer],
  );

  const onEditorPointerLeave = useCallback(() => {
    clearBubbleTimer();
    bubbleTimerRef.current = setTimeout(() => setBubble(null), 200);
  }, [clearBubbleTimer]);

  if (!editor) {
    return null;
  }

  return (
    <div
      ref={rootRef}
      className="flex flex-col w-full relative"
      onKeyDown={onKeyDown}
      onPointerMove={onEditorPointerMove}
      onPointerLeave={onEditorPointerLeave}
    >
      {editable && (
        <div className="flex flex-wrap items-center gap-1 mb-4 pb-2 border-b border-border">
          <ToolbarButton
            onClick={() => editor.chain().focus().toggleBold().run()}
            isActive={editor.isActive('bold')}
            icon={<Bold size={16} />}
          />
          <ToolbarButton
            onClick={() => editor.chain().focus().toggleItalic().run()}
            isActive={editor.isActive('italic')}
            icon={<Italic size={16} />}
          />
          <div className="w-px h-4 bg-border mx-1" />
          <ToolbarButton
            onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
            isActive={editor.isActive('heading', { level: 1 })}
            icon={<Heading1 size={16} />}
          />
          <ToolbarButton
            onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
            isActive={editor.isActive('heading', { level: 2 })}
            icon={<Heading2 size={16} />}
          />
          <div className="w-px h-4 bg-border mx-1" />
          <ToolbarButton
            onClick={() => editor.chain().focus().toggleBulletList().run()}
            isActive={editor.isActive('bulletList')}
            icon={<List size={16} />}
          />
          <ToolbarButton
            onClick={() => editor.chain().focus().toggleOrderedList().run()}
            isActive={editor.isActive('orderedList')}
            icon={<ListOrdered size={16} />}
          />
          <ToolbarButton
            onClick={() => editor.chain().focus().toggleBlockquote().run()}
            isActive={editor.isActive('blockquote')}
            icon={<Quote size={16} />}
          />
        </div>
      )}
      <EditorContent editor={editor} />
      {bubble &&
        createPortal(
          <div
            className="fixed z-[100] pointer-events-none max-w-[34rem] -translate-x-1/2 -translate-y-full"
            style={{ left: bubble.left, top: bubble.top }}
            role="tooltip"
          >
            <div className="rounded-xl border border-border bg-surface shadow-xl px-3 py-2 text-left max-h-[min(50vh,28rem)] flex flex-col min-w-0">
              <div className="text-[10px] font-sans font-semibold uppercase tracking-wide text-ink-light mb-1 shrink-0">
                {bubble.title}
              </div>
              <div className="text-xs font-sans text-ink leading-relaxed whitespace-pre-wrap overflow-y-auto min-h-0">
                {bubble.body}
              </div>
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}

function ToolbarButton({
  onClick,
  isActive,
  icon,
}: {
  onClick: (e: React.MouseEvent) => void;
  isActive: boolean;
  icon: React.ReactNode;
}) {
  return (
    <button
      onClick={(e) => {
        e.preventDefault();
        onClick(e);
      }}
      className={cn(
        'p-1.5 rounded-md transition-colors',
        isActive ? 'bg-overlay text-ink' : 'text-ink-light hover:bg-overlay hover:text-ink',
      )}
      type="button"
    >
      {icon}
    </button>
  );
}
