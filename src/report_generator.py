"""HTML report generator.

Renders a standalone, self-contained HTML file using Jinja2 + Tailwind CSS
(loaded from CDN).  Sections: New → Price Drop → Active → Delisted.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path

from jinja2 import Environment, BaseLoader

from .diff_engine import DiffEntry

_TEMPLATE = """\
{# ── Card macro ─────────────────────────────────────────────── #}
{% macro card(entry, kind) %}
{% set prop = entry.property %}
{% set old_price = entry.old_price %}
{% set region = prop.address.split('-')[0] if prop.address and '-' in prop.address else (prop.address or '') %}
<a href="{{ prop.link }}" target="_blank" rel="noopener"
   class="card-item bg-white rounded-2xl shadow-sm hover:shadow-md transition-all duration-200 overflow-hidden flex flex-col{% if kind == 'delisted' %} opacity-40{% endif %}"
   data-region="{{ region }}"
   data-elevator="{{ 'true' if prop.has_elevator else 'false' }}"
   data-status="{{ kind }}">

  <!-- image -->
  {% if prop.image_url %}
  <img src="{{ prop.image_url }}" alt="{{ prop.title }}"
       class="card-img" loading="lazy" onerror="this.style.display='none'">
  {% else %}
  <div class="card-img flex items-center justify-center bg-slate-100 text-slate-300 text-5xl">🏠</div>
  {% endif %}

  <div class="p-4 flex flex-col gap-2 flex-1">
    <!-- status badge -->
    <div class="flex items-center justify-between">
      {% if kind == "new" %}
      <span class="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200">
        <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>新上架
      </span>
      {% elif kind == "drop" %}
      <span class="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full bg-amber-50 text-amber-700 ring-1 ring-amber-200">
        ↓ 降價
      </span>
      {% elif kind == "delisted" %}
      <span class="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full bg-slate-100 text-slate-500 ring-1 ring-slate-200">
        已下架
      </span>
      {% else %}
      <span class="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full bg-blue-50 text-blue-600 ring-1 ring-blue-200">
        在架中
      </span>
      {% endif %}
      <span class="text-xs text-slate-400 font-medium">{{ prop.platform }}</span>
    </div>

    <!-- price -->
    <div class="mt-0.5">
      <span class="text-2xl font-bold tracking-tight {% if kind == 'delisted' %}text-slate-400{% else %}text-slate-900{% endif %}">
        NT${{ "{:,}".format(prop.price) }}
      </span>
      <span class="text-slate-400 text-sm ml-0.5">/月</span>
      {% if old_price %}
      <div class="flex items-center gap-1.5 mt-1">
        <span class="text-xs text-slate-400 line-through">NT${{ "{:,}".format(old_price) }}</span>
        <span class="text-xs font-semibold text-red-500 bg-red-50 px-1.5 py-0.5 rounded">
          ↓ NT${{ "{:,}".format(old_price - prop.price) }}
        </span>
      </div>
      {% endif %}
    </div>

    <!-- title -->
    <p class="text-sm font-medium text-slate-700 leading-snug line-clamp-2">{{ prop.title }}</p>

    <!-- meta -->
    <div class="flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-400 mt-auto pt-3 border-t border-slate-100">
      {% if prop.floor %}<span>🏢 {{ prop.floor }}</span>{% endif %}
      {% if prop.area %}<span>📐 {{ prop.area }} 坪</span>{% endif %}
      {% if prop.layout %}<span>🛏 {{ prop.layout }}</span>{% endif %}
      {% if prop.address %}<span class="truncate max-w-full">📍 {{ prop.address }}</span>{% endif %}
    </div>
  </div>
</a>
{% endmacro %}

<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>租房監控報表 {{ report_date }}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    .card-img { object-fit: cover; height: 192px; width: 100%; }

    /* region tags */
    .region-tag { cursor: pointer; transition: all .15s; }
    .region-tag.active {
      background: #4f46e5; color: white;
      box-shadow: 0 1px 3px rgba(79,70,229,.35);
    }

    /* building tabs */
    .bld-tab { cursor: pointer; transition: all .2s; position: relative; }
    .bld-tab.active {
      background: white; color: #1e293b;
      box-shadow: 0 -1px 0 0 white, 0 0 0 1px #e2e8f0;
      border-bottom-color: white !important;
    }
    .bld-tab:not(.active) { color: #94a3b8; }

    /* card hidden by filter */
    .card-item.hidden-by-filter { display: none !important; }

    /* section visibility */
    .status-section { }
    .status-section.empty-section { display: none; }

    /* empty state */
    .filter-empty { display: none; }
    .filter-empty.visible { display: flex; }
  </style>
</head>
<body class="bg-slate-50 min-h-screen">

  <!-- ══ HEADER ══════════════════════════════════════════════════ -->
  <div class="bg-white border-b border-slate-200 sticky top-0 z-20 shadow-sm">
    <div class="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between gap-4 flex-wrap">
      <div>
        <h1 class="text-xl font-bold text-slate-900 leading-none">租房監控報表</h1>
        <p class="text-xs text-slate-400 mt-0.5">{{ report_date }}</p>
      </div>
      <!-- stat pills -->
      <div class="flex items-center gap-2 flex-wrap">
        <span class="inline-flex items-center gap-1.5 bg-emerald-50 text-emerald-700 text-sm font-semibold px-3 py-1.5 rounded-full ring-1 ring-emerald-200">
          <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
          新上架 {{ new_count }}
        </span>
        <span class="inline-flex items-center gap-1.5 bg-amber-50 text-amber-700 text-sm font-semibold px-3 py-1.5 rounded-full ring-1 ring-amber-200">
          ↓ 降價 {{ drop_count }}
        </span>
        <span class="inline-flex items-center gap-1.5 bg-blue-50 text-blue-700 text-sm font-semibold px-3 py-1.5 rounded-full ring-1 ring-blue-200">
          在架中 {{ active_count }}
        </span>
        <span class="inline-flex items-center gap-1.5 bg-slate-100 text-slate-500 text-sm font-semibold px-3 py-1.5 rounded-full ring-1 ring-slate-200">
          已下架 {{ delisted_count }}
        </span>
      </div>
    </div>
  </div>

  <div class="max-w-6xl mx-auto px-6">

    <!-- ── 篩選條件小字列 ── -->
    {% if config %}
    <div class="flex flex-wrap items-center gap-2 py-3 border-b border-slate-100 text-xs text-slate-400">
      <span class="font-medium text-slate-500">篩選條件</span>
      {% if config.target_cities %}
      <span>{{ config.target_cities | join("、") }}</span>
      {% endif %}
      <span class="text-slate-200">|</span>
      <span>NT${{ "{:,}".format(config.price_min) }}–{{ "{:,}".format(config.price_max) }}/月</span>
      {% if config.floor_min and config.floor_min > 1 %}
      <span class="text-slate-200">|</span><span>{{ config.floor_min }}F 以上</span>
      {% endif %}
      {% if config.area_min and config.area_min > 0 %}
      <span class="text-slate-200">|</span>
      <span>{{ config.area_min | int if config.area_min == (config.area_min | int) else config.area_min }} 坪以上</span>
      {% endif %}
      {% if config.exclude_rooftop_addition %}<span class="text-slate-200">|</span><span>排除頂加</span>{% endif %}
      {% if config.exclude_top_floor %}<span class="text-slate-200">|</span><span>排除頂樓</span>{% endif %}
    </div>
    {% endif %}

    <!-- ══ FILTER CONTROLS ══════════════════════════════════════ -->
    <div class="py-5 space-y-4">

      <!-- Layer 1: Region tags -->
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-xs font-semibold text-slate-400 uppercase tracking-wide w-8 shrink-0">區域</span>
        <button class="region-tag active text-xs font-semibold px-3.5 py-1.5 rounded-full bg-slate-100 text-slate-600"
                data-region="all">全部</button>
        {% for region in regions %}
        <button class="region-tag text-xs font-semibold px-3.5 py-1.5 rounded-full bg-slate-100 text-slate-600"
                data-region="{{ region }}">{{ region }}</button>
        {% endfor %}
      </div>

      <!-- Layer 2: Building type tabs -->
      <div class="flex items-end gap-0 border-b border-slate-200">
        <span class="text-xs font-semibold text-slate-400 uppercase tracking-wide w-8 shrink-0 pb-2.5">類型</span>
        <button class="bld-tab active text-sm font-semibold px-5 py-2.5 rounded-t-lg border border-slate-200 -mb-px"
                data-bld="elevator">
          🏢 電梯大樓／華廈
          <span id="count-elevator" class="ml-1.5 text-xs font-normal opacity-60"></span>
        </button>
        <button class="bld-tab text-sm font-semibold px-5 py-2.5 rounded-t-lg border border-transparent -mb-px ml-1"
                data-bld="walkup">
          🏠 公寓
          <span id="count-walkup" class="ml-1.5 text-xs font-normal opacity-60"></span>
        </button>
      </div>
    </div>

    <!-- ══ CARDS ════════════════════════════════════════════════ -->
    <div id="card-container" class="space-y-10 pb-16">

      {% macro section(entries, kind, label, badge_class) %}
      {% if entries %}
      <section class="status-section" data-kind="{{ kind }}">
        <h2 class="flex items-center gap-2 text-base font-semibold text-slate-700 mb-4">
          {{ label }}
          <span class="section-count text-xs font-semibold px-2 py-0.5 rounded-full {{ badge_class }}"></span>
        </h2>
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {% for entry in entries %}{{ card(entry, kind) }}{% endfor %}
        </div>
      </section>
      {% endif %}
      {% endmacro %}

      {{ section(new_entries,      "new",      "新上架",  "bg-emerald-50 text-emerald-700") }}
      {{ section(drop_entries,     "drop",     "降價",    "bg-amber-50 text-amber-700") }}
      {{ section(active_entries,   "active",   "在架中",  "bg-blue-50 text-blue-700") }}
      {{ section(delisted_entries, "delisted", "已下架",  "bg-slate-100 text-slate-500") }}

      <!-- empty state -->
      <div class="filter-empty flex-col items-center justify-center py-24 text-slate-300" id="empty-state">
        <div class="text-6xl mb-4">🏙</div>
        <p class="text-lg font-medium">此條件下無物件</p>
      </div>
    </div>

  </div>

  <script>
  (function() {
    var currentRegion = 'all';
    var currentBld    = 'elevator';

    var allCards    = Array.from(document.querySelectorAll('.card-item'));
    var sections    = Array.from(document.querySelectorAll('.status-section'));
    var emptyState  = document.getElementById('empty-state');

    function applyFilter() {
      var visible = 0;

      allCards.forEach(function(card) {
        var regionOk = currentRegion === 'all' || card.dataset.region === currentRegion;
        var elevOk   = currentBld === 'elevator'
                       ? card.dataset.elevator === 'true'
                       : card.dataset.elevator === 'false';

        if (regionOk && elevOk) {
          card.classList.remove('hidden-by-filter');
          visible++;
        } else {
          card.classList.add('hidden-by-filter');
        }
      });

      // update section visibility + counts
      sections.forEach(function(sec) {
        var kind    = sec.dataset.kind;
        var showing = sec.querySelectorAll('.card-item:not(.hidden-by-filter)').length;
        var badge   = sec.querySelector('.section-count');
        if (badge) badge.textContent = showing + ' 筆';
        sec.classList.toggle('empty-section', showing === 0);
      });

      // update tab counts
      ['elevator','walkup'].forEach(function(bld) {
        var count = allCards.filter(function(c) {
          var regionOk = currentRegion === 'all' || c.dataset.region === currentRegion;
          var elevOk   = bld === 'elevator' ? c.dataset.elevator === 'true' : c.dataset.elevator === 'false';
          var notDelist = c.dataset.status !== 'delisted';
          return regionOk && elevOk && notDelist;
        }).length;
        var el = document.getElementById('count-' + bld);
        if (el) el.textContent = count + ' 筆';
      });

      // empty state
      emptyState.classList.toggle('visible', visible === 0);
    }

    // region tags
    document.querySelectorAll('.region-tag').forEach(function(btn) {
      btn.addEventListener('click', function() {
        document.querySelectorAll('.region-tag').forEach(function(b) { b.classList.remove('active'); });
        btn.classList.add('active');
        currentRegion = btn.dataset.region;
        applyFilter();
      });
    });

    // building tabs
    document.querySelectorAll('.bld-tab').forEach(function(btn) {
      btn.addEventListener('click', function() {
        document.querySelectorAll('.bld-tab').forEach(function(b) { b.classList.remove('active'); });
        btn.classList.add('active');
        currentBld = btn.dataset.bld;
        applyFilter();
      });
    });

    // init
    applyFilter();
  })();
  </script>

</body>
</html>
"""


def clean_old_reports(output_dir: Path) -> None:
    """Delete all previously generated report_*.html files in output_dir."""
    if output_dir.exists():
        for old in output_dir.glob("report_*.html"):
            old.unlink()


def render_report(
    entries: list[DiffEntry],
    output_dir: str | Path = ".",
    config: dict | None = None,
) -> Path:
    """Render a standalone HTML report for all entries.

    Sections: New → Price Drop → Active (unchanged) → Delisted.
    Deletes any previous report_*.html in output_dir before writing.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    clean_old_reports(out_dir)

    new_entries      = [e for e in entries if e.status == "new"]
    drop_entries     = [e for e in entries if e.status == "price_drop"]
    active_entries   = [e for e in entries if e.status == "unchanged"]
    delisted_entries = [e for e in entries if e.status == "delisted"]

    # collect unique regions from all non-delisted entries, preserve insertion order
    seen_regions: dict[str, None] = {}
    for e in new_entries + drop_entries + active_entries:
        addr = e.property.address or ""
        region = addr.split("-")[0].strip() if "-" in addr else addr.strip()
        if region:
            seen_regions[region] = None
    regions = list(seen_regions.keys())

    env      = Environment(loader=BaseLoader())
    template = env.from_string(_TEMPLATE)
    html     = template.render(
        report_date=date.today().strftime("%Y-%m-%d"),
        new_entries=new_entries,
        drop_entries=drop_entries,
        active_entries=active_entries,
        delisted_entries=delisted_entries,
        new_count=len(new_entries),
        drop_count=len(drop_entries),
        active_count=len(active_entries),
        delisted_count=len(delisted_entries),
        config=config,
        regions=regions,
    )

    filename = out_dir / f"report_{date.today().strftime('%Y%m%d')}.html"
    filename.write_text(html, encoding="utf-8")
    return filename
