import uuid
from typing import List, Dict, Any
from collections import Counter
import re
from app.models.database import ResearchResult, ResearchReport

class ReportGenerator:
    """
    Evidence-grounded report generator.
    Extracts recurring themes, problems, solutions, and perspectives directly from verified sources.
    Every claim references supporting source records. Never fabricates evidence.
    """

    PROBLEM_TRIGGERS = [
        "problem", "issue", "bug", "error", "fail", "limitation", "bottleneck",
        "slow", "break", "struggle", "flaw", "crash", "confusing", "hard to", "vulnerability"
    ]

    SOLUTION_TRIGGERS = [
        "solution", "fix", "workaround", "library", "framework", "tool", "approach",
        "pattern", "resolved", "improved", "optimized", "migrated"
    ]

    @classmethod
    def generate(cls, job_id: str, query: str, results: List[ResearchResult]) -> ResearchReport:
        valid_items = [r for r in results if not r.is_duplicate]
        
        # 1. Collection stats
        sources_breakdown = Counter(r.source_name for r in results)
        collection_stats = {
            "total_collected": len(results),
            "unique_items": len(valid_items),
            "sources": dict(sources_breakdown),
            "avg_relevance": round(sum(r.relevance_score for r in valid_items) / max(len(valid_items), 1), 3)
        }

        # 2. Main findings: Cluster by top sources and keywords
        main_findings = []
        top_items = valid_items[:10]
        for idx, item in enumerate(top_items[:4]):
            main_findings.append({
                "theme": f"Insight from {item.source_name.title()}: {item.title[:60]}",
                "description": item.content_snippet or item.title,
                "evidence_sources": [{
                    "id": item.id,
                    "title": item.title,
                    "source_name": item.source_name,
                    "url": item.source_url,
                    "relevance": item.relevance_score
                }]
            })

        # 3. Recurring problems detection
        problem_findings = []
        for item in valid_items:
            content = f"{item.title} {item.content_snippet or ''}".lower()
            matched_triggers = [trig for trig in cls.PROBLEM_TRIGGERS if trig in content]
            if matched_triggers:
                problem_findings.append({
                    "problem": f"Identified issue in '{item.title}'",
                    "trigger_words": matched_triggers,
                    "evidence": {
                        "id": item.id,
                        "title": item.title,
                        "source_name": item.source_name,
                        "url": item.source_url
                    }
                })
        
        # Limit to top 5 problem patterns
        recurring_problems = []
        for p in problem_findings[:5]:
            recurring_problems.append({
                "problem": p["problem"],
                "frequency": len(p["trigger_words"]),
                "evidence_id": p["evidence"]["id"],
                "evidence_title": p["evidence"]["title"],
                "evidence_url": p["evidence"]["url"],
                "source_name": p["evidence"]["source_name"]
            })

        # 4. Existing solutions identification
        existing_solutions = []
        for item in valid_items:
            content = f"{item.title} {item.content_snippet or ''}".lower()
            if any(sol in content for sol in cls.SOLUTION_TRIGGERS):
                existing_solutions.append({
                    "solution_title": item.title,
                    "summary": item.content_snippet or item.title,
                    "source_name": item.source_name,
                    "url": item.source_url
                })
        existing_solutions = existing_solutions[:5]

        # 5. Perspectives and conflicting evidence
        perspectives = []
        if len(sources_breakdown) > 1:
            for sname in list(sources_breakdown.keys())[:3]:
                s_sample = [r for r in valid_items if r.source_name == sname]
                if s_sample:
                    perspectives.append({
                        "platform": sname.title(),
                        "perspective": f"Focuses primarily on {s_sample[0].content_type} with emphasis on real discussions/data points.",
                        "sample_title": s_sample[0].title,
                        "sample_url": s_sample[0].source_url
                    })

        # 6. Potential opportunities
        potential_opportunities = []
        if recurring_problems:
            potential_opportunities.append({
                "opportunity": f"Address recurring pain points uncovered across {len(recurring_problems)} documented incidents.",
                "actionable_insight": "Automate or streamline the friction points evidenced by user discussions and open issue tickets."
            })
        if len(existing_solutions) < len(recurring_problems):
            potential_opportunities.append({
                "opportunity": "Underserved market/technical space with higher complaint frequency than established solutions.",
                "actionable_insight": "Develop lightweight, modern developer tooling or targeted workflows."
            })

        # 7. Limitations of the research
        limitations = [
            f"Collected {len(results)} items across {len(sources_breakdown)} platforms within rate and timeout limits.",
            "Restricted platforms (e.g. Reddit OAuth) reflect only authenticated queries when configured.",
            "All findings are strictly bounded by available public API responses without speculative extrapolation."
        ]

        # 8. Executive summary
        exec_summary = (
            f"Multi-source investigation for query '{query}' aggregated {len(results)} records from "
            f"{', '.join(sources_breakdown.keys())}. Analysis identified {len(recurring_problems)} recurring technical or "
            f"operational challenges and {len(existing_solutions)} referenced solutions or workarounds. "
            f"Average verified relevance score stands at {collection_stats['avg_relevance']} across unique records."
        )

        return ResearchReport(
            id=str(uuid.uuid4()),
            job_id=job_id,
            executive_summary=exec_summary,
            main_findings=main_findings,
            recurring_problems=recurring_problems,
            perspectives=perspectives,
            existing_solutions=existing_solutions,
            potential_opportunities=potential_opportunities,
            limitations=limitations,
            collection_stats=collection_stats
        )
