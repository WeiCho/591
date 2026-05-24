"""HTML report generator.

Renders a standalone, self-contained HTML file using Jinja2 + Tailwind CSS
(loaded from CDN).  Sections: New → Price Drop → Active.
Delisted listings are excluded from the report entirely.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path

from jinja2 import Environment, BaseLoader

from .diff_engine import DiffEntry

_TEMPLATE = """\
{# ── Card macro ─────────────────────────────────────────────── #}
{% macro card(entry, kind, r2c) %}
{% set prop = entry.property %}
{% set old_price = entry.old_price %}
{% set region = prop.address.split('-')[0] if prop.address and '-' in prop.address else (prop.address or '') %}
{% set city = r2c.get(region, '') if r2c else '' %}
<a href="{{ prop.link }}" target="_blank" rel="noopener"
   class="card-item bg-white rounded-2xl shadow-sm hover:shadow-md transition-all duration-200 overflow-hidden flex flex-col{% if kind == 'delisted' %} opacity-50 grayscale{% endif %}"
   data-region="{{ region }}"
   data-city="{{ city }}"
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
      <span class="text-2xl font-bold tracking-tight text-slate-900">
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
      {% if prop.listed_date %}<span>📅 上架 {{ prop.listed_date }}</span>{% endif %}
    </div>
  </div>
</a>
{% endmacro %}

<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>我與寶的租房趣 {{ report_date }}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    .card-img { object-fit: cover; height: 192px; width: 100%; }

    /* city tabs */
    .city-tab {
      cursor: pointer; transition: all .18s;
      border-bottom: 2px solid transparent;
      padding: 0.5rem 1.25rem;
      font-size: .875rem; font-weight: 600;
      color: #94a3b8;
      white-space: nowrap;
    }
    .city-tab:hover { color: #4f46e5; }
    .city-tab.active {
      color: #4f46e5;
      border-bottom-color: #4f46e5;
    }

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

    .card-item.hidden-by-filter { display: none !important; }
    .status-section.empty-section { display: none; }
    .filter-empty { display: none; }
    .filter-empty.visible { display: flex; }

    /* region row hidden when city not selected */
    .city-regions { display: none; }
    .city-regions.active { display: flex; }
  </style>
</head>
<body class="bg-slate-50 min-h-screen">

  <!-- ══ HEADER ══════════════════════════════════════════════════ -->
  <div class="bg-white border-b border-slate-200 sticky top-0 z-20 shadow-sm">
    <div class="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between gap-4 flex-wrap">
      <div>
        <h1 class="text-xl font-bold text-slate-900 leading-none">我與寶的租房趣</h1>
        <p class="text-xs text-slate-400 mt-0.5">{{ report_date }}</p>
      </div>
      <!-- stat pills -->
      <div class="flex items-center gap-2 flex-wrap">
        <span class="inline-flex items-center gap-1.5 bg-emerald-50 text-emerald-700 text-sm font-semibold px-3 py-1.5 rounded-full ring-1 ring-emerald-200">
          <span class="w-2 h-2 rounded-full bg-emerald-500"></span>
          新上架 <span id="pill-new">{{ new_count }}</span>
        </span>
        <span class="inline-flex items-center gap-1.5 bg-amber-50 text-amber-700 text-sm font-semibold px-3 py-1.5 rounded-full ring-1 ring-amber-200">
          ↓ 降價 <span id="pill-drop">{{ drop_count }}</span>
        </span>
        <span class="inline-flex items-center gap-1.5 bg-blue-50 text-blue-700 text-sm font-semibold px-3 py-1.5 rounded-full ring-1 ring-blue-200">
          在架中 <span id="pill-active">{{ active_count }}</span>
        </span>
        {% if delisted_count %}
        <span class="inline-flex items-center gap-1.5 bg-slate-100 text-slate-500 text-sm font-semibold px-3 py-1.5 rounded-full ring-1 ring-slate-200">
          下架 <span id="pill-delisted">{{ delisted_count }}</span>
        </span>
        {% endif %}
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
    <div class="py-5 space-y-3">

      {% if multi_city %}
      <!-- Layer 0: City tabs (only shown when >1 city) -->
      <div class="flex items-center gap-0 border-b border-slate-200 overflow-x-auto">
        {% for city_name in city_names %}
        <button class="city-tab{% if loop.first %} active{% endif %} shrink-0" data-city="{{ city_name }}">{{ city_name }}</button>
        {% endfor %}
      </div>
      {% endif %}

      <!-- Layer 1: Region tags — one row per city -->
      <div class="space-y-2">
        {% for city_name, city_regions in city_region_map.items() %}
        <div class="city-regions" data-city-row="{{ city_name }}"
             style="display:none; flex-wrap:wrap; align-items:center; gap:0.5rem;">
          <span class="text-xs font-semibold text-slate-400 uppercase tracking-wide w-8 shrink-0">區域</span>
          <button class="region-tag active text-xs font-semibold px-3.5 py-1.5 rounded-full bg-slate-100 text-slate-600"
                  data-region="all" data-city-scope="{{ city_name }}">全部</button>
          {% for region in city_regions %}
          <button class="region-tag text-xs font-semibold px-3.5 py-1.5 rounded-full bg-slate-100 text-slate-600"
                  data-region="{{ region }}" data-city-scope="{{ city_name }}">{{ region }}</button>
          {% endfor %}
        </div>
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
          {% for entry in entries %}{{ card(entry, kind, region_to_city) }}{% endfor %}
        </div>
      </section>
      {% endif %}
      {% endmacro %}

      {{ section(new_entries,      "new",      "新上架",  "bg-emerald-50 text-emerald-700") }}
      {{ section(drop_entries,     "drop",     "降價",    "bg-amber-50 text-amber-700") }}
      {{ section(active_entries,   "active",   "在架中",  "bg-blue-50 text-blue-700") }}
      {{ section(delisted_entries, "delisted", "本次下架", "bg-slate-100 text-slate-500") }}

      <!-- empty state -->
      <div class="filter-empty flex-col items-center justify-center py-24 text-slate-300" id="empty-state">
        <div class="text-6xl mb-4">🏙</div>
        <p class="text-lg font-medium">此條件下無物件</p>
      </div>
    </div>

  </div>

  <script>
  (function() {
    var firstCity     = {{ first_city_js }};
    var currentCity   = (document.querySelector('.city-tab.active') || {dataset:{city:firstCity}}).dataset.city;
    var currentRegion = 'all';
    var currentBld    = 'elevator';

    var allCards   = Array.from(document.querySelectorAll('.card-item'));
    var sections   = Array.from(document.querySelectorAll('.status-section'));
    var emptyState = document.getElementById('empty-state');

    function applyFilter() {
      var visible = 0;

      allCards.forEach(function(card) {
        var cityOk   = currentCity === 'all' || card.dataset.city === currentCity;
        var regionOk = currentRegion === 'all' || card.dataset.region === currentRegion;
        var isDelisted = card.dataset.status === 'delisted';
        var elevOk   = isDelisted || (currentBld === 'elevator'
                       ? card.dataset.elevator === 'true'
                       : card.dataset.elevator === 'false');

        if (cityOk && regionOk && elevOk) {
          card.classList.remove('hidden-by-filter');
          visible++;
        } else {
          card.classList.add('hidden-by-filter');
        }
      });

      sections.forEach(function(sec) {
        var showing = sec.querySelectorAll('.card-item:not(.hidden-by-filter)').length;
        var badge   = sec.querySelector('.section-count');
        if (badge) badge.textContent = showing + ' 筆';
        sec.classList.toggle('empty-section', showing === 0);

        // sync header pill
        var kind  = sec.dataset.kind;
        var pillId = {new:'pill-new', drop:'pill-drop', active:'pill-active', delisted:'pill-delisted'}[kind];
        if (pillId) {
          var pill = document.getElementById(pillId);
          if (pill) pill.textContent = showing;
        }
      });

      ['elevator','walkup'].forEach(function(bld) {
        var count = allCards.filter(function(c) {
          var cityOk   = currentCity === 'all' || c.dataset.city === currentCity;
          var regionOk = currentRegion === 'all' || c.dataset.region === currentRegion;
          var elevOk   = bld === 'elevator' ? c.dataset.elevator === 'true' : c.dataset.elevator === 'false';
          return cityOk && regionOk && elevOk;
        }).length;
        var el = document.getElementById('count-' + bld);
        if (el) el.textContent = count + ' 筆';
      });

      emptyState.classList.toggle('visible', visible === 0);
    }

    // ── City tabs ──────────────────────────────────────────────
    document.querySelectorAll('.city-tab').forEach(function(btn) {
      btn.addEventListener('click', function() {
        document.querySelectorAll('.city-tab').forEach(function(b) { b.classList.remove('active'); });
        btn.classList.add('active');
        currentCity   = btn.dataset.city;
        currentRegion = 'all';  // reset region on city switch

        // show correct region row
        document.querySelectorAll('.city-regions').forEach(function(row) {
          var match = row.dataset.cityRow === currentCity;
          row.style.display = match ? 'flex' : 'none';
          // reset active tag in this row
          if (match) {
            row.querySelectorAll('.region-tag').forEach(function(t) { t.classList.remove('active'); });
            var allBtn = row.querySelector('[data-region="all"]');
            if (allBtn) allBtn.classList.add('active');
          }
        });

        applyFilter();
      });
    });

    // ── Region tags ────────────────────────────────────────────
    document.querySelectorAll('.region-tag').forEach(function(btn) {
      btn.addEventListener('click', function() {
        // only deactivate tags in the same city-scope row
        var scope = btn.dataset.cityScope;
        document.querySelectorAll('.region-tag[data-city-scope="' + scope + '"]').forEach(function(b) {
          b.classList.remove('active');
        });
        btn.classList.add('active');
        currentRegion = btn.dataset.region;
        applyFilter();
      });
    });

    // ── Building tabs ──────────────────────────────────────────
    document.querySelectorAll('.bld-tab').forEach(function(btn) {
      btn.addEventListener('click', function() {
        document.querySelectorAll('.bld-tab').forEach(function(b) { b.classList.remove('active'); });
        btn.classList.add('active');
        currentBld = btn.dataset.bld;
        applyFilter();
      });
    });

    // ── Init ───────────────────────────────────────────────────
    document.querySelectorAll('.city-regions').forEach(function(row) {
      row.style.display = row.dataset.cityRow === currentCity ? 'flex' : 'none';
    });

    applyFilter();
  })();
  </script>

</body>
</html>
"""


def clean_old_reports(output_dir: Path) -> None:
    if output_dir.exists():
        for old in output_dir.glob("report_*.html"):
            old.unlink()


def render_report(
    entries: list[DiffEntry],
    output_dir: str | Path = ".",
    config: dict | None = None,
) -> Path:
    """Render a standalone HTML report. Delisted entries are excluded."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    clean_old_reports(out_dir)

    def _sort_key(e: DiffEntry) -> str:
        return e.property.listed_date or ""

    new_entries      = sorted([e for e in entries if e.status == "new"],       key=_sort_key, reverse=True)
    drop_entries     = sorted([e for e in entries if e.status == "price_drop"], key=_sort_key, reverse=True)
    active_entries   = sorted([e for e in entries if e.status == "unchanged"],  key=_sort_key, reverse=True)
    delisted_entries = [e for e in entries if e.status == "delisted"]  # first-time delisted only

    # build city → [region] map from config
    cities_cfg: list[dict] = (config or {}).get("cities", [])
    city_region_map: dict[str, list[str]] = {
        c["name"]: c["regions"] for c in cities_cfg if c.get("regions")
    }
    city_names = list(city_region_map.keys())
    multi_city = len(city_names) > 1

    # build region → city reverse map for card data-city attribute
    region_to_city: dict[str, str] = {}
    for city_name, regions in city_region_map.items():
        for r in regions:
            region_to_city[r] = city_name

    # collect unique regions from active entries (address format: "板橋區-路名")
    seen_regions: dict[str, None] = {}
    for e in new_entries + drop_entries + active_entries:
        addr   = e.property.address or ""
        region = addr.split("-")[0].strip() if "-" in addr else addr.strip()
        if region:
            seen_regions[region] = None
    all_regions_list = list(seen_regions.keys())

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
        # city / region data for UI
        multi_city=multi_city,
        city_names=city_names,
        city_region_map=city_region_map,
        all_regions_list=all_regions_list,
        region_to_city=region_to_city,
        first_city_js=f'"{city_names[0]}"' if city_names else '"all"',
    )

    filename = out_dir / f"report_{date.today().strftime('%Y%m%d')}.html"
    filename.write_text(html, encoding="utf-8")
    return filename
