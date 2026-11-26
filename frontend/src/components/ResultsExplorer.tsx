import React, { useState } from 'react';
import { ExternalLink, Filter, Download, User, Calendar, ShieldCheck, ShieldAlert, AlertTriangle, Eye, EyeOff } from 'lucide-react';
import type { ResearchResult, ValidationStatus } from '../types';

const EXCLUDED_STATUSES = new Set<ValidationStatus>([
  'INACCESSIBLE',
  'DELETED',
  'NOT_FOUND',
  'MISMATCH',
]);

const STATUS_BADGE: Record<ValidationStatus, { label: string; cls: string }> = {
  VERIFIED: { label: 'Verified', cls: 'bg-emerald-950/80 text-emerald-400 border-emerald-800/60' },
  PARTIALLY_VERIFIED: { label: 'Partially Verified', cls: 'bg-amber-950/80 text-amber-300 border-amber-800/60' },
  INACCESSIBLE: { label: 'Inaccessible', cls: 'bg-orange-950/80 text-orange-400 border-orange-800/60' },
  DELETED: { label: 'Deleted', cls: 'bg-rose-950/80 text-rose-400 border-rose-800/60' },
  NOT_FOUND: { label: 'Not Found', cls: 'bg-rose-950/80 text-rose-400 border-rose-800/60' },
  MISMATCH: { label: 'Content Mismatch', cls: 'bg-rose-950/80 text-rose-400 border-rose-800/60' },
  UNCHECKED: { label: 'Unchecked', cls: 'bg-slate-800 text-slate-400 border-slate-700' },
};

interface ResultsExplorerProps {
  results: ResearchResult[];
  query: string;
  onExport: (format: 'csv' | 'json') => void;
}

export const ResultsExplorer: React.FC<ResultsExplorerProps> = ({ results, onExport }) => {
  const [filterSource, setFilterSource] = useState('all');
  const [filterType, setFilterType] = useState('all');
  const [minRelevance] = useState(0);
  const [searchKeyword, setSearchKeyword] = useState('');
  const [sortBy, setSortBy] = useState<'relevance' | 'date'>('relevance');
  const [showExcluded, setShowExcluded] = useState(false);

  // Available unique sources and types
  const uniqueSources = Array.from(new Set(results.map(r => r.source_name)));
  const uniqueTypes = Array.from(new Set(results.map(r => r.content_type)));
  const excludedCount = results.filter(r => r.validation_status && EXCLUDED_STATUSES.has(r.validation_status)).length;

  const filtered = results.filter(r => {
    const vStatus = r.validation_status || 'UNCHECKED';
    if (!showExcluded && EXCLUDED_STATUSES.has(vStatus)) return false;
    if (filterSource !== 'all' && r.source_name !== filterSource) return false;
    if (filterType !== 'all' && r.content_type !== filterType) return false;
    if (r.relevance_score < minRelevance) return false;
    if (searchKeyword.trim()) {
      const matchText = `${r.title} ${r.content_snippet || ''}`.toLowerCase();
      if (!matchText.includes(searchKeyword.toLowerCase())) return false;
    }
    return true;
  }).sort((a, b) => {
    const prio: Record<string, number> = { VERIFIED: 0, PARTIALLY_VERIFIED: 1, UNCHECKED: 2 };
    const pa = prio[a.validation_status || 'UNCHECKED'] ?? 3;
    const pb = prio[b.validation_status || 'UNCHECKED'] ?? 3;
    if (pa !== pb) return pa - pb;
    if (sortBy === 'relevance') return b.relevance_score - a.relevance_score;
    const dateA = a.published_at ? new Date(a.published_at).getTime() : 0;
    const dateB = b.published_at ? new Date(b.published_at).getTime() : 0;
    return dateB - dateA;
  });

  return (
    <div className="space-y-4">
      {/* Filters & Export Header */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-wrap items-center justify-between gap-3 shadow-md">
        <div className="flex flex-wrap items-center gap-2.5 text-xs">
          <div className="flex items-center gap-1.5 text-slate-400 font-semibold mr-1">
            <Filter className="w-3.5 h-3.5 text-sky-400" />
            <span>Filter:</span>
          </div>

          <select
            value={filterSource}
            onChange={(e) => setFilterSource(e.target.value)}
            className="bg-slate-950 border border-slate-800 text-slate-300 rounded-lg px-2.5 py-1.5 focus:outline-none"
          >
            <option value="all">All Sources ({results.length})</option>
            {uniqueSources.map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>

          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="bg-slate-950 border border-slate-800 text-slate-300 rounded-lg px-2.5 py-1.5 focus:outline-none capitalize"
          >
            <option value="all">All Content Types</option>
            {uniqueTypes.map(t => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>

          <input
            type="text"
            placeholder="Search within results..."
            value={searchKeyword}
            onChange={(e) => setSearchKeyword(e.target.value)}
            className="bg-slate-950 border border-slate-800 text-slate-200 placeholder-slate-500 rounded-lg px-3 py-1.5 focus:outline-none w-44"
          />
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2">
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as any)}
            className="bg-slate-950 border border-slate-800 text-slate-300 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none"
          >
            <option value="relevance">Sort: Highest Relevance</option>
            <option value="date">Sort: Most Recent</option>
          </select>

          <button
            onClick={() => onExport('csv')}
            className="flex items-center gap-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs px-3 py-1.5 rounded-lg border border-slate-700 transition cursor-pointer"
          >
            <Download className="w-3.5 h-3.5 text-sky-400" />
            <span>CSV</span>
          </button>

          <button
            onClick={() => onExport('json')}
            className="flex items-center gap-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs px-3 py-1.5 rounded-lg border border-slate-700 transition cursor-pointer"
          >
            <Download className="w-3.5 h-3.5 text-emerald-400" />
            <span>JSON</span>
          </button>

          {excludedCount > 0 && (
            <button
              onClick={() => setShowExcluded(prev => !prev)}
              className="flex items-center gap-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs px-3 py-1.5 rounded-lg border border-slate-700 transition cursor-pointer"
              title="Toggle excluded (inaccessible, deleted, 404, or mismatched) results"
            >
              {showExcluded ? <EyeOff className="w-3.5 h-3.5 text-amber-400" /> : <Eye className="w-3.5 h-3.5 text-slate-400" />}
              <span>{showExcluded ? 'Hide' : 'Show'} excluded ({excludedCount})</span>
            </button>
          )}
        </div>
      </div>

      {/* Results List */}
      <div className="space-y-3">
        {filtered.length === 0 ? (
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center text-slate-500">
            No results match the current filters.
          </div>
        ) : (
          filtered.map((item) => {
            const scorePercent = Math.round(item.relevance_score * 100);
            return (
              <div 
                key={item.id}
                className="bg-slate-900/90 border border-slate-800/80 hover:border-slate-700 rounded-xl p-4 transition shadow-sm space-y-2.5"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-sky-950 text-sky-400 border border-sky-800/50">
                        {item.source_name}
                      </span>
                      <span className="text-[10px] font-medium px-2 py-0.5 rounded bg-slate-800 text-slate-400 capitalize">
                        {item.content_type}
                      </span>
                      {(() => {
                        const vStatus = item.validation_status || 'UNCHECKED';
                        const badge = STATUS_BADGE[vStatus] || STATUS_BADGE.UNCHECKED;
                        const Icon = vStatus === 'VERIFIED' ? ShieldCheck : vStatus === 'PARTIALLY_VERIFIED' ? AlertTriangle : ShieldAlert;
                        return (
                          <span
                            title={item.validation_reason || `Status: ${vStatus}${item.validation_method ? ` (${item.validation_method})` : ''}`}
                            className={`inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded border ${badge.cls}`}
                          >
                            <Icon className="w-3 h-3" />
                            {badge.label}
                          </span>
                        );
                      })()}
                      {item.is_duplicate && (
                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-amber-950 text-amber-400 border border-amber-800">
                          Near Duplicate
                        </span>
                      )}
                    </div>
                    <a
                      href={item.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-base font-semibold text-slate-100 hover:text-sky-400 flex items-center gap-1.5 transition leading-snug group"
                    >
                      <span>{item.title}</span>
                      <ExternalLink className="w-3.5 h-3.5 text-slate-500 group-hover:text-sky-400 flex-shrink-0" />
                    </a>
                  </div>

                  {/* Relevance Badge */}
                  <div className="flex flex-col items-end flex-shrink-0">
                    <div className="flex items-center gap-1 text-xs font-bold text-sky-400 bg-sky-950/60 px-2 py-1 rounded-lg border border-sky-800/40">
                      <span>{scorePercent}%</span>
                      <span className="text-[10px] text-slate-400 font-normal">match</span>
                    </div>
                  </div>
                </div>

                {/* Excerpt */}
                <p className="text-xs text-slate-300 leading-relaxed line-clamp-3">
                  {item.content_snippet || 'No excerpt available.'}
                </p>

                {/* Meta details */}
                <div className="flex flex-wrap items-center justify-between text-[11px] text-slate-400 pt-1 border-t border-slate-800/60">
                  <div className="flex items-center gap-3">
                    {item.author && (
                      <span className="flex items-center gap-1 text-slate-300">
                        <User className="w-3 h-3 text-slate-500" /> {item.author}
                      </span>
                    )}
                    {item.published_at && (
                      <span className="flex items-center gap-1">
                        <Calendar className="w-3 h-3 text-slate-500" /> {new Date(item.published_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>

                  {/* Engagement indicators */}
                  {item.engagement_metrics && Object.keys(item.engagement_metrics).length > 0 && (
                    <div className="flex items-center gap-2 text-slate-400">
                      {item.engagement_metrics.points !== undefined && (
                        <span>▲ {item.engagement_metrics.points} pts</span>
                      )}
                      {item.engagement_metrics.comments !== undefined && (
                        <span>💬 {item.engagement_metrics.comments} comments</span>
                      )}
                      {item.engagement_metrics.reactions_total !== undefined && (
                        <span>👍 {item.engagement_metrics.reactions_total} reactions</span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
