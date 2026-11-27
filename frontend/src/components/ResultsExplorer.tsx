import React, { useState, useMemo } from 'react';
import { ExternalLink, Filter, Download, User, Calendar, ThumbsUp, ThumbsDown, Flag, Bookmark } from 'lucide-react';
import type { ResearchResult } from '../types';
import { api } from '../services/api';

const VALIDATION_BADGE_MAP: Record<string, { label: string; cls: string }> = {
  VERIFIED: { label: 'Verified', cls: 'bg-emerald-950 text-emerald-400 border-emerald-800/60' },
  LIGHT_VERIFIED: { label: 'Link OK', cls: 'bg-emerald-950/70 text-emerald-300 border-emerald-800/40' },
  FAST_VERIFIED: { label: 'Fast Check', cls: 'bg-slate-800 text-sky-300 border-slate-700' },
  PENDING: { label: 'Validating...', cls: 'bg-slate-800 text-slate-400 border-slate-700' },
  PROTECTED: { label: 'Protected', cls: 'bg-amber-950/70 text-amber-300 border-amber-800/50' },
  BROKEN_LINK: { label: 'Broken Link', cls: 'bg-rose-950 text-rose-400 border-rose-800/60' },
  SOFT_404: { label: 'Soft 404', cls: 'bg-rose-950 text-rose-400 border-rose-800/60' },
  UNREACHABLE: { label: 'Unreachable', cls: 'bg-amber-950 text-amber-400 border-amber-800/60' },
  UNVERIFIED: { label: 'Unverified', cls: 'bg-slate-800 text-slate-400 border-slate-700' },
};

interface ResultsExplorerProps {
  results: ResearchResult[];
  query: string;
  onExport: (format: 'csv' | 'json') => void;
  savedUrls?: Set<string>;
  onToggleWishlist?: (item: ResearchResult) => void;
}

export const ResultsExplorer: React.FC<ResultsExplorerProps> = ({ results, onExport, savedUrls, onToggleWishlist }) => {
  const [filterSource, setFilterSource] = useState('all');
  const [filterType, setFilterType] = useState('all');
  const [filterLanguage, setFilterLanguage] = useState('all');
  const [filterVerification, setFilterVerification] = useState('all');
  const [academicOnly, setAcademicOnly] = useState(false);
  const [openAccessOnly, setOpenAccessOnly] = useState(false);
  const [minRelevance] = useState(0);
  const [searchKeyword, setSearchKeyword] = useState('');
  const [sortBy, setSortBy] = useState<'relevant' | 'newest' | 'oldest'>('relevant');
  const [feedbackSent, setFeedbackSent] = useState<Record<string, string>>({});
  const [expandedBreakdownId, setExpandedBreakdownId] = useState<string | null>(null);

  const handleFeedback = async (
    item: ResearchResult,
    type: 'relevant' | 'irrelevant' | 'wrong_version' | 'broken_link'
  ) => {
    try {
      await api.submitFeedback(item.job_id, item.id, type);
      setFeedbackSent(prev => ({ ...prev, [item.id]: type }));
    } catch {
      // Ignore silent feedback failure
    }
  };

  // Available unique sources, types, and languages (memoized)
  const uniqueSources = useMemo(
    () => Array.from(new Set(results.map(r => r.source_name))),
    [results]
  );
  const uniqueTypes = useMemo(
    () => Array.from(new Set(results.map(r => r.content_type))),
    [results]
  );
  const uniqueLanguages = useMemo(
    () => Array.from(new Set(results.map(r => r.metadata_fields?.language).filter(Boolean) as string[])),
    [results]
  );

  const filtered = useMemo(() => {
    const items = results.filter(r => {
      const meta = r.metadata_fields || {};
      if (filterSource !== 'all' && r.source_name !== filterSource) return false;
      if (filterType !== 'all' && r.content_type !== filterType) return false;
      if (filterLanguage !== 'all' && meta.language !== filterLanguage) return false;
      if (filterVerification !== 'all' && meta.validation_status !== filterVerification) return false;
      if (academicOnly && !meta.is_academic) return false;
      if (openAccessOnly && !meta.is_open_access) return false;
      if (r.relevance_score < minRelevance) return false;
      if (searchKeyword.trim()) {
        const matchText = `${r.title} ${r.content_snippet || ''}`.toLowerCase();
        if (!matchText.includes(searchKeyword.toLowerCase())) return false;
      }
      return true;
    });

    if (sortBy === 'relevant') {
      return [...items].sort((a, b) => {
        if (b.relevance_score !== a.relevance_score) return b.relevance_score - a.relevance_score;
        const dA = a.published_at ? new Date(a.published_at).getTime() : 0;
        const dB = b.published_at ? new Date(b.published_at).getTime() : 0;
        return dB - dA;
      });
    }

    // Deterministic chronological sort: undated records strictly AFTER dated records
    const dated = items.filter(x => Boolean(x.published_at));
    const undated = items.filter(x => !x.published_at);
    dated.sort((a, b) => {
      const dA = new Date(a.published_at!).getTime();
      const dB = new Date(b.published_at!).getTime();
      if (dA !== dB) return sortBy === 'oldest' ? dA - dB : dB - dA;
      return b.relevance_score - a.relevance_score;
    });
    undated.sort((a, b) => b.relevance_score - a.relevance_score);
    return [...dated, ...undated];
  }, [results, filterSource, filterType, filterLanguage, filterVerification, academicOnly, openAccessOnly, minRelevance, searchKeyword, sortBy]);

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

          <select
            value={filterLanguage}
            onChange={(e) => setFilterLanguage(e.target.value)}
            className="bg-slate-950 border border-slate-800 text-slate-300 rounded-lg px-2.5 py-1.5 focus:outline-none uppercase"
          >
            <option value="all">All Languages</option>
            {uniqueLanguages.map(lang => (
              <option key={lang} value={lang}>{lang}</option>
            ))}
          </select>

          <select
            value={filterVerification}
            onChange={(e) => setFilterVerification(e.target.value)}
            className="bg-slate-950 border border-slate-800 text-slate-300 rounded-lg px-2.5 py-1.5 focus:outline-none"
          >
            <option value="all">All Verification</option>
            <option value="VERIFIED">Verified</option>
            <option value="LIGHT_VERIFIED">Link OK</option>
            <option value="FAST_VERIFIED">Fast Check</option>
            <option value="BROKEN_LINK">Broken Link</option>
          </select>

          <label className="flex items-center gap-1.5 text-slate-300 cursor-pointer select-none px-1.5">
            <input
              type="checkbox"
              checked={academicOnly}
              onChange={(e) => setAcademicOnly(e.target.checked)}
              className="accent-sky-500 rounded"
            />
            <span>Academic</span>
          </label>

          <label className="flex items-center gap-1.5 text-slate-300 cursor-pointer select-none px-1.5">
            <input
              type="checkbox"
              checked={openAccessOnly}
              onChange={(e) => setOpenAccessOnly(e.target.checked)}
              className="accent-emerald-500 rounded"
            />
            <span>Open Access</span>
          </label>

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
            onChange={(e) => setSortBy(e.target.value as 'relevant' | 'newest' | 'oldest')}
            className="bg-slate-950 border border-slate-800 text-slate-300 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none"
          >
            <option value="relevant">Sort: Most Relevant</option>
            <option value="newest">Sort: Newest First</option>
            <option value="oldest">Sort: Oldest First</option>
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
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-sky-950 text-sky-400 border border-sky-800/50">
                        {item.source_name}
                      </span>
                      <span className="text-[10px] font-medium px-2 py-0.5 rounded bg-slate-800 text-slate-400 capitalize">
                        {item.content_type}
                      </span>
                      {item.metadata_fields?.language && (
                        <span className="text-[10px] font-medium uppercase px-1.5 py-0.5 rounded bg-slate-800/80 text-slate-300 border border-slate-700/60">
                          {item.metadata_fields.language}
                        </span>
                      )}
                      {item.metadata_fields?.source_quality_label && (
                        <span className="text-[10px] font-medium px-2 py-0.5 rounded bg-indigo-950/60 text-indigo-300 border border-indigo-800/40">
                          {item.metadata_fields.source_quality_label}
                        </span>
                      )}
                      {(() => {
                        const vStatus = item.metadata_fields?.validation_status;
                        const badge = vStatus ? VALIDATION_BADGE_MAP[vStatus] : undefined;
                        if (!badge) return null;
                        return (
                          <span className={`text-[10px] font-semibold px-2 py-0.5 rounded border ${badge.cls}`}>
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

                  {/* Relevance Badge & Bookmark */}
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {onToggleWishlist && (
                      <button
                        onClick={() => onToggleWishlist(item)}
                        title={savedUrls?.has(item.source_url) ? 'Remove from Wishlist' : 'Save to Wishlist'}
                        className={`p-1.5 rounded-lg border transition cursor-pointer ${
                          savedUrls?.has(item.source_url)
                            ? 'bg-[#18BFFF]/15 border-[#18BFFF]/50 text-[#18BFFF]'
                            : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-sky-400 hover:border-slate-700'
                        }`}
                      >
                        <Bookmark className={`w-3.5 h-3.5 ${savedUrls?.has(item.source_url) ? 'fill-current' : ''}`} />
                      </button>
                    )}
                    <button
                      onClick={() => setExpandedBreakdownId(expandedBreakdownId === item.id ? null : item.id)}
                      title="Inspect match score breakdown"
                      className="flex items-center gap-1 text-xs font-bold text-sky-400 bg-sky-950/60 hover:bg-sky-950 px-2 py-1 rounded-lg border border-sky-800/40 cursor-pointer transition"
                    >
                      <span>{scorePercent}%</span>
                      <span className="text-[10px] text-slate-400 font-normal">match</span>
                    </button>
                  </div>
                </div>

                {/* Expandable Match Breakdown */}
                {expandedBreakdownId === item.id && item.metadata_fields?.match_breakdown && (
                  <div className="bg-slate-950/70 border border-slate-800/80 rounded-lg p-2.5 text-[11px] text-slate-300 flex flex-wrap gap-3">
                    <span>Title: <strong>{item.metadata_fields.match_breakdown.title}%</strong></span>
                    <span>Description: <strong>{item.metadata_fields.match_breakdown.description}%</strong></span>
                    <span>Topic/Qualifiers: <strong>{item.metadata_fields.match_breakdown.topic}%</strong></span>
                    <span>Semantic/BM25: <strong>{item.metadata_fields.match_breakdown.semantic}%</strong></span>
                    {item.metadata_fields.match_breakdown.entity_version !== null && (
                      <span>Entity/Version: <strong>{item.metadata_fields.match_breakdown.entity_version}%</strong></span>
                    )}
                  </div>
                )}

                {/* Excerpt */}
                <p className="text-xs text-slate-300 leading-relaxed line-clamp-3">
                  {item.content_snippet || 'No excerpt available.'}
                </p>

                {/* Match Evidence & Provenance */}
                {Array.isArray(item.metadata_fields?.match_reasons) && item.metadata_fields.match_reasons.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-slate-400">
                    <span className="text-slate-500 font-medium">Match signals:</span>
                    {item.metadata_fields.match_reasons.map((reason: string, rIdx: number) => (
                      <span key={rIdx} className="px-1.5 py-0.5 rounded bg-slate-800/60 text-slate-300 border border-slate-700/40">
                        {reason}
                      </span>
                    ))}
                  </div>
                )}

                {/* Meta details */}
                <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-400 pt-1 border-t border-slate-800/60">
                  <div className="flex items-center gap-3">
                    {item.author && (
                      <span className="flex items-center gap-1 text-slate-300">
                        <User className="w-3 h-3 text-slate-500" /> {item.author}
                      </span>
                    )}
                    {item.published_at ? (
                      <span className="flex items-center gap-1">
                        <Calendar className="w-3 h-3 text-slate-500" /> {new Date(item.published_at).toLocaleDateString()}
                      </span>
                    ) : (
                      <span className="text-slate-500 italic">Date unknown</span>
                    )}
                  </div>

                  <div className="flex items-center gap-3">
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

                    {/* Lightweight Feedback Controls */}
                    <div className="flex items-center gap-1.5">
                      {feedbackSent[item.id] ? (
                        <span className="text-[10px] text-emerald-400 px-1.5 py-0.5 rounded bg-emerald-950/60 border border-emerald-800/40">
                          Feedback: {feedbackSent[item.id].replace('_', ' ')}
                        </span>
                      ) : (
                        <>
                          <button
                            onClick={() => handleFeedback(item, 'relevant')}
                            title="Mark Relevant"
                            className="p-1 rounded hover:bg-slate-800 text-slate-500 hover:text-emerald-400 transition cursor-pointer"
                          >
                            <ThumbsUp className="w-3 h-3" />
                          </button>
                          <button
                            onClick={() => handleFeedback(item, 'irrelevant')}
                            title="Mark Irrelevant"
                            className="p-1 rounded hover:bg-slate-800 text-slate-500 hover:text-rose-400 transition cursor-pointer"
                          >
                            <ThumbsDown className="w-3 h-3" />
                          </button>
                          <button
                            onClick={() => handleFeedback(item, 'wrong_version')}
                            title="Report Wrong Version / Issue"
                            className="p-1 rounded hover:bg-slate-800 text-slate-500 hover:text-amber-400 transition cursor-pointer"
                          >
                            <Flag className="w-3 h-3" />
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
