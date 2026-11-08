import React, { useState, useEffect, useRef } from 'react';
import { 
  Sparkles, ArrowLeft, Send, Search, CheckCircle2, 
  HelpCircle, ExternalLink, RefreshCw, AlertCircle, 
  Layers, Download, ChevronRight
} from 'lucide-react';
import { api } from '../services/api';
import type { 
  DiscoveryChatMessage, DiscoveryChatResponse, 
  DiscoverySearchResponse, DiscoveryStatus, ResearchResult 
} from '../types';

interface DiscoveryModeProps {
  onBackToHome: () => void;
  onSelectJob?: (jobId: string) => void;
  initialPrompt?: string;
}

export const DiscoveryMode: React.FC<DiscoveryModeProps> = ({ 
  onBackToHome, 
  onSelectJob,
  initialPrompt = ''
}) => {
  const [messages, setMessages] = useState<DiscoveryChatMessage[]>([]);
  const [inputValue, setInputValue] = useState(initialPrompt);
  const [isLoadingChat, setIsLoadingChat] = useState(false);
  const [isExecutingSearch, setIsExecutingSearch] = useState(false);
  const [status, setStatus] = useState<DiscoveryStatus | null>(null);
  const [latestPlanResponse, setLatestPlanResponse] = useState<DiscoveryChatResponse | null>(null);
  const [searchResults, setSearchResults] = useState<DiscoverySearchResponse | null>(null);
  const [selectedGroupTab, setSelectedGroupTab] = useState<string>('All');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll chat to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, latestPlanResponse, isExecutingSearch, searchResults]);

  // Load provider status on mount
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const s = await api.getDiscoveryStatus();
        setStatus(s);
      } catch (err) {
        console.error('Failed to get discovery status:', err);
      }
    };
    fetchStatus();
  }, []);

  // Handle initial prompt if passed from hero search
  useEffect(() => {
    if (initialPrompt && initialPrompt.trim() && messages.length === 0) {
      handleSendMessage(initialPrompt.trim());
    }
  }, [initialPrompt]);

  const handleSendMessage = async (userText: string) => {
    if (!userText.trim() || isLoadingChat || isExecutingSearch) return;

    setErrorMessage(null);
    const newHistory: DiscoveryChatMessage[] = [
      ...messages,
      { role: 'user', content: userText.trim() }
    ];
    setMessages(newHistory);
    setInputValue('');
    setIsLoadingChat(true);

    try {
      const resp = await api.sendDiscoveryChat(userText.trim(), newHistory.slice(-8));

      if (resp.status === 'not_configured') {
        setMessages(prev => [
          ...prev,
          { role: 'assistant', content: resp.message }
        ]);
        setLatestPlanResponse(resp);
      } else if (resp.status === 'error') {
        setErrorMessage(resp.error_detail || resp.message);
        setMessages(prev => [
          ...prev,
          { role: 'assistant', content: `⚠️ ${resp.message}` }
        ]);
      } else {
        // Success or clarification
        setMessages(prev => [
          ...prev,
          { role: 'assistant', content: resp.message }
        ]);
        setLatestPlanResponse(resp);
      }
    } catch (err: any) {
      console.error('Discovery chat error:', err);
      const detail = err?.response?.data?.detail || err.message || 'Failed to reach discovery server.';
      setErrorMessage(detail);
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: `⚠️ Connection error: ${detail}` }
      ]);
    } finally {
      setIsLoadingChat(false);
    }
  };

  const handleExecuteSearch = async () => {
    if (!latestPlanResponse?.search_plan || isExecutingSearch) return;

    setIsExecutingSearch(true);
    setErrorMessage(null);

    try {
      const plan = latestPlanResponse.search_plan;
      const resp = await api.executeDiscoverySearch({
        queries: plan.queries,
        sources: plan.recommended_sources,
        mode: latestPlanResponse.intent?.category === 'developer' ? 'technical' : 'general',
        limit_per_source: 8,
        original_objective: latestPlanResponse.intent?.objective,
        language: latestPlanResponse.intent?.detected_language || 'en'
      });

      setSearchResults(resp);
      setSelectedGroupTab('All');
    } catch (err: any) {
      console.error('Discovery search execution error:', err);
      setErrorMessage(err?.response?.data?.detail || 'Failed to execute discovery search.');
    } finally {
      setIsExecutingSearch(false);
    }
  };

  const handleExport = (format: 'csv' | 'json') => {
    if (!searchResults?.job_id) return;
    const url = api.getExportUrl(searchResults.job_id, format);
    window.open(url, '_blank');
  };

  const starterPrompts = [
    {
      title: "Automotive (Darija)",
      desc: "Engineering & vehicle design",
      prompt: "bghit chi handasa dyal tomobilat"
    },
    {
      title: "Buy a Computer",
      desc: "Find online stores & reviews",
      prompt: "I want to buy a PC, but don't know which stores or websites to check."
    },
    {
      title: "Data Science (Darija)",
      desc: "Courses & training resources",
      prompt: "بغيت شي cours ديال informatique لي فيه traitement de données"
    },
    {
      title: "Learn AI From Scratch",
      desc: "Curated beginner pathway",
      prompt: "I want to learn AI, but I don't know where to start."
    }
  ];

  // Grouped results tabs
  const groupKeys = searchResults ? ['All', ...Object.keys(searchResults.grouped_by_type)] : [];
  const currentDisplayedResults: ResearchResult[] = searchResults
    ? selectedGroupTab === 'All'
      ? searchResults.results
      : searchResults.grouped_by_type[selectedGroupTab] || []
    : [];

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-6 space-y-6 w-full">
      {/* ── Top Header Navigation ────────────────────────────── */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-[#243149]">
        <div className="flex items-center gap-3">
          <button
            onClick={onBackToHome}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#10182A] border border-[#243149] text-[#9BA9C0] hover:text-[#F5F7FC] hover:border-[#18BFFF]/40 transition text-xs font-semibold cursor-pointer"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Back to Search</span>
          </button>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl sm:text-2xl font-black text-[#F5F7FC] tracking-tight flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-[#18BFFF]" />
                <span>ELORA Discovery Assistant</span>
              </h1>
              <span className="text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider bg-[#18BFFF]/10 text-[#18BFFF] border border-[#18BFFF]/30">
                Not Sure? Mode
              </span>
            </div>
            <p className="text-xs text-[#9BA9C0] mt-0.5">
              Describe your idea, goal, or curiosity in natural language. We'll find the right search strategy.
            </p>
          </div>
        </div>

        {/* Provider Status Pill */}
        <div className="flex items-center gap-2 text-xs">
          {status?.configured ? (
            <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#65D96E]/10 border border-[#65D96E]/30 text-[#65D96E]">
              <span className="w-1.5 h-1.5 rounded-full bg-[#65D96E] animate-pulse" />
              <span className="font-medium text-[11px]">{status.provider} ({status.model})</span>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-950/40 border border-amber-900/50 text-amber-300">
              <HelpCircle className="w-3.5 h-3.5" />
              <span className="font-medium text-[11px]">AI Key Needed</span>
            </div>
          )}
        </div>
      </div>

      {/* ── Error Notification ───────────────────────────────── */}
      {errorMessage && (
        <div className="bg-rose-950/40 border border-rose-900/50 rounded-2xl p-4 text-xs text-rose-300 flex items-center justify-between gap-3 animate-in fade-in">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />
            <span>{errorMessage}</span>
          </div>
          <button
            onClick={() => setErrorMessage(null)}
            className="text-rose-400 hover:text-rose-200 cursor-pointer font-bold px-2 py-0.5 rounded hover:bg-rose-950/60 transition"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* ── Unconfigured AI Provider Warning Banner ───────────── */}
      {status && !status.configured && (
        <div className="bg-[#10182A] border border-amber-900/50 rounded-2xl p-4 sm:p-5 text-xs text-amber-200/90 space-y-2">
          <div className="flex items-center gap-2 font-bold text-amber-300 text-sm">
            <AlertCircle className="w-4 h-4 text-amber-400" />
            <span>AI Configuration Required for Discovery Mode</span>
          </div>
          <p className="text-[#9BA9C0] text-xs">
            Discovery Assistant is powered by <strong>Agnes AI</strong> (or optionally OpenAI) to understand natural language requests across multiple languages.
          </p>
          <div className="bg-[#070B18] p-3 rounded-xl border border-[#243149] font-mono text-[11px] text-slate-300 space-y-1">
            <p className="text-[#18BFFF]"># Add to your backend/.env file:</p>
            <p>AGNES_API_KEY=your_agnes_api_key</p>
            <p>AGNES_BASE_URL=https://apihub.agnes-ai.com/v1</p>
            <p>AGNES_MODEL=agnes-2.5-flash</p>
          </div>
        </div>
      )}

      {/* ── Welcome Starters (if conversation hasn't started) ─── */}
      {messages.length === 0 && (
        <div className="bg-[#10182A] border border-[#243149] rounded-2xl p-6 sm:p-8 space-y-6 shadow-xl">
          <div className="space-y-1 text-center max-w-xl mx-auto">
            <div className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-[#18BFFF] to-[#65D96E] flex items-center justify-center mx-auto mb-3 text-[#070B18]">
              <Sparkles className="w-5 h-5" />
            </div>
            <h2 className="text-lg sm:text-xl font-bold text-[#F5F7FC]">
              What are you trying to accomplish?
            </h2>
            <p className="text-xs sm:text-sm text-[#9BA9C0]">
              You don't need technical keywords. Express yourself in English, French, Arabic, Darija, or any language you prefer.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
            {starterPrompts.map((sp, idx) => (
              <button
                key={idx}
                onClick={() => handleSendMessage(sp.prompt)}
                className="p-4 rounded-xl bg-[#070B18] border border-[#243149] hover:border-[#18BFFF]/50 hover:bg-[#18BFFF]/5 transition text-left space-y-1 group cursor-pointer"
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-xs text-[#F5F7FC] group-hover:text-[#18BFFF] transition">
                    {sp.title}
                  </span>
                  <ChevronRight className="w-3.5 h-3.5 text-[#9BA9C0] group-hover:text-[#18BFFF] transition" />
                </div>
                <p className="text-[11px] text-[#9BA9C0]">{sp.desc}</p>
                <p className="text-[11px] text-slate-400 font-mono italic truncate pt-1">"{sp.prompt}"</p>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ── Conversation Message History ──────────────────────── */}
      {messages.length > 0 && (
        <div className="space-y-4">
          {messages.map((m, idx) => {
            const isUser = m.role === 'user';
            return (
              <div 
                key={idx} 
                className={`flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}
              >
                {!isUser && (
                  <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-[#18BFFF] to-[#65D96E] flex items-center justify-center flex-shrink-0 text-[#070B18] mt-0.5">
                    <Sparkles className="w-4 h-4" />
                  </div>
                )}
                <div 
                  className={`max-w-[85%] sm:max-w-2xl rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-lg ${
                    isUser 
                      ? 'bg-[#18BFFF] text-[#070B18] font-medium rounded-br-none' 
                      : 'bg-[#10182A] border border-[#243149] text-[#F5F7FC] rounded-bl-none'
                  }`}
                >
                  <p className="whitespace-pre-wrap">{m.content}</p>
                </div>
              </div>
            );
          })}

          {/* Loading indicator during chat processing */}
          {isLoadingChat && (
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-xl bg-[#10182A] border border-[#243149] flex items-center justify-center text-[#18BFFF]">
                <Sparkles className="w-4 h-4 animate-spin" />
              </div>
              <div className="bg-[#10182A] border border-[#243149] rounded-2xl px-4 py-3 text-xs text-[#9BA9C0] flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-[#18BFFF] animate-ping" />
                <span>ELORA is analyzing your request and building discovery plan…</span>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      )}

      {/* ── Structured Discovery Search Plan Card ─────────────── */}
      {latestPlanResponse?.search_plan && (
        <div className="bg-[#10182A] border border-[#18BFFF]/40 rounded-2xl p-5 sm:p-6 shadow-2xl space-y-4 animate-in fade-in duration-200">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-3 border-b border-[#243149]">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-bold text-[#F5F7FC] text-base sm:text-lg flex items-center gap-2">
                  <Layers className="w-4 h-4 text-[#18BFFF]" />
                  <span>Proposed Discovery Search Strategy</span>
                </h3>
                <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded bg-[#18BFFF]/10 text-[#18BFFF] border border-[#18BFFF]/30">
                  {latestPlanResponse.intent?.category || 'General'}
                </span>
              </div>
              {latestPlanResponse.understanding && (
                <p className="text-xs text-[#9BA9C0] mt-1">
                  <strong>Understanding:</strong> {latestPlanResponse.understanding}
                </p>
              )}
            </div>

            {/* Start Discovery Execution Button */}
            <button
              onClick={handleExecuteSearch}
              disabled={isExecutingSearch}
              className="bg-gradient-to-r from-[#18BFFF] to-[#65D96E] hover:opacity-95 disabled:opacity-50 text-[#070B18] font-bold px-5 py-2.5 rounded-xl shadow-lg shadow-[#18BFFF]/10 transition cursor-pointer flex items-center gap-2 text-sm whitespace-nowrap self-stretch sm:self-auto justify-center"
            >
              {isExecutingSearch ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Executing Discovery Search…</span>
                </>
              ) : (
                <>
                  <Search className="w-4 h-4" />
                  <span>Start Discovery</span>
                </>
              )}
            </button>
          </div>

          {/* Topics & Extracted Concepts */}
          {latestPlanResponse.intent && (
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="text-[#9BA9C0] font-semibold">Key Topics:</span>
              <span className="px-2.5 py-1 rounded-lg bg-[#070B18] border border-[#243149] text-[#F5F7FC] font-medium">
                {latestPlanResponse.intent.main_topic}
              </span>
              {latestPlanResponse.intent.related_topics.map((t, idx) => (
                <span key={idx} className="px-2.5 py-1 rounded-lg bg-[#070B18] border border-[#243149] text-[#9BA9C0]">
                  {t}
                </span>
              ))}
            </div>
          )}

          {/* Search Queries Planned */}
          <div className="space-y-1.5">
            <span className="text-xs font-semibold text-[#9BA9C0]">Targeted Search Queries:</span>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {latestPlanResponse.search_plan.queries.map((q, idx) => (
                <div key={idx} className="flex items-center gap-2 p-2.5 rounded-xl bg-[#070B18] border border-[#243149] text-xs text-[#F5F7FC]">
                  <Search className="w-3.5 h-3.5 text-[#18BFFF] flex-shrink-0" />
                  <span className="truncate">{q}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Recommended Sources */}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <span className="text-xs font-semibold text-[#9BA9C0]">Target Engines:</span>
            {latestPlanResponse.search_plan.recommended_sources.map((sid, idx) => (
              <span key={idx} className="text-[11px] px-2.5 py-1 rounded-lg bg-[#070B18] border border-[#243149] text-[#18BFFF] font-mono">
                {sid}
              </span>
            ))}
          </div>

          {latestPlanResponse.search_plan.reasoning && (
            <p className="text-[11px] text-[#9BA9C0]/80 italic border-t border-[#243149] pt-2">
              Strategy note: {latestPlanResponse.search_plan.reasoning}
            </p>
          )}
        </div>
      )}

      {/* ── Real Search Results Section ───────────────────────── */}
      {searchResults && (
        <div className="bg-[#10182A] border border-[#243149] rounded-2xl p-5 sm:p-6 space-y-5 shadow-2xl">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-3 border-b border-[#243149]">
            <div>
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-5 h-5 text-[#65D96E]" />
                <h3 className="font-bold text-[#F5F7FC] text-lg">Verified Discovery Evidence</h3>
                <span className="text-xs px-2 py-0.5 rounded-full bg-[#65D96E]/10 text-[#65D96E] border border-[#65D96E]/30 font-semibold">
                  {searchResults.total_results} records
                </span>
              </div>
              <p className="text-xs text-[#9BA9C0] mt-0.5">
                {searchResults.summary || "Genuine evidence collected from official web & academic connectors."}
              </p>
            </div>

            {/* Export Actions */}
            <div className="flex items-center gap-2">
              <button
                onClick={() => handleExport('csv')}
                className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-[#070B18] border border-[#243149] text-[#9BA9C0] hover:text-[#F5F7FC] transition cursor-pointer"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Export CSV</span>
              </button>
              {onSelectJob && searchResults.job_id && (
                <button
                  onClick={() => onSelectJob(searchResults.job_id)}
                  className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-[#18BFFF]/10 border border-[#18BFFF]/30 text-[#18BFFF] hover:bg-[#18BFFF]/20 transition cursor-pointer"
                >
                  <span>Detailed Report &rarr;</span>
                </button>
              )}
            </div>
          </div>

          {/* Category / Group Tabs */}
          {groupKeys.length > 2 && (
            <div className="flex items-center gap-2 overflow-x-auto pb-1 text-xs">
              {groupKeys.map((gk) => {
                const count = gk === 'All' ? searchResults.total_results : searchResults.grouped_by_type[gk]?.length || 0;
                return (
                  <button
                    key={gk}
                    onClick={() => setSelectedGroupTab(gk)}
                    className={`px-3 py-1.5 rounded-xl border transition whitespace-nowrap cursor-pointer ${
                      selectedGroupTab === gk
                        ? 'bg-[#18BFFF]/10 border-[#18BFFF] text-[#18BFFF] font-semibold'
                        : 'bg-[#070B18] border-[#243149] text-[#9BA9C0] hover:text-[#F5F7FC]'
                    }`}
                  >
                    <span>{gk} ({count})</span>
                  </button>
                );
              })}
            </div>
          )}

          {/* Results List */}
          {currentDisplayedResults.length === 0 ? (
            <div className="py-12 text-center text-[#9BA9C0] text-xs">
              No results found in this category.
            </div>
          ) : (
            <div className="space-y-3">
              {currentDisplayedResults.slice(0, 15).map((r) => (
                <div
                  key={r.id}
                  className="p-4 rounded-xl bg-[#070B18] border border-[#243149] hover:border-[#18BFFF]/40 transition space-y-2 group"
                >
                  <div className="flex items-start justify-between gap-3">
                    <a
                      href={r.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-semibold text-sm text-[#F5F7FC] group-hover:text-[#18BFFF] transition flex items-center gap-1.5"
                    >
                      <span>{r.title}</span>
                      <ExternalLink className="w-3.5 h-3.5 text-[#9BA9C0] group-hover:text-[#18BFFF] flex-shrink-0" />
                    </a>
                    <span className="text-[10px] px-2 py-0.5 rounded font-mono uppercase bg-[#10182A] text-[#18BFFF] border border-[#243149] flex-shrink-0">
                      {r.source_name}
                    </span>
                  </div>

                  {r.content_snippet && (
                    <p className="text-xs text-[#9BA9C0] line-clamp-3 leading-relaxed">
                      {r.content_snippet}
                    </p>
                  )}

                  <div className="flex flex-wrap items-center gap-3 text-[11px] text-[#9BA9C0]/70 pt-1">
                    {r.author && <span>By {r.author}</span>}
                    {r.published_at && (
                      <span>Date: {new Date(r.published_at).toLocaleDateString()}</span>
                    )}
                    <span>Score: {Math.round(r.relevance_score * 100)}%</span>
                    <a
                      href={r.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[#18BFFF] hover:underline truncate max-w-xs"
                    >
                      {r.source_url}
                    </a>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Suggestion to continue the conversation */}
          <div className="p-3 rounded-xl bg-[#070B18] border border-[#243149] text-xs text-[#9BA9C0] flex items-center justify-between">
            <span>Want to refine or explore further? Type below (e.g., <em>"Find free ones only"</em>, <em>"Focus on practical tutorials"</em>, <em>"Search in French"</em>).</span>
          </div>
        </div>
      )}

      {/* ── Follow-Up Input Bar ──────────────────────────────── */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          handleSendMessage(inputValue);
        }}
        className="sticky bottom-4 z-40"
      >
        <div className="relative flex items-center bg-[#10182A] border border-[#243149] focus-within:border-[#18BFFF] rounded-2xl shadow-2xl overflow-hidden transition">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder={
              messages.length === 0
                ? "Describe what you're trying to find in any language (English, French, Darija, Arabic...)"
                : "Ask follow-ups, refine topics, or steer the search direction..."
            }
            disabled={isLoadingChat || isExecutingSearch}
            className="w-full bg-transparent px-5 py-4 text-sm text-[#F5F7FC] placeholder-[#9BA9C0]/60 focus:outline-none"
            autoFocus
          />
          <div className="pr-2 flex items-center gap-2">
            <button
              type="submit"
              disabled={!inputValue.trim() || isLoadingChat || isExecutingSearch}
              className="bg-gradient-to-r from-[#18BFFF] to-[#65D96E] hover:opacity-95 disabled:opacity-30 disabled:cursor-not-allowed text-[#070B18] font-bold px-4 py-2 rounded-xl transition cursor-pointer flex items-center gap-1.5 text-xs"
            >
              <Send className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Send</span>
            </button>
          </div>
        </div>
      </form>
    </div>
  );
};
