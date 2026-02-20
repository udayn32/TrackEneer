'use client';

import { FormEvent, useEffect, useRef, useState } from 'react';
import { usePathname } from 'next/navigation';
import { useSession } from 'next-auth/react';

const API_BASE = (process.env.NEXT_PUBLIC_SCHEDULER_API || 'http://localhost:5000').replace(/\/$/, '');

type Feedback = {
  variant: 'success' | 'error';
  message: string;
};

export function GlobalKnowledgeCapture() {
  const [isOpen, setIsOpen] = useState(false);
  const [note, setNote] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const { data: session, status } = useSession();
  const pathname = usePathname();
  const isAuthenticated = status === 'authenticated';

  useEffect(() => {
    if (isOpen && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen]);

  useEffect(() => {
    if (!feedback) {
      return;
    }
    const timeout = window.setTimeout(() => setFeedback(null), 4000);
    return () => window.clearTimeout(timeout);
  }, [feedback]);

  if (!isAuthenticated) {
    return null;
  }

  const closePanel = () => {
    setIsOpen(false);
    setIsSubmitting(false);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = note.trim();
    if (!trimmed) {
      setFeedback({ variant: 'error', message: 'Please share a quick note before submitting.' });
      return;
    }
    setIsSubmitting(true);
    try {
      const response = await fetch(`${API_BASE}/knowledge`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(session?.user?.email ? { 'x-user-email': session.user.email } : {}),
        },
        credentials: 'include',
        body: JSON.stringify({
          text: trimmed,
          pagePath: pathname,
        }),
      });

      const data = await response.json().catch(() => null);
      if (!response.ok) {
        const errorMessage = (data && (data.detail || data.message)) || 'We could not save that note. Please try again.';
        throw new Error(errorMessage);
      }

      const addedCount: number = data?.added ?? 0;
      const autoTasks: { taskId: string; title: string; startTime: string; endTime: string }[] =
        data?.autoCreatedTasks ?? [];

      let message = addedCount > 1 ? `Saved ${addedCount} knowledge updates.` : 'Saved to your knowledge graph.';
      if (autoTasks.length > 0) {
        const taskNames = autoTasks.map((t) => `"${t.title}"`).join(', ');
        message += ` Auto-created ${autoTasks.length} task${autoTasks.length > 1 ? 's' : ''}: ${taskNames}`;
        // Notify other components (e.g. Schedule page) to refresh their task list
        window.dispatchEvent(new CustomEvent('knowledge-tasks-created', { detail: autoTasks }));
      }

      setFeedback({ variant: 'success', message });
      setNote('');
      closePanel();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Something went wrong while saving your note.';
      setFeedback({ variant: 'error', message });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 z-40 rounded-full bg-emerald-600 px-5 py-3 text-sm font-medium text-white shadow-lg shadow-emerald-900/40 transition hover:bg-emerald-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300"
      >
        What we should know
      </button>

      {isOpen && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div className="absolute inset-0 bg-black/40" onClick={closePanel} />
          <aside className="relative h-full w-full max-w-md translate-x-0 bg-slate-900/95 p-6 text-white shadow-2xl backdrop-blur">
            <div className="flex items-start justify-between">
              <div>
                <h2 className="text-lg font-semibold">What we should know</h2>
                <p className="mt-1 text-sm text-slate-300">
                  Post your important events, deadlines, meetings or exams and we will automatically integrate it into your system.
                </p>
              </div>
              <button
                type="button"
                onClick={closePanel}
                className="ml-4 rounded-full p-2 text-slate-300 transition hover:bg-slate-800 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300"
                aria-label="Close panel"
              >
                X
              </button>
            </div>

            <form onSubmit={handleSubmit} className="mt-5 flex h-[calc(100%-4rem)] flex-col">
              <label htmlFor="knowledge-note" className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                Your note
              </label>
              <textarea
                id="knowledge-note"
                ref={textareaRef}
                value={note}
                onChange={(event) => setNote(event.target.value)}
                placeholder="eg. Project presentation on 3rd Nov at 2 PM with mentor."
                className="mt-2 h-full resize-none rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                disabled={isSubmitting}
              />
              <div className="mt-4 flex justify-end gap-3">
                <button
                  type="button"
                  onClick={closePanel}
                  className="rounded-md border border-slate-700 px-4 py-2 text-sm font-medium text-slate-300 transition hover:bg-slate-800"
                  disabled={isSubmitting}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:bg-emerald-800"
                  disabled={isSubmitting}
                >
                  {isSubmitting ? 'Saving...' : 'Submit'}
                </button>
              </div>
            </form>
          </aside>
        </div>
      )}

      {feedback && (
        <div
          className={[
            'fixed bottom-28 right-6 z-40 rounded-md px-4 py-3 text-sm shadow-lg',
            feedback.variant === 'success' ? 'bg-emerald-600 text-white' : 'bg-rose-600 text-white',
          ].join(' ')}
        >
          {feedback.message}
        </div>
      )}
    </>
  );
}
