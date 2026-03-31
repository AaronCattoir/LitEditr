import React, { useState, useEffect } from 'react';
import { BookOpen, Plus, Pencil } from 'lucide-react';
import { cn } from '../lib/utils';
import type { ChapterDoc } from '../lib/api';

interface ChapterSidebarProps {
  chapters: ChapterDoc[];
  activeChapterId: string;
  onSelect: (chapterId: string) => void;
  onAddChapter: () => void;
  onRenameChapter: (chapterId: string, title: string) => void;
  isFocusMode?: boolean;
}

export function ChapterSidebar({
  chapters,
  activeChapterId,
  onSelect,
  onAddChapter,
  onRenameChapter,
  isFocusMode = false,
}: ChapterSidebarProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');

  useEffect(() => {
    if (editingId && !chapters.some((c) => c.id === editingId)) {
      setEditingId(null);
    }
  }, [chapters, editingId]);

  const startEdit = (e: React.MouseEvent, ch: ChapterDoc) => {
    e.stopPropagation();
    setEditingId(ch.id);
    setEditValue(ch.title);
  };

  const commitEdit = () => {
    if (!editingId) return;
    const t = editValue.trim();
    if (t) onRenameChapter(editingId, t);
    setEditingId(null);
  };

  if (isFocusMode) return null;

  return (
    <aside className="w-[calc(14rem+10vw)] max-w-[min(18rem,40vw)] shrink-0 border-r border-border bg-surface/50 flex flex-col h-full min-h-0">
      <div className="px-4 py-3 border-b border-border flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-ink-light">
        <BookOpen size={14} />
        Chapters
      </div>
      <nav className="flex-1 overflow-y-auto p-2 space-y-1">
        {chapters.map((ch) => (
          <div
            key={ch.id}
            className={cn(
              'group flex items-center gap-1 rounded-lg transition-colors',
              ch.id === activeChapterId ? 'bg-accent/15' : 'hover:bg-overlay/80',
            )}
          >
            {editingId === ch.id ? (
              <input
                type="text"
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                onBlur={commitEdit}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    commitEdit();
                  }
                  if (e.key === 'Escape') setEditingId(null);
                }}
                className="flex-1 min-w-0 px-2 py-2 text-sm font-sans bg-surface rounded-md border border-accent/40 text-ink outline-none"
                autoFocus
              />
            ) : (
              <>
                <button
                  type="button"
                  onClick={() => onSelect(ch.id)}
                  className={cn(
                    'flex-1 min-w-0 text-left px-3 py-2 rounded-lg text-sm font-sans transition-colors truncate',
                    ch.id === activeChapterId ? 'text-ink font-medium' : 'text-ink-light hover:text-ink',
                  )}
                  title={ch.title}
                >
                  {ch.title || 'Untitled'}
                </button>
                <button
                  type="button"
                  onClick={(e) => startEdit(e, ch)}
                  className="shrink-0 p-1.5 mr-1 rounded-md text-ink-light opacity-0 group-hover:opacity-100 hover:text-accent hover:bg-overlay transition-opacity"
                  title="Rename chapter"
                >
                  <Pencil size={14} />
                </button>
              </>
            )}
          </div>
        ))}
      </nav>
      <div className="p-2 border-t border-border">
        <button
          type="button"
          onClick={onAddChapter}
          className="w-full flex items-center justify-center gap-2 py-2 rounded-lg text-sm text-accent hover:bg-accent/10 font-medium font-sans"
        >
          <Plus size={16} />
          Add chapter
        </button>
      </div>
    </aside>
  );
}
