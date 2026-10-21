import React from 'react';
import { 
  Activity, Database, ShieldCheck, FileText, ArrowUpRight, Trash2, Search
} from 'lucide-react';
import type { ResearchJob, SourceInfo } from '../types';

interface DashboardProps {
  jobs: ResearchJob[];
  sources: SourceInfo[];
  onSelectJob: (jobId: string) => void;
  onNavigateSearch: () => void;
  onDeleteJob: (jobId: string) => void;
  onClearHistory: () => void;
}

export const Dashboard: React.FC<DashboardProps> = ({ 
  jobs, 
  sources, 
  onSelectJob, 
  onNavigateSearch,
  onDeleteJob,
  onClearHistory
}) => {
  const completedJobs = jobs.filter(j => j.status === 'completed');
  const totalResults = jobs.reduce((sum, j) => sum + (j.total_results_count || 0), 0);
  const operationalSources = sources.filter(s => s.health_status === 'operational' || s.health_status === 'connected').length;

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="bg-gradient-to-r from-[#10182A] via-[#0E1A33] to-[#10182A] border border-[#243149] rounded-2xl p-6 sm:p-7 shadow-xl flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[11px] font-bold tracking-widest text-[#18BFFF] uppercase">Operational Overview</span>
          </div>
          <h1 className="text-2xl font-bold text-[#F5F7FC] tracking-tight">ELORA Intelligence Operations</h1>
          <p className="text-[#9BA9C0] mt-1 max-w-2xl text-xs sm:text-sm">
            Autonomous multi-source research across technical communities, web search, knowledge graphs, academic repos, and archives with zero fabricated citations.
          </p>
        </div>
        <button
          onClick={onNavigateSearch}
          className="flex items-center gap-2 bg-gradient-to-r from-[#18BFFF] to-[#65D96E] hover:opacity-95 text-[#070B18] font-bold px-5 py-2.5 rounded-xl shadow-lg shadow-[#18BFFF]/10 transition-all cursor-pointer whitespace-nowrap text-sm"
        >
          <Search className="w-4 h-4" />
          <span>New Investigation</span>
        </button>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-[#10182A] border border-[#243149] rounded-xl p-5 hover:border-[#324466] transition">
          <div className="flex items-center justify-between text-[#9BA9C0]">
            <span className="text-xs uppercase font-semibold tracking-wider">Research Operations</span>
            <Activity className="w-5 h-5 text-[#18BFFF]" />
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-[#F5F7FC]">{jobs.length}</span>
            <span className="text-xs text-[#65D96E] font-medium">({completedJobs.length} completed)</span>
          </div>
        </div>

        <div className="bg-[#10182A] border border-[#243149] rounded-xl p-5 hover:border-[#324466] transition">
          <div className="flex items-center justify-between text-[#9BA9C0]">
            <span className="text-xs uppercase font-semibold tracking-wider">Indexed Evidence</span>
            <Database className="w-5 h-5 text-[#65D96E]" />
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-[#F5F7FC]">{totalResults}</span>
            <span className="text-xs text-[#9BA9C0]">verified records</span>
          </div>
        </div>

        <div className="bg-[#10182A] border border-[#243149] rounded-xl p-5 hover:border-[#324466] transition">
          <div className="flex items-center justify-between text-[#9BA9C0]">
            <span className="text-xs uppercase font-semibold tracking-wider">Connected Engines</span>
            <ShieldCheck className="w-5 h-5 text-[#18BFFF]" />
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-[#F5F7FC]">{operationalSources}</span>
            <span className="text-xs text-[#9BA9C0]">/ {sources.length} active</span>
          </div>
        </div>

        <div className="bg-[#10182A] border border-[#243149] rounded-xl p-5 hover:border-[#324466] transition">
          <div className="flex items-center justify-between text-[#9BA9C0]">
            <span className="text-xs uppercase font-semibold tracking-wider">Report Synthesis</span>
            <FileText className="w-5 h-5 text-amber-400" />
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-[#F5F7FC]">{completedJobs.length}</span>
            <span className="text-xs text-[#9BA9C0]">grounded reports</span>
          </div>
        </div>
      </div>

      {/* Recent Investigations & Sources Overview */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-[#10182A] border border-[#243149] rounded-xl p-5 sm:p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-base font-semibold text-[#F5F7FC]">Recent Research Investigations</h2>
              <span className="text-xs text-[#9BA9C0] font-normal">Click any item to explore full evidence & synthesis</span>
            </div>
            {jobs.length > 0 && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  if (confirm("Are you sure you want to delete ALL research history?")) {
                    onClearHistory();
                  }
                }}
                className="flex items-center gap-1.5 text-xs text-rose-400 hover:text-rose-300 bg-rose-950/30 hover:bg-rose-950/60 border border-rose-900/40 px-2.5 py-1.5 rounded-lg transition cursor-pointer"
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>Clear All History</span>
              </button>
            )}
          </div>
          {jobs.length === 0 ? (
            <div className="py-14 text-center text-[#9BA9C0] space-y-3">
              <Search className="w-8 h-8 text-[#9BA9C0]/40 mx-auto" />
              <p className="text-sm">No investigations yet. Start your first research task above!</p>
            </div>
          ) : (
            <div className="divide-y divide-[#243149]">
              {jobs.slice(0, 15).map((job) => (
                <div 
                  key={job.id}
                  onClick={() => onSelectJob(job.id)}
                  className="py-3.5 px-3 -mx-3 rounded-lg hover:bg-[#070B18]/70 cursor-pointer transition flex items-center justify-between group"
                >
                  <div className="space-y-1 pr-4 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-[#F5F7FC] group-hover:text-[#18BFFF] transition text-sm truncate">
                        {job.query}
                      </span>
                      <span className={`text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase tracking-wider ${
                        job.status === 'completed' ? 'bg-[#65D96E]/10 text-[#65D96E] border border-[#65D96E]/30' :
                        job.status === 'running' ? 'bg-[#18BFFF]/10 text-[#18BFFF] border border-[#18BFFF]/30 animate-pulse' :
                        'bg-[#243149] text-[#9BA9C0]'
                      }`}>
                        {job.status}
                      </span>
                    </div>
                    <div className="text-xs text-[#9BA9C0] flex items-center gap-3">
                      <span>Mode: <strong className="text-[#F5F7FC] capitalize">{job.mode.replace('_', ' ')}</strong></span>
                      <span>•</span>
                      <span>{job.total_results_count} results</span>
                      <span>•</span>
                      <span>{new Date(job.created_at).toLocaleDateString()}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      title="Delete this search"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (confirm(`Delete research for: "${job.query}"?`)) {
                          onDeleteJob(job.id);
                        }
                      }}
                      className="p-1.5 rounded-md text-[#9BA9C0] hover:text-rose-400 hover:bg-rose-950/40 transition opacity-0 group-hover:opacity-100 cursor-pointer"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                    <ArrowUpRight className="w-4 h-4 text-[#9BA9C0] group-hover:text-[#18BFFF] transition" />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Source Health Panel */}
        <div className="bg-[#10182A] border border-[#243149] rounded-xl p-5 sm:p-6 flex flex-col justify-between">
          <div>
            <h2 className="text-base font-semibold text-[#F5F7FC] mb-1">Connector Status</h2>
            <p className="text-xs text-[#9BA9C0] mb-4">Official APIs and compliant access points.</p>
            <div className="space-y-2.5 max-h-[460px] overflow-y-auto pr-1">
              {sources.map(src => {
                const isGood = src.health_status === 'operational' || src.health_status === 'connected';
                const isRate = src.health_status === 'rate_limited';
                const isWarn = !isGood && !isRate && src.health_status !== 'error';

                const badgeColor = isGood ? 'bg-[#65D96E]/10 text-[#65D96E] border-[#65D96E]/30' :
                  isRate ? 'bg-amber-950/60 text-amber-300 border-amber-800/60' :
                  isWarn ? 'bg-amber-950/60 text-amber-400 border-amber-800/60' :
                  'bg-rose-950/60 text-rose-400 border-rose-800/60';

                return (
                  <div key={src.id} className="flex flex-col gap-1 text-xs p-2.5 rounded-lg bg-[#070B18] border border-[#243149]">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-[#F5F7FC] block truncate">{src.name}</span>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${badgeColor}`}>
                        {src.health_status.replace('_', ' ')}
                      </span>
                    </div>
                    {src.message && (
                      <span className="text-[10px] text-[#9BA9C0] truncate" title={src.message}>
                        {src.message}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
          <div className="mt-4 pt-4 border-t border-[#243149] text-[11px] text-[#9BA9C0]/70">
            Zero hallucinations: All reported evidence is linked directly to live sources.
          </div>
        </div>
      </div>
    </div>
  );
};
