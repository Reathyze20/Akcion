/**
 * QuickNoteInput Component
 * 
 * Allows users to quickly add notes/information to a stock's knowledge base.
 * Implements the "Brain Logic" - paste chat, add news, etc.
 * 
 * Features:
 * - Expandable input field
 * - Source selection (Chat, News, Earnings, Other)
 * - Real-time synthesis feedback
 */

import React, { useState, useRef, useEffect } from 'react';
import { MessageSquarePlus, Send, Loader2, Check, AlertTriangle, ChevronDown, X } from 'lucide-react';
import { apiClient } from '../api/client';
import type { KnowledgeSynthesisResponse } from '../api/client';

interface QuickNoteInputProps {
  ticker: string;
  onSuccess?: (result: KnowledgeSynthesisResponse) => void;
  className?: string;
  variant?: 'inline' | 'expanded';
}

const SOURCE_OPTIONS = [
  { value: 'Chat', label: '💬 Chat Discussion', icon: '💬' },
  { value: 'News', label: '📰 News/PR', icon: '📰' },
  { value: 'Earnings', label: '📊 Earnings Call', icon: '📊' },
  { value: 'Research', label: '🔍 Research Note', icon: '🔍' },
  { value: 'Personal', label: '📝 Personal Note', icon: '📝' },
];

export const QuickNoteInput: React.FC<QuickNoteInputProps> = ({
  ticker,
  onSuccess,
  className = '',
  variant = 'inline',
}) => {
  const [isExpanded, setIsExpanded] = useState(variant === 'expanded');
  const [note, setNote] = useState('');
  const [source, setSource] = useState('Chat');
  const [showSourceDropdown, setShowSourceDropdown] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<KnowledgeSynthesisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  }, [note]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowSourceDropdown(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSubmit = async () => {
    if (!note.trim() || note.length < 10) {
      setError('Note must be at least 10 characters');
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await apiClient.synthesizeKnowledge({
        ticker: ticker.toUpperCase(),
        new_info: note.trim(),
        source,
      });

      setResult(response);
      onSuccess?.(response);

      // Clear form after success
      if (response.success) {
        setTimeout(() => {
          setNote('');
          setResult(null);
          if (variant === 'inline') {
            setIsExpanded(false);
          }
        }, 3000);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to synthesize knowledge');
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      handleSubmit();
    }
  };

  const selectedSource = SOURCE_OPTIONS.find(s => s.value === source);

  // Collapsed state - just show button
  if (variant === 'inline' && !isExpanded) {
    return (
      <button
        onClick={() => setIsExpanded(true)}
        className={`flex items-center gap-2 px-3 py-2 text-sm text-text-secondary hover:text-text-primary hover:bg-surface-hover/50 rounded-lg transition-colors ${className}`}
      >
        <MessageSquarePlus className="w-4 h-4" />
        <span>Add Note</span>
      </button>
    );
  }

  return (
    <div className={`bg-surface-raised/50 border border-border rounded-xl overflow-hidden ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-border/50">
        <div className="flex items-center gap-2">
          <MessageSquarePlus className="w-4 h-4 text-accent" />
          <span className="text-sm font-medium text-text-primary">
            Add Knowledge for <span className="font-mono text-accent">{ticker}</span>
          </span>
        </div>
        {variant === 'inline' && (
          <button
            onClick={() => {
              setIsExpanded(false);
              setNote('');
              setError(null);
              setResult(null);
            }}
            className="p-1 text-text-secondary hover:text-text-primary rounded transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Textarea */}
      <div className="p-4">
        <textarea
          ref={textareaRef}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Paste chat discussion, news, or any information about this stock..."
          className="w-full bg-surface-base/50 border border-border rounded-lg px-4 py-3 text-sm text-text-primary placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 resize-none min-h-[80px]"
          disabled={loading}
        />

        {/* Controls Row */}
        <div className="flex items-center justify-between mt-3">
          {/* Source Selector */}
          <div className="relative" ref={dropdownRef}>
            <button
              onClick={() => setShowSourceDropdown(!showSourceDropdown)}
              className="flex items-center gap-2 px-3 py-1.5 text-sm bg-surface-hover/50 hover:bg-surface-hover rounded-lg transition-colors"
            >
              <span>{selectedSource?.icon}</span>
              <span className="text-text-secondary">{selectedSource?.label.split(' ').slice(1).join(' ')}</span>
              <ChevronDown className={`w-4 h-4 text-text-secondary transition-transform ${showSourceDropdown ? 'rotate-180' : ''}`} />
            </button>

            {showSourceDropdown && (
              <div className="absolute bottom-full left-0 mb-1 w-48 bg-surface-raised border border-border rounded-lg shadow-xl overflow-hidden z-10">
                {SOURCE_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    onClick={() => {
                      setSource(option.value);
                      setShowSourceDropdown(false);
                    }}
                    className={`w-full flex items-center gap-2 px-3 py-2 text-sm text-left hover:bg-surface-hover transition-colors ${
                      source === option.value ? 'bg-surface-hover/50 text-text-primary' : 'text-text-secondary'
                    }`}
                  >
                    <span>{option.icon}</span>
                    <span>{option.label.split(' ').slice(1).join(' ')}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Submit Button */}
          <div className="flex items-center gap-3">
            <span className="text-xs text-text-muted">
              {note.length} / 10 min
            </span>
            <button
              onClick={handleSubmit}
              disabled={loading || note.length < 10}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium bg-blue-600 hover:bg-blue-500 disabled:bg-surface-hover disabled:text-text-muted text-text-primary rounded-lg transition-colors"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Synthesizing...</span>
                </>
              ) : (
                <>
                  <Send className="w-4 h-4" />
                  <span>Add Knowledge</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Keyboard hint */}
        <p className="mt-2 text-xs text-text-muted">
          Press <kbd className="px-1.5 py-0.5 bg-surface-hover rounded text-text-secondary">⌘</kbd> + <kbd className="px-1.5 py-0.5 bg-surface-hover rounded text-text-secondary">Enter</kbd> to submit
        </p>
      </div>

      {/* Result/Error Display */}
      {(result || error) && (
        <div className={`px-4 py-3 border-t ${error ? 'bg-negative/10 border-negative/30' : 'bg-positive/10 border-emerald-500/30'}`}>
          {error ? (
            <div className="flex items-center gap-2 text-negative">
              <AlertTriangle className="w-4 h-4" />
              <span className="text-sm">{error}</span>
            </div>
          ) : result && (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-positive">
                <Check className="w-4 h-4" />
                <span className="text-sm font-medium">Knowledge synthesized successfully!</span>
              </div>
              
              <div className="text-sm text-text-secondary">
                <span className="text-text-muted">Action:</span> {result.action}
                {result.old_score !== null && result.new_score !== null && result.old_score !== result.new_score && (
                  <span className="ml-3">
                    <span className="text-text-muted">Score:</span>{' '}
                    <span className="text-text-secondary">{result.old_score}</span>
                    {' → '}
                    <span className={result.new_score > result.old_score ? 'text-positive' : 'text-negative'}>
                      {result.new_score}
                    </span>
                  </span>
                )}
              </div>

              {result.conflicts.length > 0 && (
                <div className="flex items-start gap-2 mt-2 p-2 bg-warning/10 rounded-lg">
                  <AlertTriangle className="w-4 h-4 text-warning flex-shrink-0 mt-0.5" />
                  <div className="text-sm text-amber-300">
                    <span className="font-medium">Conflicts detected:</span>
                    <ul className="mt-1 list-disc list-inside text-text-secondary">
                      {result.conflicts.map((conflict, i) => (
                        <li key={i}>{conflict}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}

              {result.merged_fields.length > 0 && (
                <p className="text-xs text-text-muted">
                  Merged fields: {result.merged_fields.join(', ')}
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default QuickNoteInput;


