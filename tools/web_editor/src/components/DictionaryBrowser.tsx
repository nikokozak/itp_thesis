import { useMemo, useState } from 'react';
import type { StackEffectDatabase } from '../analysis/types';
import type { WordEntry } from '../engine/types';
import { useUiStore } from '../store/ui-store';

interface DictionaryBrowserProps {
  words: WordEntry[];
  effects: StackEffectDatabase;
  selectedWord?: string;
  onSelectWord: (word: string) => void;
  compact?: boolean;
}

type SortMode = 'definition' | 'alphabetical' | 'frequency';

const PAGE_SIZE = 40;

function effectSummary(effect?: { inputs: number; outputs: number }): string {
  if (!effect) {
    return '?';
  }
  return `${effect.inputs} -> ${effect.outputs}`;
}

function modulePrefix(name: string): string | undefined {
  const dot = name.indexOf('.');
  if (dot <= 0) {
    return undefined;
  }
  return name.slice(0, dot);
}

export function DictionaryBrowser({ words, effects, selectedWord, onSelectWord, compact }: DictionaryBrowserProps) {
  const query = useUiStore((state) => state.dictionaryQuery);
  const typeFilter = useUiStore((state) => state.dictionaryFilterType);
  const arityFilter = useUiStore((state) => state.dictionaryArityFilter);
  const setQuery = useUiStore((state) => state.setDictionaryQuery);
  const setTypeFilter = useUiStore((state) => state.setDictionaryTypeFilter);
  const setArityFilter = useUiStore((state) => state.setDictionaryArityFilter);

  const [sortMode, setSortMode] = useState<SortMode>('definition');
  const [showFullList, setShowFullList] = useState(false);
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  const filtered = useMemo(() => {
    const normalizedQuery = query.trim().toUpperCase();
    let result = words.filter((word) => {
      if (normalizedQuery && !word.name.toUpperCase().includes(normalizedQuery)) {
        return false;
      }

      if (typeFilter !== 'all' && word.type !== typeFilter) {
        return false;
      }

      if (arityFilter) {
        const effect = effects[word.name.toUpperCase()];
        if (!effect) {
          return false;
        }
        if (effect.inputs !== arityFilter.inputs || effect.outputs !== arityFilter.outputs) {
          return false;
        }
      }

      return true;
    });

    if (sortMode === 'alphabetical') {
      result = [...result].sort((a, b) => a.name.localeCompare(b.name));
    } else if (sortMode === 'frequency') {
      result = [...result].sort((a, b) => b.callCount - a.callCount);
    } else {
      result = [...result].sort((a, b) => a.definitionOrder - b.definitionOrder);
    }

    return result;
  }, [arityFilter, effects, query, sortMode, typeFilter, words]);

  const hasActiveFilters = Boolean(query.trim()) || typeFilter !== 'all' || Boolean(arityFilter);
  const discoveryMode = !showFullList && !hasActiveFilters;

  const recentUserWords = useMemo(() => {
    return words
      .filter((word) => word.type !== 'primitive')
      .sort((a, b) => b.definitionOrder - a.definitionOrder)
      .slice(0, 16);
  }, [words]);

  const groupedModules = useMemo(() => {
    const groups = new Map<string, number>();
    for (const word of words) {
      const prefix = modulePrefix(word.name);
      if (!prefix) {
        continue;
      }
      groups.set(prefix, (groups.get(prefix) ?? 0) + 1);
    }

    return Array.from(groups.entries()).sort((a, b) => b[1] - a[1]);
  }, [words]);

  const visibleWords = filtered.slice(0, visibleCount);

  const countByType = useMemo(() => {
    return {
      all: words.length,
      primitive: words.filter((word) => word.type === 'primitive').length,
      compiled: words.filter((word) => word.type === 'compiled').length,
      constant: words.filter((word) => word.type === 'constant').length,
      variable: words.filter((word) => word.type === 'variable').length,
      value: words.filter((word) => word.type === 'value').length,
    };
  }, [words]);

  if (compact) {
    return (
      <div className="dictionary-pane dictionary-compact">
        <div className="dictionary-controls">
          <input
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setVisibleCount(PAGE_SIZE);
            }}
            placeholder="Search words..."
            aria-label="Search dictionary"
          />
        </div>
        <div className="dictionary-list compact-list">
          {filtered.slice(0, 20).map((word) => {
            const effect = effects[word.name.toUpperCase()];
            return (
              <button
                type="button"
                key={`${word.name}-${word.definitionOrder}`}
                className={`dictionary-item ${selectedWord?.toUpperCase() === word.name.toUpperCase() ? 'is-selected' : ''}`}
                onClick={() => onSelectWord(word.name)}
              >
                <span className="word-name">{word.name}</span>
                <span className="word-meta">{word.type}</span>
                <span className="word-meta">{effectSummary(effect)}</span>
              </button>
            );
          })}
          {filtered.length === 0 ? <div className="muted">No words match.</div> : null}
          {filtered.length > 20 ? (
            <div className="hint" style={{ padding: '0.2rem 0.4rem' }}>
              {filtered.length - 20} more...
            </div>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div className="dictionary-pane">
      <div className="panel-header">
        <span>Dictionary Browser</span>
        <span className="hint">Discovery mode avoids dumping all words by default.</span>
      </div>

      <div className="dictionary-controls">
        <input
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setVisibleCount(PAGE_SIZE);
          }}
          placeholder="Search words..."
          aria-label="Search dictionary"
        />

        <div className="dictionary-row">
          <select
            value={typeFilter}
            onChange={(event) => {
              setTypeFilter(event.target.value as typeof typeFilter);
              setVisibleCount(PAGE_SIZE);
            }}
          >
            <option value="all">All types ({countByType.all})</option>
            <option value="primitive">Primitives ({countByType.primitive})</option>
            <option value="compiled">Compiled ({countByType.compiled})</option>
            <option value="constant">Constants ({countByType.constant})</option>
            <option value="variable">Variables ({countByType.variable})</option>
            <option value="value">Values ({countByType.value})</option>
          </select>

          <select value={sortMode} onChange={(event) => setSortMode(event.target.value as SortMode)}>
            <option value="definition">Definition order</option>
            <option value="alphabetical">Alphabetical</option>
            <option value="frequency">Frequency</option>
          </select>
        </div>

        <div className="arity-filter-row">
          <label>Arity:</label>
          <button type="button" onClick={() => setArityFilter(undefined)}>
            Any
          </button>
          <button type="button" onClick={() => setArityFilter({ inputs: 2, outputs: 1 })}>
            2 -&gt; 1
          </button>
          <button type="button" onClick={() => setArityFilter({ inputs: 1, outputs: 1 })}>
            1 -&gt; 1
          </button>
          <button
            type="button"
            onClick={() => {
              setShowFullList(!showFullList);
              setVisibleCount(PAGE_SIZE);
            }}
          >
            {showFullList ? 'Discovery Mode' : 'Browse All'}
          </button>
        </div>
      </div>

      {discoveryMode ? (
        <div className="dictionary-discovery">
          <div className="dictionary-section">
            <strong>Quick Categories</strong>
            <div className="chip-row">
              <button type="button" onClick={() => setTypeFilter('compiled')}>
                Compiled ({countByType.compiled})
              </button>
              <button type="button" onClick={() => setTypeFilter('primitive')}>
                Primitives ({countByType.primitive})
              </button>
              <button type="button" onClick={() => setTypeFilter('variable')}>
                Variables ({countByType.variable})
              </button>
              <button type="button" onClick={() => setTypeFilter('constant')}>
                Constants ({countByType.constant})
              </button>
            </div>
          </div>

          <div className="dictionary-section">
            <strong>Recent User Words</strong>
            <div className="dictionary-list compact-list">
              {recentUserWords.length === 0 ? <div className="muted">No user definitions yet.</div> : null}
              {recentUserWords.map((word) => (
                <button
                  type="button"
                  key={`${word.name}-${word.definitionOrder}`}
                  className={`dictionary-item ${selectedWord?.toUpperCase() === word.name.toUpperCase() ? 'is-selected' : ''}`}
                  onClick={() => onSelectWord(word.name)}
                >
                  <span className="word-name">{word.name}</span>
                  <span className="word-meta">{word.type}</span>
                  <span className="word-meta">{effectSummary(effects[word.name.toUpperCase()])}</span>
                </button>
              ))}
            </div>
          </div>

          {groupedModules.length > 0 ? (
            <div className="dictionary-section">
              <strong>Module-Like Groups</strong>
              <div className="chip-row">
                {groupedModules.slice(0, 8).map(([group, count]) => (
                  <button
                    type="button"
                    key={group}
                    onClick={() => {
                      setQuery(`${group}.`);
                      setVisibleCount(PAGE_SIZE);
                    }}
                  >
                    {group} ({count})
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      ) : (
        <>
          <div className="dictionary-list">
            {visibleWords.map((word) => {
              const effect = effects[word.name.toUpperCase()];
              return (
                <button
                  type="button"
                  key={`${word.name}-${word.definitionOrder}`}
                  className={`dictionary-item ${selectedWord?.toUpperCase() === word.name.toUpperCase() ? 'is-selected' : ''}`}
                  onClick={() => onSelectWord(word.name)}
                >
                  <span className="word-name">{word.name}</span>
                  <span className="word-meta">{word.type}</span>
                  <span className="word-meta">{effectSummary(effect)}</span>
                </button>
              );
            })}
            {visibleWords.length === 0 ? <div className="muted">No words match current filters.</div> : null}
          </div>

          <div className="dictionary-footer">
            <span>
              Showing {visibleWords.length} / {filtered.length}
            </span>
            <div className="dictionary-row">
              {visibleCount < filtered.length ? (
                <button type="button" onClick={() => setVisibleCount((count) => count + PAGE_SIZE)}>
                  Show More
                </button>
              ) : null}
              <button
                type="button"
                onClick={() => {
                  setVisibleCount(PAGE_SIZE);
                  setQuery('');
                  setTypeFilter('all');
                  setArityFilter(undefined);
                }}
              >
                Reset Filters
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
