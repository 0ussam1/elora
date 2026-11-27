import React, { useState, useMemo } from 'react';
import { Bookmark, Trash2, ExternalLink, Calendar, User, RefreshCw, Search, AlertTriangle } from 'lucide-react';
import type { WishlistItem } from '../types';

interface WishlistViewProps {
  items: WishlistItem[];
  onRemove: (id: string) => void;
  onVerify: (id: string) => Promise<void>;
}

const VALIDATION_BADGE_MAP: Record<string, { label: string; cls: string }> = {
  VERIFIED: { label: 'Verified', cls: 'bg-emerald-950 text-emerald-400 border-emerald-800/60' },
  LIGHT_VERIFIED: { label: 'Link OK', cls: 'bg-emerald-950/70 text-emerald-300 border-emerald-800/40' },
  FAST_VERIFIED: { label: 'Fast Check', cls: 'bg-slate-800 text-sky-300 border-slate-700' },
  BROKEN_LINK: { label: 'Inaccessible / Broken', cls: 'bg-rose-950 text-rose-400 border-rose-800/60' },
  DELETED: { label: 'Deleted', cls: 'bg-rose-950 text-rose-400 border-rose-800/60' },
  SOFT_404: { label: 'Soft 404', cls: 'bg-rose-950 text-rose-400 border-rose-800/60' },
  UNREACHABLE: { label: 'Unreachable', cls: 'bg-amber-950 text-amber-400 border-amber-800/60' },
  UNCHECKED: { label: 'Unchecked', cls: 'bg-slate-800 text-slate-400 border-slate-700' },
};

export const WishlistView: React.FC<WishlistViewProps> = ({ items, onRemove, onVerify }) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [filterSource, setFilterSource] = useState('all');
  const [filterType, setFilterType] = useState('all');
  const [sortBy, setSortBy] = useState<'saved_at' | 'relevance' | 'newest' | 'oldest'>('saved_at');
  const [verifyingId, setVerifyingId] = useState<string | null>(null);

  const uniqueSources = useMemo(() => Array.from(new Set(items.map(i => i.source_name))), [items]);
  const uniqueTypes = useMemo(() => Array.from(new Set(items.map(i => i.content_type))), [items]);

  const filtered = useMemo(() => {
    const res = items.filter(it => {
      if (filterSource !== 'all' && it.source_name !== filterSource) return false;
      if (filterType !== 'all' && it.content_type !== filterType) return false;
      if (searchQuery.trim()) {
        const text = `${it.title} ${it.content_snippet || ''}`.toLowerCase();
        if (!text.includes(searchQuery.toLowerCase())) return false;
      }
      return true;
    });

    if (sortBy === 'relevance') {
      return [...res].sort((a, b) => b.saved_relevance_score - a.saved_relevance_score);
    }
    if (sortBy === 'newest' || sortBy === 'oldest') {
      const dated = res.filter(x => Boolean(x.published_at));
      const undated = res.filter(x => !x.published_at);
      dated.sort((a, b) => {
        const da = new Date(a.published_at!).getTime();
        const db = new Date(b.published_at!).getTime();
        return sortBy === 'oldest' ? da - db : db - da;
      });
      return [...dated, ...undated];
    }
    return [...res].sort((a, b) => new Date(b.saved_at).getTime() - new Date(a.saved_at).getTime());
  }, [items, filterSource, filterType, searchQuery, sortBy]);

  const handleVerify = async (id: string) => {
    setVerifyingId(id);
    try {
      await onVerify(id);
    } finally {
      setVerifyingId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-[#F5F7FC] flex items-center gap-2.5">
            <Bookmark className="w-6 h-6 text-[#18BFFF]" />
            <span>Research Wishlist</span>
          </h1>
          <p className="text-xs text-[#9BA9C0] mt-1">
            Persistent saved research items with original provenance, saved match score, and live link status.
          </p>
        </div>
        <span className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-[#10182A] border border-[#243149] text-[#18BFFF]">
          {items.length} Saved {items.length === 1 ? 'Item' : 'Items'}
        </span>
      </div>

      {/* Filters Bar */}
      <div className="bg-[#10182A] border border-[#243149] rounded-xl p-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2.5 text-xs">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-2" />
            <input
              type="text"
              placeholder="Search saved items..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="bg-slate-950 border border-slate-800 text-slate-200 placeholder-slate-500 rounded-lg pl-8 pr-3 py-1.5 focus:outline-none w-52"
            />
          </div>

          <select
            value={filterSource}
            onChange={(e) => setFilterSource(e.target.value)}
            className="bg-slate-950 border border-slate-800 text-slate-300 rounded-lg px-2.5 py-1.5 focus:outline-none"
          >
            <option value="all">All Providers</option>
            {uniqueSources.map(s => <option key={s} value={s}>{s}</option>)}
          </select>

          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="bg-slate-950 border border-slate-800 text-slate-300 rounded-lg px-2.5 py-1.5 focus:outline-none capitalize"
          >
            <option value="all">All Types</option>
            {uniqueTypes.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>

        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as any)}
          className="bg-slate-950 border border-slate-800 text-slate-300 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none"
        >
          <option value="saved_at">Sort: Recently Saved</option>
          <option value="relevance">Sort: Saved Match %</option>
          <option value="newest">Sort: Publication Date (Newest)</option>
          <option value="oldest">Sort: Publication Date (Oldest)</option>
        </select>
      </div>

      {/* Saved Items List */}
      {filtered.length === 0 ? (
        <div className="bg-[#10182A] border border-[#243149] rounded-xl p-10 text-center text-slate-400 text-sm">
          {items.length === 0
            ? 'Your Wishlist is empty. Click the Bookmark icon on any search result to save it here.'
            : 'No saved items match your current filter.'}
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((item) => {
            const scorePct = Math.round(item.saved_relevance_score * 100);
            const vBadge = VALIDATION_BADGE_MAP[item.validation_status] || VALIDATION_BADGE_MAP.UNCHECKED;
            const isBroken = ['BROKEN_LINK', 'DELETED', 'SOFT_404', 'UNREACHABLE'].includes(item.validation_status);

            return (
              <div
                key={item.id}
                className="bg-[#10182A] border border-[#243149] hover:border-slate-700 rounded-xl p-4 space-y-2.5 transition"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="space-y-1.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-sky-950 text-sky-400 border border-sky-800/50">
                        {item.source_name}
                      </span>
                      <span className="text-[10px] font-medium px-2 py-0.5 rounded bg-slate-800 text-slate-400 capitalize">
                        {item.content_type}
                      </span>
                      <span className={`text-[10px] font-semibold px-2 py-0.5 rounded border ${vBadge.cls}`}>
                        {isBroken && <AlertTriangle className="w-3 h-3 inline mr-1" />}
                        {vBadge.label}
                      </span>
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

                  <div className="flex items-center gap-2 flex-shrink-0">
                    <div className="flex items-center gap-1 text-xs font-bold text-sky-400 bg-sky-950/60 px-2 py-1 rounded-lg border border-sky-800/40">
                      <span>{scorePct}%</span>
                      <span className="text-[10px] text-slate-400 font-normal">saved match</span>
                    </div>
                  </div>
                </div>

                {item.content_snippet && (
                  <p className="text-xs text-slate-300 leading-relaxed line-clamp-3">
                    {item.content_snippet}
                  </p>
                )}

                <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-400 pt-1 border-t border-slate-800/60">
                  <div className="flex flex-wrap items-center gap-3">
                    {item.author && (
                      <span className="flex items-center gap-1 text-slate-300">
                        <User className="w-3 h-3 text-slate-500" /> {item.author}
                      </span>
                    )}
                    {item.published_at && (
                      <span className="flex items-center gap-1">
                        <Calendar className="w-3 h-3 text-slate-500" /> Published {new Date(item.published_at).toLocaleDateString()}
                      </span>
                    )}
                    <span className="text-slate-500">
                      Saved {new Date(item.saved_at).toLocaleDateString()}
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleVerify(item.id)}
                      disabled={verifyingId === item.id}
                      className="flex items-center gap-1 px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 transition cursor-pointer disabled:opacity-50"
                      title="Verify source availability"
                    >
                      <RefreshCw className={`w-3 h-3 ${verifyingId === item.id ? 'animate-spin' : ''}`} />
                      <span>Check Link</span>
                    </button>
                    <button
                      onClick={() => onRemove(item.id)}
                      className="flex items-center gap-1 px-2 py-1 rounded bg-rose-950/50 hover:bg-rose-900/60 text-rose-400 border border-rose-800/40 transition cursor-pointer"
                      title="Remove from Wishlist"
                    >
                      <Trash2 className="w-3 h-3" />
                      <span>Remove</span>
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
