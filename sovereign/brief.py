"""A cited, extractive brief for any topic.

The brief is not a synthesis engine. It consults guardians, absorbs what they
return, ranks the units, and quotes them with provenance. Gaps and failed
sources are part of the output, not hidden.
"""

from __future__ import annotations

import time
from collections import Counter
from typing import Any

from .absorption import absorb
from .evidence import content_terms
from .models import utcnow

_HEADINGS = {
    "en": {
        "title": "Brief",
        "what": "What the sources say",
        "recurring": "Concepts that recur",
        "gaps": "Gaps and cautions",
        "evidence": "Evidence status",
        "coverage": "Topic coverage",
        "entailment": "Entailment",
        "language": "The quoted content stays in its original language.",
        "empty": "No units were returned, so there is nothing to quote.",
    },
    "ar": {
        "title": "موجز بحثي",
        "what": "ما تقوله المصادر",
        "recurring": "مفاهيم تتكرر",
        "gaps": "فجوات وتحذيرات",
        "evidence": "حالة الأدلة",
        "coverage": "تغطية الموضوع",
        "entailment": "الاستنتاج الدلالي",
        "language": "المحتوى المقتبس يبقى بلغته الأصلية.",
        "empty": "لم تُرجع المصادر أي وحدات، فلا يوجد ما يُقتبس.",
    },
}


def _unit_row(unit) -> dict[str, Any]:
    return {
        "title": unit.title,
        "source": unit.provenance.source,
        "url": unit.provenance.url,
        "summary": unit.summary,
        "retrieved_at": unit.provenance.retrieved_at,
        "confidence": unit.provenance.confidence,
    }


def _markdown(query: str, lang: str, units: list, agreements: list[str], gaps: list[str], coverage: float) -> str:
    h = _HEADINGS[lang]
    lines = [
        f"# {h['title']}: {query}",
        "",
        f"_{'Generated' if lang == 'en' else 'تم التوليد'} {utcnow()} · "
        f"{'extractive and cited; no semantic synthesis' if lang == 'en' else 'اقتباس مع مصادر، بلا تركيب دلالي'}._",
        "",
        f"## {h['what']}",
        "",
    ]
    if not units:
        lines.append(h["empty"])
    for unit in units:
        summary = (unit.summary or "").strip()
        if len(summary) > 320:
            summary = summary[:320].rstrip() + "…"
        date = f", {unit.provenance.retrieved_at}" if unit.provenance.retrieved_at else ""
        link = f"[{unit.provenance.source}]({unit.provenance.url})" if unit.provenance.url else unit.provenance.source
        lines.append(f"- **{unit.title}** — {summary or '(no summary)'} ({link}{date})")
    lines += ["", f"## {h['recurring']}", ""]
    lines.extend([f"- {concept}" for concept in agreements] or ["- (none)"])
    lines += ["", f"## {h['gaps']}", ""]
    lines.extend([f"- {gap}" for gap in gaps] or ["- (none)"])
    lines += [
        "",
        f"## {h['evidence']}",
        "",
        f"- {h['coverage']}: {coverage:.0%}",
        f"- {h['entailment']}: {'not attempted' if lang == 'en' else 'لم يُحاول'} (`entails=false`)",
        f"- {h['language']}",
        "",
    ]
    return "\n".join(lines)


def build_brief(
    engine,
    query: str,
    *,
    limit: int = 5,
    sources: list[str] | None = None,
    lang: str = "en",
    deadline_s: float = 12.0,
) -> dict[str, Any]:
    started = time.monotonic()
    lang = "ar" if lang == "ar" else "en"
    h = _HEADINGS[lang]
    consultation = engine.guardians.consult(
        query, limit=limit, sources=sources, deadline_s=deadline_s
    )
    absorbed = absorb(engine.store, consultation.units)
    ranked = engine.store.search_knowledge(query, k=limit)
    units = [unit for unit, _score in ranked]

    terms = content_terms(query)
    union = set()
    for unit in units:
        union |= content_terms(unit.searchable_text())
    coverage = len(terms & union) / len(terms) if terms else 0.0

    concept_counts: Counter[str] = Counter()
    for unit in units:
        for concept in set(unit.concepts):
            concept_counts[concept.strip().lower()] += 1
    agreements = [name for name, count in concept_counts.most_common(8) if count >= 2]

    failed = [name for name, status in consultation.sources.items() if status != "ok"]
    gaps: list[str] = []
    if not units:
        gaps.append(h["empty"])
    elif len(units) < limit:
        gaps.append(
            f"Only {len(units)} of {limit} requested units were available."
            if lang == "en"
            else f"توفرت {len(units)} فقط من {limit} وحدات مطلوبة."
        )
    if failed:
        gaps.append(
            f"Sources that did not answer: {', '.join(sorted(failed))}."
            if lang == "en"
            else f"مصادر لم تُجب: {', '.join(sorted(failed))}."
        )
    if coverage < 0.5:
        gaps.append(
            f"The query terms are only {coverage:.0%} covered by the selected units."
            if lang == "en"
            else f"مصطلحات الاستعلام مغطاة بنسبة {coverage:.0%} فقط في الوحدات المختارة."
        )
    gaps.append(
        "This brief quotes and cites; it does not infer, translate, or verify truth."
        if lang == "en"
        else "هذا الموجز يقتبس ويوثّق؛ لا يستنتج ولا يترجم ولا يتحقق من الصحة."
    )

    dates = [unit.provenance.retrieved_at for unit in units if unit.provenance.retrieved_at]
    return {
        "ok": bool(units),
        "query": query,
        "lang": lang,
        "units": [_unit_row(unit) for unit in units],
        "absorbed": absorbed,
        "agreements": agreements,
        "gaps": gaps,
        "sources": consultation.sources,
        "coverage": round(coverage, 3),
        "newest_unit_date": max(dates) if dates else None,
        "markdown": _markdown(query, lang, units, agreements, gaps, coverage),
        "duration_s": round(time.monotonic() - started, 3),
        "generated_at": utcnow(),
    }
