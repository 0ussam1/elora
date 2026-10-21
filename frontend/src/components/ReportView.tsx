import React from 'react';
import { 
  FileText, AlertTriangle, Lightbulb, CheckCircle2, 
  Layers, ExternalLink, ShieldAlert
} from 'lucide-react';
import type { ResearchReport } from '../types';

interface ReportViewProps {
  report: ResearchReport;
  query: string;
}

export const ReportView: React.FC<ReportViewProps> = ({ report, query }) => {
  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Report Header */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-3">
        <div className="flex items-center gap-2 text-xs font-semibold text-sky-400 uppercase tracking-wider">
          <FileText className="w-4 h-4" />
          <span>Unified Intelligence Report</span>
        </div>
        <h1 className="text-2xl font-bold text-white tracking-tight">
          Research Findings: "{query}"
        </h1>
        <p className="text-xs text-slate-400">
          Generated on {new Date(report.created_at).toLocaleString()} • Rigorously verified with zero synthetic citations
        </p>

        {/* Collection Stats Bar */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-4 border-t border-slate-800">
          <div className="bg-slate-950/60 p-3 rounded-xl border border-slate-800/80">
            <span className="text-[11px] text-slate-400 block">Total Analyzed</span>
            <span className="text-xl font-bold text-white">{report.collection_stats.total_collected}</span>
          </div>
          <div className="bg-slate-950/60 p-3 rounded-xl border border-slate-800/80">
            <span className="text-[11px] text-slate-400 block">Unique Sources</span>
            <span className="text-xl font-bold text-emerald-400">{Object.keys(report.collection_stats.sources || {}).length}</span>
          </div>
          <div className="bg-slate-950/60 p-3 rounded-xl border border-slate-800/80">
            <span className="text-[11px] text-slate-400 block">Mean Relevance</span>
            <span className="text-xl font-bold text-sky-400">{Math.round(report.collection_stats.avg_relevance * 100)}%</span>
          </div>
          <div className="bg-slate-950/60 p-3 rounded-xl border border-slate-800/80">
            <span className="text-[11px] text-slate-400 block">Problem Patterns</span>
            <span className="text-xl font-bold text-amber-400">{report.recurring_problems.length}</span>
          </div>
        </div>
      </div>

      {/* 1. Executive Summary */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-md space-y-3">
        <h2 className="text-lg font-semibold text-white flex items-center gap-2">
          <span>1. Executive Summary</span>
        </h2>
        <p className="text-slate-300 text-sm leading-relaxed bg-slate-950/40 p-4 rounded-xl border border-slate-800/60">
          {report.executive_summary}
        </p>
      </div>

      {/* 2. Key Findings & Grounded Evidence */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-md space-y-4">
        <h2 className="text-lg font-semibold text-white flex items-center gap-2">
          <CheckCircle2 className="w-5 h-5 text-emerald-400" />
          <span>2. Synthesized Findings & Traceable Evidence</span>
        </h2>
        <div className="space-y-3">
          {report.main_findings.map((item, idx) => (
            <div key={idx} className="bg-slate-950/60 p-4 rounded-xl border border-slate-800/80 space-y-2">
              <h3 className="font-semibold text-sm text-slate-100">{item.theme}</h3>
              <p className="text-xs text-slate-300 leading-relaxed">{item.description}</p>
              
              {/* Evidence Link */}
              {item.evidence_sources && item.evidence_sources.map(ev => (
                <div key={ev.id} className="pt-2 flex items-center gap-2 text-xs">
                  <span className="text-slate-500 font-medium">Evidence:</span>
                  <a
                    href={ev.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sky-400 hover:underline flex items-center gap-1 font-medium truncate max-w-md"
                  >
                    <span>{ev.title}</span>
                    <ExternalLink className="w-3 h-3 flex-shrink-0" />
                  </a>
                  <span className="text-[10px] bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded uppercase">
                    {ev.source_name}
                  </span>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>

      {/* 3. Recurring Problems / Pain Points */}
      {report.recurring_problems.length > 0 && (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-md space-y-4">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-amber-400" />
            <span>3. Recurring Problems & Bottlenecks</span>
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {report.recurring_problems.map((prob, idx) => (
              <div key={idx} className="bg-slate-950/60 p-4 rounded-xl border border-amber-900/30 flex flex-col justify-between space-y-3">
                <div className="space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-amber-400 font-semibold uppercase tracking-wider text-[10px]">
                      Issue Pattern #{idx + 1}
                    </span>
                    <span className="text-[10px] text-slate-400 bg-slate-900 px-2 py-0.5 rounded">
                      {prob.source_name}
                    </span>
                  </div>
                  <h3 className="font-semibold text-xs text-slate-200 line-clamp-2">{prob.problem}</h3>
                </div>

                <a
                  href={prob.evidence_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-slate-400 hover:text-sky-400 flex items-center gap-1 truncate pt-2 border-t border-slate-800/80"
                >
                  <span className="truncate">{prob.evidence_title}</span>
                  <ExternalLink className="w-3 h-3 flex-shrink-0" />
                </a>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 4. Existing Solutions & Workarounds */}
      {report.existing_solutions.length > 0 && (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-md space-y-4">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <Layers className="w-5 h-5 text-indigo-400" />
            <span>4. Existing Solutions & Workarounds</span>
          </h2>
          <div className="space-y-3">
            {report.existing_solutions.map((sol, idx) => (
              <div key={idx} className="bg-slate-950/60 p-3.5 rounded-xl border border-slate-800/80 flex items-start justify-between gap-4">
                <div className="space-y-1">
                  <h3 className="font-semibold text-xs text-slate-200">{sol.solution_title}</h3>
                  <p className="text-xs text-slate-400 line-clamp-2">{sol.summary}</p>
                </div>
                <a
                  href={sol.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-sky-400 hover:underline flex items-center gap-1 flex-shrink-0"
                >
                  <span>Inspect</span>
                  <ExternalLink className="w-3 h-3" />
                </a>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 5. Potential Opportunities */}
      {report.potential_opportunities.length > 0 && (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-md space-y-4">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <Lightbulb className="w-5 h-5 text-yellow-400" />
            <span>5. Potential Opportunities & SaaS/Tool Angles</span>
          </h2>
          <div className="space-y-3">
            {report.potential_opportunities.map((opp, idx) => (
              <div key={idx} className="bg-gradient-to-r from-sky-950/30 to-indigo-950/30 p-4 rounded-xl border border-sky-800/40 space-y-1.5">
                <h3 className="font-semibold text-xs text-sky-300">{opp.opportunity}</h3>
                <p className="text-xs text-slate-300">{opp.actionable_insight}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 6. Limitations */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-md space-y-3">
        <h2 className="text-base font-semibold text-slate-300 flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 text-slate-400" />
          <span>Research Methodology & Limitations</span>
        </h2>
        <ul className="list-disc list-inside space-y-1 text-xs text-slate-400">
          {report.limitations.map((lim, idx) => (
            <li key={idx}>{lim}</li>
          ))}
        </ul>
      </div>
    </div>
  );
};
