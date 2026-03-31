import React, { useEffect, useRef } from 'react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import { Markdown } from 'tiptap-markdown';
import Placeholder from '@tiptap/extension-placeholder';
import { Bold, Italic, Heading1, Heading2, List, ListOrdered, Quote } from 'lucide-react';
import { cn } from '../lib/utils';
import { splitOnSceneMarkers } from '../lib/manuscriptSerialize';

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
}

export function RichTextEditor({
  content,
  onChange,
  editable = true,
  onKeyDown,
  onPasteSceneSplit,
}: RichTextEditorProps) {
  const pasteSplitRef = useRef(onPasteSceneSplit);
  pasteSplitRef.current = onPasteSceneSplit;

  const editor = useEditor({
    extensions: [
      StarterKit,
      Markdown,
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
        class: 'prose prose-lg max-w-none font-serif leading-relaxed focus:outline-none prose-headings:font-sans prose-headings:font-semibold prose-headings:tracking-tight prose-a:text-accent hover:prose-a:text-accent-hover min-h-[3rem]',
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

  if (!editor) {
    return null;
  }

  return (
    <div className="flex flex-col w-full" onKeyDown={onKeyDown}>
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
    </div>
  );
}

function ToolbarButton({ onClick, isActive, icon }: { onClick: (e: React.MouseEvent) => void, isActive: boolean, icon: React.ReactNode }) {
  return (
    <button
      onClick={(e) => {
        e.preventDefault();
        onClick(e);
      }}
      className={cn(
        "p-1.5 rounded-md transition-colors",
        isActive ? "bg-overlay text-ink" : "text-ink-light hover:bg-overlay hover:text-ink"
      )}
      type="button"
    >
      {icon}
    </button>
  );
}
