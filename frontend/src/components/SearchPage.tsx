import React, { useState } from 'react';
import { Search, Sliders, Zap, Sparkles, CheckCircle2 } from 'lucide-react';
import type { SourceInfo } from '../types';

interface SearchPageProps {
  sources: SourceInfo[];
  onSubmit: (params: {
    query: string;
    mode: string;
    sources: string[];
    limit_per_source: number;
  }) => void;
  isLoading: boolean;
  initialQuery?: string;
  initialMode?: string;
}

export const SearchPage: React.FC<SearchPageProps> = ({ 
  sources, 
  onSubmit, 
  isLoading,
  initialQuery = '',
  initialMode = 'general'
}) => {
  const [query, setQuery] = useState(initialQuery);
  const [mode, setMode] = useState(initialMode);
  const [selectedSources, setSelectedSources] = useState<string[]>(
    sources.filter(s => s.health_status === 'operational' || s.health_status === 'connected').map(s => s.id)
  );
  const [limit, setLimit] = useState(15);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const toggleSource = (id: string) => {
    setSelectedSources(prev => 
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    );
  };

  const selectAllSources = () => {
    setSelectedSources(sources.map(s => s.id));
  };

  const selectNoneSources = () => {
    setSelectedSources([]);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || isLoading) return;
    onSubmit({
      query: query.trim(),
      mode,
      sources: selectedSources,
      limit_per_source: limit
    });
  };

  const sampleQueries = [
    "Find recurring problems people experience with free AI tools",
    "Research the limitations of current data-cleaning tools",
    "Find unresolved issues related to Python machine learning libraries",
    "Discover potential SaaS ideas based on real user complaints"
  ];

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="text-center space-y-2 py-2">
        <h1 className="text-3xl font-extrabold text-[#F5F7FC] tracking-tight">
          Deep Multi-Source Investigation
        </h1>
        <p className="text-[#9BA9C0] text-sm max-w-xl mx-auto">
          Query across open web discussions, issue trackers, research repositories, and public knowledge bases simultaneously.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="bg-[#10182A] border border-[#243149] rounded-2xl p-6 sm:p-7 shadow-2xl space-y-5">
        {/* Main Search Input */}
        <div className="relative">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search the web, repositories, research papers, and more..."
            className="w-full bg-[#070B18] border border-[#243149] focus:border-[#18BFFF] rounded-xl px-5 py-4 pl-12 text-[#F5F7FC] placeholder-[#9BA9C0]/60 focus:outline-none focus:ring-2 focus:ring-[#18BFFF]/20 text-base transition-colors"
            disabled={isLoading}
            autoFocus
          />
          <Search className="w-5 h-5 text-[#9BA9C0] absolute left-4 top-4.5" />
        </div>

        {/* Query Suggestions */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-[#9BA9C0] flex items-center gap-1 font-medium">
            <Sparkles className="w-3.5 h-3.5 text-[#18BFFF]" /> Suggestions:
          </span>
          {sampleQueries.map((sq, i) => (
            <button
              key={i}
              type="button"
              onClick={() => setQuery(sq)}
              className="text-xs text-[#9BA9C0] hover:text-[#18BFFF] bg-[#070B18] hover:bg-[#18BFFF]/10 border border-[#243149] hover:border-[#18BFFF]/40 rounded-lg px-2.5 py-1 transition cursor-pointer"
            >
              {sq}
            </button>
          ))}
        </div>

        {/* Research Modes */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2">
          {[
            { id: 'general', title: 'General Research', desc: 'Balanced discovery across all active web sources & media' },
            { id: 'technical', title: 'Technical Research', desc: 'Prioritizes GitHub code, StackOverflow, Kaggle, & arXiv' },
            { id: 'problem_discovery', title: 'Problem Discovery', desc: 'Focuses on user pain points, bug tickets, & real complaints' }
          ].map((m) => {
            const isSelected = mode === m.id;
            return (
              <div
                key={m.id}
                onClick={() => setMode(m.id)}
                className={`p-3.5 rounded-xl border cursor-pointer transition select-none ${
                  isSelected
                    ? 'bg-[#18BFFF]/10 border-[#18BFFF] text-[#F5F7FC] shadow-lg shadow-[#18BFFF]/5'
                    : 'bg-[#070B18] border-[#243149] text-[#9BA9C0] hover:border-[#324466]'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className={`font-semibold text-xs ${isSelected ? 'text-[#18BFFF]' : 'text-[#F5F7FC]'}`}>
                    {m.title}
                  </div>
                  {isSelected && <CheckCircle2 className="w-3.5 h-3.5 text-[#18BFFF]" />}
                </div>
                <div className="text-[11px] text-[#9BA9C0] mt-1 leading-relaxed">
                  {m.desc}
                </div>
              </div>
            );
          })}
        </div>

        {/* Advanced Filters Toggle */}
        <div className="pt-2 border-t border-[#243149] flex items-center justify-between">
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex items-center gap-2 text-xs font-medium text-[#9BA9C0] hover:text-[#F5F7FC] transition cursor-pointer"
          >
            <Sliders className="w-4 h-4 text-[#18BFFF]" />
            <span>{showAdvanced ? 'Hide Advanced Options' : 'Configure Sources & Limits'}</span>
          </button>

          <div className="text-xs text-[#9BA9C0]">
            <span className="text-[#18BFFF] font-semibold">{selectedSources.length}</span> of {sources.length} sources enabled
          </div>
        </div>

        {/* Advanced Options Panel */}
        {showAdvanced && (
          <div className="space-y-4 pt-3 bg-[#070B18]/70 p-4 rounded-xl border border-[#243149]">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-[#F5F7FC]">Active Connectors ({sources.length})</label>
              <div className="flex items-center gap-2 text-[11px]">
                <button
                  type="button"
                  onClick={selectAllSources}
                  className="text-[#18BFFF] hover:underline cursor-pointer"
                >
                  Select All
                </button>
                <span className="text-[#243149]">|</span>
                <button
                  type="button"
                  onClick={selectNoneSources}
                  className="text-[#9BA9C0] hover:text-[#F5F7FC] cursor-pointer"
                >
                  Clear
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
              {sources.map((src) => {
                const isChecked = selectedSources.includes(src.id);
                const isAvailable = src.health_status === 'operational' || src.health_status === 'connected';
                return (
                  <label
                    key={src.id}
                    className={`flex items-start gap-2.5 p-2 rounded-lg border text-xs cursor-pointer transition select-none ${
                      isChecked 
                        ? 'bg-[#18BFFF]/10 border-[#18BFFF]/50 text-[#F5F7FC]' 
                        : 'bg-[#10182A] border-[#243149] text-[#9BA9C0] opacity-70 hover:opacity-100'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => toggleSource(src.id)}
                      className="mt-0.5 rounded border-[#243149] text-[#18BFFF] focus:ring-0 cursor-pointer"
                    />
                    <div className="flex-1 min-w-0">
                      <div className="font-medium truncate text-[11px] sm:text-xs">{src.name}</div>
                      <div className="text-[10px] text-[#9BA9C0] flex items-center gap-1 mt-0.5">
                        <span className={`inline-block w-1.5 h-1.5 rounded-full ${isAvailable ? 'bg-[#65D96E]' : 'bg-amber-400'}`} />
                        <span className="capitalize truncate">{src.health_status.replace('_', ' ')}</span>
                      </div>
                    </div>
                  </label>
                );
              })}
            </div>

            <div className="flex items-center gap-4 pt-2 border-t border-[#243149]">
              <label className="text-xs text-[#9BA9C0]">Max Results Per Source:</label>
              <input
                type="number"
                min="5"
                max="30"
                value={limit}
                onChange={(e) => setLimit(Number(e.target.value))}
                className="w-20 bg-[#10182A] border border-[#243149] rounded-lg px-2.5 py-1 text-xs text-[#F5F7FC] focus:border-[#18BFFF] outline-none"
              />
              <span className="text-[11px] text-[#9BA9C0]/70">Default: 15 per connector</span>
            </div>
          </div>
        )}

        {/* Submit Button */}
        <button
          type="submit"
          disabled={isLoading || !query.trim()}
          className="w-full bg-gradient-to-r from-[#18BFFF] to-[#65D96E] hover:opacity-95 disabled:opacity-40 disabled:cursor-not-allowed text-[#070B18] font-bold py-3.5 rounded-xl shadow-lg shadow-[#18BFFF]/10 transition-all cursor-pointer flex items-center justify-center gap-2 text-sm"
        >
          {isLoading ? (
            <>
              <div className="w-4 h-4 border-2 border-[#070B18]/30 border-t-[#070B18] rounded-full animate-spin" />
              <span>Coordinating Multi-Source Data Collection...</span>
            </>
          ) : (
            <>
              <Zap className="w-4 h-4" />
              <span>Launch Research Engine</span>
            </>
          )}
        </button>
      </form>
    </div>
  );
};
