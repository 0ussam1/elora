import { useState, useEffect, useRef } from 'react';
import { 
  Search, LayoutDashboard, Plus, FileText, Settings, 
  ArrowLeft, Terminal, Database, History, X, Zap, 
  BookOpen, Globe, Code2, ShieldCheck, Sparkles
} from 'lucide-react';
import { api } from './services/api';
import type { ResearchJob, SourceInfo, ResearchResult, ResearchReport, CollectionLog, SourceDiagnostic } from './types';
import { Dashboard } from './components/Dashboard';
import { SearchPage } from './components/SearchPage';
import { ResultsExplorer } from './components/ResultsExplorer';
import { ReportView } from './components/ReportView';
import { DiscoveryMode } from './components/DiscoveryMode';

// ── ELORA Brand Logo ──────────────────────────────────────────────────────────
export function EloraLogo({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) {
  const isLg = size === 'lg';
  const isSm = size === 'sm';
  const fontSize = isLg ? 'text-4xl sm:text-6xl' : isSm ? 'text-lg' : 'text-2xl';
  const capsuleW = isLg ? 42 : isSm ? 15 : 22;
  const capsuleH = isLg ? 26 : isSm ? 10 : 15;

  return (
    <span className={`inline-flex items-center gap-0.5 font-black tracking-tight select-none ${fontSize} text-[#F5F7FC]`}>
      <span>EL</span>
      <span className="inline-flex items-center justify-center px-0.5">
        <svg
          width={capsuleW}
          height={capsuleH}
          viewBox={`0 0 ${capsuleW} ${capsuleH}`}
          className="inline-block"
          aria-hidden="true"
        >
          <defs>
            <linearGradient id={`elora-grad-${size}`} x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#18BFFF" />
              <stop offset="100%" stopColor="#65D96E" />
            </linearGradient>
          </defs>
          <rect
            x="0.5"
            y="0.5"
            width={capsuleW - 1}
            height={capsuleH - 1}
            rx={(capsuleH - 1) / 2}
            ry={(capsuleH - 1) / 2}
            fill={`url(#elora-grad-${size})`}
          />
        </svg>
      </span>
      <span>RA</span>
    </span>
  );
}

// ── Application Tabs ─────────────────────────────────────────────────────────
type Tab = 'home' | 'dashboard' | 'search' | 'job_detail' | 'settings' | 'discovery';

export function App() {
  const [activeTab, setActiveTab] = useState<Tab>('home');
  const [initialDiscoveryPrompt, setInitialDiscoveryPrompt] = useState<string>('');
  const [jobs, setJobs] = useState<ResearchJob[]>([]);
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [currentJob, setCurrentJob] = useState<ResearchJob | null>(null);
  const [results, setResults] = useState<ResearchResult[]>([]);
  const [report, setReport] = useState<ResearchReport | null>(null);
  const [logs, setLogs] = useState<CollectionLog[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [jobViewTab, setJobViewTab] = useState<'results' | 'report' | 'logs'>('results');
  const [testingSourceId, setTestingSourceId] = useState<string | null>(null);
  const [diagnosticResults, setDiagnosticResults] = useState<Record<string, SourceDiagnostic>>({});
  
  // Navigation Menu State
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close menu on clicking outside
  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);

  // Load initial data
  useEffect(() => {
    loadSources();
    loadHistory();
  }, []);

  const loadSources = async () => {
    try {
      const data = await api.getSources();
      setSources(data);
    } catch (err) {
      console.error("Failed to load sources:", err);
    }
  };

  const loadHistory = async () => {
    try {
      const data = await api.getHistory();
      setJobs(data);
    } catch (err) {
      console.error("Failed to load history:", err);
    }
  };

  // Poll active job if running
  useEffect(() => {
    if (!selectedJobId) return;

    const fetchDetails = async () => {
      try {
        const j = await api.getJob(selectedJobId);
        setCurrentJob(j);

        const res = await api.getResults(selectedJobId);
        setResults(res);

        const l = await api.getLogs(selectedJobId);
        setLogs(l);

        if (j.status === 'completed') {
          try {
            const rep = await api.getReport(selectedJobId);
            setReport(rep);
          } catch (e) {
            // Report might still be generating
          }
        }
      } catch (err) {
        console.error("Error polling job details:", err);
      }
    };

    fetchDetails();
    const interval = setInterval(() => {
      if (currentJob?.status === 'running' || currentJob?.status === 'pending') {
        fetchDetails();
        loadHistory();
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [selectedJobId, currentJob?.status]);

  // Lightweight background validation status refresh after search completes
  useEffect(() => {
    if (!selectedJobId || currentJob?.status !== 'completed') return;
    const hasPendingValidation = results.some(
      (r) =>
        !r.metadata_fields?.validation_status ||
        r.metadata_fields.validation_status === 'PENDING' ||
        r.metadata_fields.validation_status === 'FAST_VERIFIED'
    );
    if (!hasPendingValidation) return;

    let attempts = 0;
    const valInterval = setInterval(async () => {
      attempts += 1;
      try {
        const res = await api.getResults(selectedJobId);
        setResults(res);
      } catch {
        // Ignore transient validation poll errors
      }
      if (attempts >= 6) {
        clearInterval(valInterval);
      }
    }, 2500);

    return () => clearInterval(valInterval);
  }, [selectedJobId, currentJob?.status, results.length]);

  const handleStartResearch = async (params: {
    query: string;
    mode: string;
    sources: string[];
    limit_per_source: number;
  }) => {
    setIsLoading(true);
    try {
      const newJob = await api.createJob(params);
      setSelectedJobId(newJob.id);
      setCurrentJob(newJob);
      setActiveTab('job_detail');
      setJobViewTab('results');
      loadHistory();
    } catch (err) {
      console.error("Failed to create job:", err);
      alert("Failed to start research job. Make sure backend is running.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleSelectJob = (id: string) => {
    setSelectedJobId(id);
    setActiveTab('job_detail');
    setJobViewTab('results');
  };

  const handleDeleteJob = async (jobId: string) => {
    try {
      await api.deleteJob(jobId);
      if (selectedJobId === jobId) {
        setSelectedJobId(null);
        setCurrentJob(null);
        setActiveTab('home');
      }
      loadHistory();
    } catch (err) {
      console.error("Failed to delete job:", err);
      alert("Failed to delete research item.");
    }
  };

  const handleClearHistory = async () => {
    try {
      await api.clearHistory();
      setSelectedJobId(null);
      setCurrentJob(null);
      setJobs([]);
      setActiveTab('home');
    } catch (err) {
      console.error("Failed to clear history:", err);
      alert("Failed to clear research history.");
    }
  };

  const handleExport = (format: 'csv' | 'json') => {
    if (!selectedJobId) return;
    const url = api.getExportUrl(selectedJobId, format);
    window.open(url, '_blank');
  };

  const navigateTo = (tab: Tab) => {
    setActiveTab(tab);
    setMenuOpen(false);
    if (tab !== 'job_detail') {
      setSelectedJobId(null);
      setCurrentJob(null);
    }
  };

  const navigationItems = [
    { icon: Sparkles, label: 'Discovery Mode (Not Sure?)', tab: 'discovery' as Tab, desc: 'AI-guided exploration & search' },
    { icon: LayoutDashboard, label: 'Dashboard', tab: 'dashboard' as Tab, desc: 'Operations & system analytics' },
    { icon: Search, label: 'New Search', tab: 'search' as Tab, desc: 'Advanced multi-source parameters' },
    { icon: History, label: 'Research History', tab: 'dashboard' as Tab, desc: 'Past investigations & evidence' },
    { icon: FileText, label: 'Reports', tab: 'dashboard' as Tab, desc: 'Synthesized intelligence briefs' },
    { icon: ShieldCheck, label: 'Connectors', tab: 'settings' as Tab, desc: 'API authorization & status' },
    { icon: Settings, label: 'Settings', tab: 'settings' as Tab, desc: 'Engine diagnostic controls' },
  ];

  return (
    <div className="min-h-screen bg-[#070B18] text-[#F5F7FC] flex flex-col selection:bg-[#18BFFF]/30 selection:text-[#F5F7FC]">
      {/* ── Top Navigation Bar ───────────────────────────────── */}
      <header className="border-b border-[#243149] bg-[#070B18]/80 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          {/* Left: Brand Logo */}
          <div 
            onClick={() => navigateTo('home')}
            className="flex items-center gap-3 cursor-pointer group"
            title="ELORA – Home"
          >
            <EloraLogo size="md" />
            <span className="text-[10px] font-semibold tracking-wider px-2 py-0.5 rounded-full bg-[#10182A] text-[#18BFFF] border border-[#243149] uppercase hidden sm:inline-block">
              Research Engine
            </span>
          </div>

          {/* Right: Actions & Plus Menu */}
          <div className="flex items-center gap-3 relative" ref={menuRef}>
            {activeTab !== 'home' && (
              <button
                onClick={() => navigateTo('home')}
                className="hidden md:flex items-center gap-1.5 text-xs text-[#9BA9C0] hover:text-[#F5F7FC] transition mr-2"
              >
                <Search className="w-3.5 h-3.5 text-[#18BFFF]" />
                <span>Search</span>
              </button>
            )}

            {/* Plus Menu Toggle */}
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              aria-label="Application menu"
              aria-expanded={menuOpen}
              className={`w-9 h-9 rounded-xl flex items-center justify-center transition cursor-pointer border ${
                menuOpen 
                  ? 'bg-[#18BFFF]/10 border-[#18BFFF] text-[#18BFFF]' 
                  : 'bg-[#10182A] border-[#243149] text-[#9BA9C0] hover:text-[#F5F7FC] hover:border-[#18BFFF]/40'
              }`}
            >
              {menuOpen ? <X className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
            </button>

            {/* Polished Dropdown Menu */}
            {menuOpen && (
              <div className="absolute right-0 top-12 w-64 bg-[#10182A] border border-[#243149] rounded-2xl shadow-2xl shadow-black/80 overflow-hidden z-50 animate-in fade-in zoom-in-95 duration-100">
                <div className="px-4 py-3 border-b border-[#243149] flex items-center justify-between">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-[#9BA9C0]">Navigation</span>
                  <span className="text-[10px] text-[#18BFFF] font-mono">v1.2</span>
                </div>
                <div className="p-2 space-y-1">
                  {navigationItems.map((item, idx) => {
                    const Icon = item.icon;
                    const isSelected = activeTab === item.tab && (item.label !== 'Research History' && item.label !== 'Reports');
                    return (
                      <button
                        key={idx}
                        onClick={() => navigateTo(item.tab)}
                        className={`w-full flex items-center gap-3 px-3 py-2 rounded-xl text-left transition cursor-pointer ${
                          isSelected
                            ? 'bg-[#18BFFF]/10 text-[#18BFFF]'
                            : 'text-[#9BA9C0] hover:text-[#F5F7FC] hover:bg-[#070B18]'
                        }`}
                      >
                        <div className={`p-1.5 rounded-lg border ${
                          isSelected 
                            ? 'bg-[#18BFFF]/20 border-[#18BFFF]/30 text-[#18BFFF]' 
                            : 'bg-[#070B18] border-[#243149] text-[#9BA9C0]'
                        }`}>
                          <Icon className="w-4 h-4" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-xs font-semibold text-[#F5F7FC]">{item.label}</div>
                          <div className="text-[10px] text-[#9BA9C0] truncate">{item.desc}</div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* ── Main View Area ───────────────────────────────────── */}
      <main className="flex-1 flex flex-col">
        {/* VIEW 1: Search-First Homepage */}
        {activeTab === 'home' && (
          <HomePageHero
            sources={sources}
            jobs={jobs}
            isLoading={isLoading}
            onSubmit={handleStartResearch}
            onSelectJob={handleSelectJob}
            onNavigateDashboard={() => navigateTo('dashboard')}
            onNavigateAdvancedSearch={() => navigateTo('search')}
            onNavigateDiscovery={(prompt) => {
              if (prompt) setInitialDiscoveryPrompt(prompt);
              navigateTo('discovery');
            }}
          />
        )}

        {/* VIEW 2: Dedicated Dashboard Section */}
        {activeTab === 'dashboard' && (
          <div className="max-w-7xl w-full mx-auto p-4 sm:p-6 lg:p-8">
            <Dashboard
              jobs={jobs}
              sources={sources}
              onSelectJob={handleSelectJob}
              onNavigateSearch={() => navigateTo('search')}
              onDeleteJob={handleDeleteJob}
              onClearHistory={handleClearHistory}
            />
          </div>
        )}

        {/* VIEW 3: Dedicated Advanced Search Form */}
        {activeTab === 'search' && (
          <div className="max-w-7xl w-full mx-auto p-4 sm:p-6 lg:p-8">
            <SearchPage
              sources={sources}
              onSubmit={handleStartResearch}
              isLoading={isLoading}
            />
          </div>
        )}

        {/* VIEW 4: Job Detail & Results Explorer */}
        {activeTab === 'job_detail' && currentJob && (
          <div className="max-w-7xl w-full mx-auto p-4 sm:p-6 lg:p-8 space-y-6">
            {/* Job Header & Status Bar */}
            <div className="bg-[#10182A] border border-[#243149] rounded-2xl p-5 sm:p-6 shadow-xl flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
              <div className="space-y-1">
                <div className="flex items-center gap-3 mb-2">
                  <button
                    onClick={() => navigateTo('dashboard')}
                    className="flex items-center gap-1.5 text-xs text-[#9BA9C0] hover:text-[#F5F7FC] transition cursor-pointer"
                  >
                    <ArrowLeft className="w-3.5 h-3.5" /> Back to Dashboard
                  </button>
                  <span className="text-[#243149]">|</span>
                  <button
                    onClick={() => {
                      if (confirm(`Delete this research investigation: "${currentJob.query}"?`)) {
                        handleDeleteJob(currentJob.id);
                      }
                    }}
                    className="flex items-center gap-1 text-xs text-rose-400 hover:text-rose-300 transition cursor-pointer"
                  >
                    <span>Delete search</span>
                  </button>
                </div>
                <h1 className="text-xl sm:text-2xl font-bold text-[#F5F7FC] tracking-tight">{currentJob.query}</h1>
                <div className="flex flex-wrap items-center gap-3 text-xs text-[#9BA9C0] pt-1">
                  <span>Mode: <strong className="text-[#F5F7FC] capitalize">{currentJob.mode}</strong></span>
                  <span>•</span>
                  <span>{results.length} collected items</span>
                  <span>•</span>
                  <span>Initiated: {new Date(currentJob.created_at).toLocaleTimeString()}</span>
                </div>
              </div>

              {/* Progress & Status */}
              <div className="w-full md:w-64 space-y-2">
                <div className="flex items-center justify-between text-xs font-semibold">
                  <span className="capitalize text-[#9BA9C0]">{currentJob.status}</span>
                  <span className="text-[#18BFFF]">{Math.round(currentJob.progress)}%</span>
                </div>
                <div className="w-full bg-[#070B18] rounded-full h-2 overflow-hidden border border-[#243149]">
                  <div
                    className="h-full transition-all duration-500 rounded-full"
                    style={{
                      width: `${currentJob.progress}%`,
                      background: 'linear-gradient(90deg, #18BFFF, #65D96E)'
                    }}
                  />
                </div>
              </div>
            </div>

            {/* Sub-navigation Tabs */}
            <div className="flex items-center gap-2 border-b border-[#243149] pb-2">
              <button
                onClick={() => setJobViewTab('results')}
                className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold transition cursor-pointer ${
                  jobViewTab === 'results' 
                    ? 'bg-gradient-to-r from-[#18BFFF] to-[#65D96E] text-[#070B18] shadow-md shadow-[#18BFFF]/10 font-bold' 
                    : 'text-[#9BA9C0] hover:text-[#F5F7FC] bg-[#10182A] border border-[#243149]'
                }`}
              >
                <Database className="w-4 h-4" />
                <span>Verified Results ({results.length})</span>
              </button>

              <button
                onClick={() => setJobViewTab('report')}
                className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold transition cursor-pointer ${
                  jobViewTab === 'report' 
                    ? 'bg-gradient-to-r from-[#18BFFF] to-[#65D96E] text-[#070B18] shadow-md shadow-[#18BFFF]/10 font-bold' 
                    : 'text-[#9BA9C0] hover:text-[#F5F7FC] bg-[#10182A] border border-[#243149]'
                }`}
              >
                <FileText className="w-4 h-4" />
                <span>Intelligence Report {report ? '✓' : ''}</span>
              </button>

              <button
                onClick={() => setJobViewTab('logs')}
                className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold transition cursor-pointer ${
                  jobViewTab === 'logs' 
                    ? 'bg-gradient-to-r from-[#18BFFF] to-[#65D96E] text-[#070B18] shadow-md shadow-[#18BFFF]/10 font-bold' 
                    : 'text-[#9BA9C0] hover:text-[#F5F7FC] bg-[#10182A] border border-[#243149]'
                }`}
              >
                <Terminal className="w-4 h-4" />
                <span>Pipeline Logs ({logs.length})</span>
              </button>
            </div>

            {/* Tab Views */}
            {jobViewTab === 'results' && (
              <ResultsExplorer
                results={results}
                query={currentJob.query}
                onExport={handleExport}
              />
            )}

            {jobViewTab === 'report' && (
              report ? (
                <ReportView
                  report={report}
                  query={currentJob.query}
                />
              ) : (
                <div className="bg-[#10182A] border border-[#243149] rounded-2xl p-12 text-center text-[#9BA9C0] space-y-3">
                  <div className="w-6 h-6 border-2 border-[#18BFFF] border-t-transparent rounded-full animate-spin mx-auto" />
                  <p className="text-sm">Synthesizing evidence-based report from verified records...</p>
                </div>
              )
            )}

            {jobViewTab === 'logs' && (
              <div className="bg-[#10182A] border border-[#243149] rounded-2xl p-5 space-y-3">
                <h3 className="text-sm font-semibold text-[#F5F7FC]">Execution Logs</h3>
                <div className="space-y-2 font-mono text-xs">
                  {logs.map(l => (
                    <div key={l.id} className="p-3 bg-[#070B18] rounded-xl border border-[#243149] flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <span className="text-[#18BFFF] font-bold uppercase">{l.source_name}</span>
                        <span className="text-[#9BA9C0]">{l.message}</span>
                      </div>
                      <div className="text-[#9BA9C0]/60 text-[11px]">
                        {l.duration_ms}ms
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* VIEW 5: Connectors & Settings Diagnostics */}
        {activeTab === 'settings' && (
          <div className="max-w-4xl mx-auto p-4 sm:p-6 lg:p-8 space-y-6 w-full">
            <div className="bg-[#10182A] border border-[#243149] rounded-2xl p-6 space-y-5">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-bold text-[#F5F7FC]">Configured Connectors & Diagnostics</h2>
                  <p className="text-xs text-[#9BA9C0] mt-0.5">
                    Sources use official APIs or open public access endpoints. Test live authorization without exposing tokens.
                  </p>
                </div>
                <button
                  onClick={loadSources}
                  className="text-xs text-[#9BA9C0] hover:text-[#F5F7FC] bg-[#070B18] px-3 py-1.5 rounded-xl border border-[#243149] transition cursor-pointer"
                >
                  Refresh Status
                </button>
              </div>

              <div className="divide-y divide-[#243149]">
                {sources.map(src => {
                  const isGood = src.health_status === 'operational' || src.health_status === 'connected';
                  const isRate = src.health_status === 'rate_limited';
                  const isWarn = !isGood && !isRate && src.health_status !== 'error';

                  const badgeColor = isGood ? 'bg-[#65D96E]/10 text-[#65D96E] border-[#65D96E]/30' :
                    isRate ? 'bg-amber-950/60 text-amber-300 border-amber-800/60' :
                    isWarn ? 'bg-amber-950/60 text-amber-400 border-amber-800/60' :
                    'bg-rose-950/60 text-rose-400 border-rose-800/60';

                  const diag = testingSourceId === src.id ? null : diagnosticResults[src.id];
                  const isTestingThis = testingSourceId === src.id;

                  return (
                    <div key={src.id} className="py-4 space-y-2">
                      <div className="flex items-start justify-between gap-4">
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-sm text-[#F5F7FC]">{src.name}</span>
                            <span className="text-[10px] text-[#9BA9C0] uppercase tracking-wider bg-[#070B18] px-2 py-0.5 rounded border border-[#243149]">
                              {src.category}
                            </span>
                          </div>
                          <div className="text-xs text-[#9BA9C0]">
                            {src.message || "Ready"}
                          </div>
                          <div className="text-[11px] text-[#9BA9C0]/70">
                            Supported: {src.supported_content_types.join(', ')} • Rate Quota: {src.rate_limit_per_minute} req/min
                          </div>
                        </div>

                        <div className="flex items-center gap-3 flex-shrink-0">
                          <span className={`px-2.5 py-1 rounded-full text-xs font-semibold border ${badgeColor}`}>
                            {src.health_status.replace('_', ' ')}
                          </span>

                          <button
                            disabled={isTestingThis}
                            onClick={async () => {
                              setTestingSourceId(src.id);
                              try {
                                const res = await api.testSource(src.id);
                                setDiagnosticResults(prev => ({ ...prev, [src.id]: res }));
                                loadSources();
                              } catch (err: any) {
                                setDiagnosticResults(prev => ({
                                  ...prev,
                                  [src.id]: {
                                    source_id: src.id,
                                    configured: false,
                                    authorized: false,
                                    connected: false,
                                    status: 'error',
                                    message: err?.response?.data?.detail || 'Connection test failed',
                                    last_checked_at: new Date().toISOString()
                                  }
                                }));
                              } finally {
                                setTestingSourceId(null);
                              }
                            }}
                            className="bg-[#070B18] hover:bg-[#243149]/50 disabled:opacity-50 text-[#18BFFF] text-xs px-3 py-1.5 rounded-xl border border-[#243149] transition cursor-pointer flex items-center gap-1.5"
                          >
                            {isTestingThis ? (
                              <div className="w-3 h-3 border-2 border-[#18BFFF] border-t-transparent rounded-full animate-spin" />
                            ) : null}
                            <span>{isTestingThis ? "Testing..." : "Test Connection"}</span>
                          </button>
                        </div>
                      </div>

                      {/* Diagnostic details box if tested */}
                      {diag && (
                        <div className="mt-2 p-3 rounded-xl bg-[#070B18] border border-[#243149] text-xs space-y-1">
                          <div className="flex items-center justify-between">
                            <span className="font-semibold text-[#9BA9C0]">
                              Diagnostic Result ({new Date(diag.last_checked_at).toLocaleTimeString()}):
                            </span>
                            <span className={`text-[10px] px-2 py-0.5 rounded font-bold uppercase ${
                              diag.connected ? 'bg-[#65D96E]/10 text-[#65D96E] border border-[#65D96E]/30' : 'bg-amber-950/60 text-amber-400'
                            }`}>
                              {diag.status.replace('_', ' ')}
                            </span>
                          </div>
                          <p className="text-[#9BA9C0]">{diag.message}</p>
                          {src.id === 'reddit' && !diag.configured && (
                            <div className="pt-2 text-[11px] text-amber-300 bg-amber-950/30 p-2 rounded-lg border border-amber-900/40 mt-1">
                              <strong>Configuration Steps:</strong> Add <code className="text-[#18BFFF]">REDDIT_CLIENT_ID</code> and <code className="text-[#18BFFF]">REDDIT_CLIENT_SECRET</code> to your backend <code className="text-[#18BFFF]">.env</code> file, then click "Test Connection".
                            </div>
                          )}
                          {src.id === 'kaggle' && !diag.configured && (
                            <div className="pt-2 text-[11px] text-amber-300 bg-amber-950/30 p-2 rounded-lg border border-amber-900/40 mt-1">
                              <strong>Configuration Steps:</strong> Add <code className="text-[#18BFFF]">KAGGLE_USERNAME</code> and <code className="text-[#18BFFF]">KAGGLE_KEY</code> (from kaggle.com/settings &rarr; Create New Token) to your backend <code className="text-[#18BFFF]">.env</code> file.
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* VIEW 6: Discovery Mode ("Not Sure?") */}
        {activeTab === 'discovery' && (
          <DiscoveryMode
            onBackToHome={() => navigateTo('home')}
            onSelectJob={handleSelectJob}
            initialPrompt={initialDiscoveryPrompt}
          />
        )}
      </main>
    </div>
  );
}

// ── Search-First Homepage Component ───────────────────────────────────────────
interface HomePageHeroProps {
  sources: SourceInfo[];
  jobs: ResearchJob[];
  isLoading: boolean;
  onSubmit: (params: { query: string; mode: string; sources: string[]; limit_per_source: number }) => void;
  onSelectJob: (id: string) => void;
  onNavigateDashboard: () => void;
  onNavigateAdvancedSearch: () => void;
  onNavigateDiscovery: (prompt?: string) => void;
}

function HomePageHero({
  sources,
  jobs,
  isLoading,
  onSubmit,
  onSelectJob,
  onNavigateDashboard,
  onNavigateAdvancedSearch,
  onNavigateDiscovery
}: HomePageHeroProps) {
  const [query, setQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState<'all' | 'web' | 'developer' | 'academic' | 'problem'>('all');

  const operationalSources = sources
    .filter(s => s.health_status === 'operational' || s.health_status === 'connected')
    .map(s => s.id);

  // Determine mode and source subset based on category filter
  const getFilterParams = () => {
    switch (categoryFilter) {
      case 'web':
        return {
          mode: 'general',
          sources: operationalSources.filter(id => ['web_search', 'wikipedia', 'hackernews'].includes(id))
        };
      case 'developer':
        return {
          mode: 'technical',
          sources: operationalSources.filter(id => ['github', 'stack_exchange', 'hackernews', 'kaggle'].includes(id))
        };
      case 'academic':
        return {
          mode: 'technical',
          sources: operationalSources.filter(id => ['arxiv', 'openalex', 'crossref', 'openlibrary', 'internet_archive'].includes(id))
        };
      case 'problem':
        return {
          mode: 'problem_discovery',
          sources: operationalSources
        };
      default:
        return {
          mode: 'general',
          sources: operationalSources
        };
    }
  };

  const handleSearchSubmit = (overrideQuery?: string) => {
    const q = (overrideQuery ?? query).trim();
    if (!q || isLoading) return;

    const { mode, sources: targetSources } = getFilterParams();
    onSubmit({
      query: q,
      mode,
      sources: targetSources.length > 0 ? targetSources : operationalSources,
      limit_per_source: 15
    });
  };

  const categories = [
    { id: 'all', label: 'All Sources', icon: Globe },
    { id: 'web', label: 'Web', icon: Globe },
    { id: 'developer', label: 'Developer', icon: Code2 },
    { id: 'academic', label: 'Academic', icon: BookOpen },
    { id: 'problem', label: 'Deep Research', icon: Zap },
  ] as const;

  const sampleQueries = [
    "Find recurring problems people experience with free AI tools",
    "Research the limitations of current data-cleaning tools",
    "Find unresolved issues related to Python machine learning libraries",
    "Discover potential SaaS ideas based on real user complaints"
  ];

  return (
    <div className="flex-1 flex flex-col items-center justify-center px-4 sm:px-6 py-12 md:py-20 max-w-4xl mx-auto w-full">
      {/* ── Brand & Tagline ─────────────────────────────────── */}
      <div className="flex flex-col items-center text-center space-y-3 mb-8">
        <EloraLogo size="lg" />
        <p className="text-sm sm:text-base text-[#9BA9C0] tracking-wide font-medium">
          Whatever you're looking for, we'll find a way.
        </p>
      </div>

      {/* ── Prominent Centered Search Bar ──────────────────── */}
      <div className="w-full max-w-[760px] space-y-4">
        <div className="relative group">
          <div className="absolute -inset-0.5 bg-gradient-to-r from-[#18BFFF]/20 to-[#65D96E]/20 rounded-2xl blur opacity-30 group-hover:opacity-75 transition duration-500" />
          <div className="relative flex items-center bg-[#10182A] border border-[#243149] focus-within:border-[#18BFFF] rounded-2xl shadow-2xl transition-all overflow-hidden">
            <Search className="w-5 h-5 text-[#9BA9C0] ml-4 flex-shrink-0" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSearchSubmit();
              }}
              placeholder="Search the web, repositories, research papers, and more…"
              disabled={isLoading}
              className="w-full bg-transparent px-4 py-4 sm:py-5 text-[#F5F7FC] placeholder-[#9BA9C0]/60 text-base focus:outline-none"
              autoFocus
            />
            <div className="pr-2 flex items-center gap-2">
              <button
                type="button"
                onClick={() => handleSearchSubmit()}
                disabled={isLoading || !query.trim()}
                className="bg-gradient-to-r from-[#18BFFF] to-[#65D96E] hover:opacity-95 disabled:opacity-30 disabled:cursor-not-allowed text-[#070B18] font-bold px-5 py-2.5 sm:py-3 rounded-xl shadow-lg transition-all cursor-pointer flex items-center gap-2 text-sm whitespace-nowrap"
              >
                {isLoading ? (
                  <div className="w-4 h-4 border-2 border-[#070B18]/30 border-t-[#070B18] rounded-full animate-spin" />
                ) : (
                  <Search className="w-4 h-4" />
                )}
                <span className="hidden sm:inline">{isLoading ? "Searching…" : "Search"}</span>
              </button>
            </div>
          </div>
        </div>

        {/* ── Category Filters / Mode Selector ──────────────── */}
        <div className="flex flex-wrap items-center justify-center gap-2 pt-1">
          {categories.map((cat) => {
            const Icon = cat.icon;
            const isSelected = categoryFilter === cat.id;
            return (
              <button
                key={cat.id}
                onClick={() => setCategoryFilter(cat.id)}
                className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs font-semibold transition cursor-pointer border ${
                  isSelected
                    ? 'bg-[#18BFFF]/10 border-[#18BFFF] text-[#18BFFF]'
                    : 'bg-[#10182A] border-[#243149] text-[#9BA9C0] hover:text-[#F5F7FC] hover:border-[#324466]'
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                <span>{cat.label}</span>
              </button>
            );
          })}
        </div>

        {/* ── Query Inspiration Chips ──────────────────────── */}
        <div className="flex flex-wrap items-center justify-center gap-2 pt-2">
          {sampleQueries.map((sq, i) => (
            <button
              key={i}
              type="button"
              onClick={() => {
                setQuery(sq);
                handleSearchSubmit(sq);
              }}
              className="text-xs text-[#9BA9C0] hover:text-[#18BFFF] bg-[#10182A]/70 hover:bg-[#10182A] border border-[#243149] hover:border-[#18BFFF]/30 rounded-xl px-3 py-1.5 transition cursor-pointer truncate max-w-xs"
            >
              {sq}
            </button>
          ))}
        </div>
      </div>

      {/* ── NOT SURE? Discovery Mode Entry Card ──────────────── */}
      <div className="w-full max-w-[760px] mt-8 bg-gradient-to-r from-[#10182A] via-[#0E1A33] to-[#10182A] border border-[#243149] hover:border-[#18BFFF]/50 rounded-2xl p-5 sm:p-6 shadow-xl transition space-y-3 group">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-start gap-3.5">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-[#18BFFF] to-[#65D96E] flex items-center justify-center text-[#070B18] flex-shrink-0 mt-0.5 shadow-md shadow-[#18BFFF]/20">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-bold text-sm sm:text-base text-[#F5F7FC] tracking-tight">
                  Not sure what to search?
                </h3>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-[#18BFFF]/10 text-[#18BFFF] border border-[#18BFFF]/30 uppercase tracking-wider">
                  Discovery Mode
                </span>
              </div>
              <p className="text-xs text-[#9BA9C0] mt-1 max-w-lg leading-relaxed">
                Tell ELORA what you're trying to find. AI will help you explore the right direction and execute real searches across all knowledge sources.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => onNavigateDiscovery(query)}
            className="bg-[#070B18] group-hover:bg-gradient-to-r group-hover:from-[#18BFFF] group-hover:to-[#65D96E] group-hover:text-[#070B18] border border-[#243149] group-hover:border-transparent text-[#18BFFF] font-bold px-4 py-2.5 rounded-xl text-xs transition cursor-pointer flex items-center gap-2 whitespace-nowrap self-stretch sm:self-auto justify-center shadow-lg"
          >
            <Sparkles className="w-4 h-4" />
            <span>Explore with AI</span>
          </button>
        </div>
      </div>

      {/* ── Compact Recent Searches / Quick Discovery ──────── */}
      {jobs.length > 0 && (
        <div className="w-full max-w-[760px] mt-10 pt-8 border-t border-[#243149]/60">
          <div className="flex items-center justify-between mb-3 px-1">
            <span className="text-[11px] font-bold uppercase tracking-wider text-[#9BA9C0]">
              Recent Investigations
            </span>
            <button
              onClick={onNavigateDashboard}
              className="text-xs text-[#18BFFF] hover:underline cursor-pointer"
            >
              View Dashboard & History &rarr;
            </button>
          </div>

          <div className="space-y-2">
            {jobs.slice(0, 4).map((j) => (
              <div
                key={j.id}
                onClick={() => onSelectJob(j.id)}
                className="flex items-center justify-between p-3 rounded-xl bg-[#10182A] border border-[#243149] hover:border-[#18BFFF]/40 transition cursor-pointer group"
              >
                <div className="flex items-center gap-3 min-w-0 pr-2">
                  <History className="w-4 h-4 text-[#9BA9C0] flex-shrink-0 group-hover:text-[#18BFFF] transition" />
                  <span className="text-xs sm:text-sm font-medium text-[#F5F7FC] group-hover:text-[#18BFFF] transition truncate">
                    {j.query}
                  </span>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <span className="text-[10px] text-[#9BA9C0]">
                    {j.total_results_count} results
                  </span>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase ${
                    j.status === 'completed' ? 'bg-[#65D96E]/10 text-[#65D96E] border border-[#65D96E]/30' :
                    j.status === 'running' ? 'bg-[#18BFFF]/10 text-[#18BFFF] border border-[#18BFFF]/30' :
                    'bg-[#243149] text-[#9BA9C0]'
                  }`}>
                    {j.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Footer Status Note ───────────────────────────────── */}
      <div className="mt-12 flex items-center gap-4 text-[11px] text-[#9BA9C0]/60">
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-[#65D96E]" />
          <span>{operationalSources.length} active engines connected</span>
        </div>
        <span>•</span>
        <span>Zero hallucinations · All evidence verified</span>
        <span>•</span>
        <button
          onClick={onNavigateAdvancedSearch}
          className="text-[#18BFFF] hover:underline cursor-pointer"
        >
          Advanced Filters
        </button>
      </div>
    </div>
  );
}

export default App;
