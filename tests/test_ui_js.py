"""Behavior tests for the dashboard/admin UI JavaScript (review #12).

The sortable ranking table (v1.0.34) and the mobile DataTables toolbar
(v1.0.37) previously had only HTML-string smoke tests in test_templates.py.
These tests render the real Jinja templates, extract the shipped functions
(``setupMobileTableSearch``, ``refreshDataTable`` from app/templates/base.html)
and execute them in Node against a minimal DOM/DataTables harness, asserting
actual behavior: toolbar restructure, magnifier toggle, pre-filled search
auto-open, idempotency, and refresh state capture/restore.

The suite is skipped when a ``node`` binary is absent (minimal runners).
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import pytest
from jinja2 import Environment, FileSystemLoader

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node binary not available")

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "app" / "templates"

# ---------------------------------------------------------------------------
# JS harness: minimal DOM + jQuery/DataTables stubs sufficient for the two
# extracted functions. Plain JavaScript so any modern node can run it.
# ---------------------------------------------------------------------------
HARNESS = r"""
'use strict';
let docRegistry, document, doc, dts, dtInits, $;
let docCreateCount = 0;

function makeEl() {
  const e = {
    kind: 'el', className: '', dataset: {}, attrs: {}, children: [], parentElement: null,
    innerHTML: '', type: '', title: '', value: '', disabled: false,
    classSet: new Set(), handlers: [], focused: false, _inputChild: null,
  };
  e.classList = {
    add(c) { e.classSet.add(c); e.className = Array.from(e.classSet).join(' '); },
    remove(c) { e.classSet.delete(c); e.className = Array.from(e.classSet).join(' '); },
    toggle(c) {
      if (e.classSet.has(c)) { e.classSet.delete(c); } else { e.classSet.add(c); }
      e.className = Array.from(e.classSet).join(' ');
      return e.classSet.has(c);
    },
    contains(c) { e.classSet.has(c); },
  };
  e.setAttribute = (n, v) => { e.attrs[n] = String(v); };
  e.addEventListener = (ev, fn) => { e.handlers.push({ ev, fn }); };
  e.click = () => { e.handlers.filter(h => h.ev === 'click').forEach(h => h.fn()); };
  e.focus = () => { e.focused = true; };
  e.appendChild = (child) => { child.parentElement = e; e.children.push(child); };
  e.replaceWith = (node) => {
    const p = e.parentElement;
    if (p) { const i = p.children.indexOf(e); if (i >= 0) p.children[i] = node; }
    node.parentElement = p;
    e.parentElement = null;
  };
  e.closest = (sel) => {
    let cur = e;
    while (cur) {
      const cls = (cur.className || '').split(/\s+/);
      if (sel.startsWith('.') && cls.includes(sel.slice(1))) return cur;
      cur = cur.parentElement;
    }
    return null;
  };
  e.querySelector = (sel) => (sel === 'input') ? e._inputChild : null;
  return e;
}

function reset() {
  docRegistry = new Map();
  docCreateCount = 0;
  doc = {
    querySelector: (sel) => docRegistry.get(sel) || null,
    createElement: () => { docCreateCount++; return makeEl(); },
    body: makeEl(),
  };
  document = doc;   // the template code uses the global `document` symbol
  dts = new Map();   // selector -> DataTable handle (or absent)
  dtInits = [];      // [{ sel, opts }] every (re)initialisation
  const mkDt = () => {
    const dt = {
      initOpts: null, initCalls: 0, destroyed: false,
      _search: '', _page: 0, _length: 10, _order: [], _draw: false,
    };
    dt.search = (v) => { if (v !== undefined) dt._search = String(v); return dt._search; };
    dt.page = (v) => { if (v !== undefined) { dt._page = v; return dt; } return dt._page; };
    dt.page.len = (v) => { if (v !== undefined) { dt._length = v; return dt; } return dt._length; };
    dt.order = (v) => { if (v !== undefined) { dt._order = v; return dt; } return dt._order; };
    dt.draw = (v) => { dt._draw = v; return dt; };
    dt.destroy = () => { dt.destroyed = true; };
    return dt;
  };
  $ = (sel) => ({
    DataTable(opts) {
      if (opts !== undefined) {
        const dt = mkDt(); dt.initOpts = opts; dt.initCalls = 1;
        dts.set(sel, dt); dtInits.push({ sel, opts });
        return dt;
      }
      return dts.get(sel) || null;
    },
  });
  $.fn = { DataTable: { isDataTable: (sel) => !!dts.get(sel) } };
}

function buildTableTable() {
  const row = makeEl();       row.className = 'row';
  const lengthCol = makeEl(); const filterCol = makeEl();
  const filterEl = makeEl();  filterEl._inputChild = makeEl();
  const lengthEl = makeEl();
  docRegistry.set('#t_filter', filterEl);
  docRegistry.set('#t_length', lengthEl);
  filterCol.appendChild(filterEl);
  lengthCol.appendChild(lengthEl);
  row.appendChild(lengthCol);
  row.appendChild(filterCol);
  doc.body.appendChild(row);
  return { row, lengthCol, filterCol, filterEl, lengthEl };
}

function assertTrue(cond, msg) { if (!cond) throw new Error('assert: ' + (msg || 'expected truthy')); }
function assertEq(actual, expected, msg) {
  const a = JSON.stringify(actual), b = JSON.stringify(expected);
  if (a !== b) throw new Error('assert: ' + (msg || '') + ' expected ' + b + ' got ' + a);
}
"""
# ---------------------------------------------------------------------------
# JS scenarios. Every scenario calls reset() first and ends with a PASS log.
# ---------------------------------------------------------------------------
SCENARIOS = {
    "no_filter_is_noop": r"""
(function no_filter_is_noop() {
  reset();
  // No '#t_filter' element: the helper must bail out without crashing.
  setupMobileTableSearch('#t');
  console.log('PASS no_filter_is_noop');
})();
""",
    "toolbar_rebuild_order": r"""
(function toolbar_rebuild_order() {
  reset();
  const t = buildTableTable();
  setupMobileTableSearch('#t');
  const toolbar = doc.body.children[0];
  assertEq(doc.body.children.length, 1, 'row replaced by exactly one toolbar');
  assertTrue(toolbar.className.includes('dt-toolbar'), 'toolbar class set');
  const kinds = toolbar.children.map(c => c === t.lengthCol ? 'length'
    : c.className.includes('dt-search-toggle') ? 'btn' : 'filter');
  assertEq(kinds, ['length', 'btn', 'filter'], 'order: length, btn, filter');
  assertTrue(t.lengthCol.className.includes('dt-length-col'), 'length column tagged');
  assertTrue(t.filterCol.className.includes('dt-filter-col'), 'filter column tagged');
  const btn = toolbar.children[1];
  assertEq(btn.attrs['aria-label'], 'Search', 'magnifier aria-label');
  assertEq(btn.attrs['aria-expanded'], 'false', 'collapsed initially');
  console.log('PASS toolbar_rebuild_order');
})();
""",
    "magnifier_toggles_search": r"""
(function magnifier_toggles_search() {
  reset();
  const t = buildTableTable();
  setupMobileTableSearch('#t');
  const btn = doc.body.children[0].children[1];
  btn.click();
  assertTrue(t.filterCol.classSet.has('dt-filter-open'), 'opens on first tap');
  assertEq(btn.attrs['aria-expanded'], 'true', 'aria expanded true');
  assertTrue(t.filterEl._inputChild.focused, 'focuses the search input');
  btn.click();
  assertTrue(!t.filterCol.classSet.has('dt-filter-open'), 'closes on second tap');
  assertEq(btn.attrs['aria-expanded'], 'false', 'aria collapsed again');
  console.log('PASS magnifier_toggles_search');
})();
""",
    "prefilled_search_auto_opens": r"""
(function prefilled_search_auto_opens() {
  reset();
  const t = buildTableTable();
  t.filterEl._inputChild.value = 'alice';
  setupMobileTableSearch('#t');
  assertTrue(t.filterCol.classSet.has('dt-filter-open'), 'stays open for active search');
  const btn = doc.body.children[0].children[1];
  assertEq(btn.attrs['aria-expanded'], 'true', 'aria reflects open state');
  console.log('PASS prefilled_search_auto_opens');
})();
""",
    "rebuild_is_idempotent": r"""
(function rebuild_is_idempotent() {
  reset();
  const t = buildTableTable();
  setupMobileTableSearch('#t');
  const createAfterFirst = docCreateCount;
  setupMobileTableSearch('#t');
  assertEq(docCreateCount, createAfterFirst, 'second call creates no new nodes');
  assertEq(doc.body.children[0].children.length, 3, 'toolbar untouched by second call');
  console.log('PASS rebuild_is_idempotent');
})();
""",
    "refresh_fresh_init": r"""
(function refresh_fresh_init() {
  reset();
  buildTableTable();
  const tbody = makeEl();
  docRegistry.set('#t tbody', tbody);
  const opts = { paging: true, pageLength: 25, order: [[2, 'desc'], [0, 'asc']], searching: true, lengthChange: true };
  const fills = [];
  refreshDataTable('#t', opts, (tb) => { fills.push('filled'); tb.innerText = 'X'; });
  assertEq(dtInits.length, 1, 'exactly one (re)initialisation');
  assertEq(dtInits[0].sel, '#t', 'initialised the right selector');
  assertEq(dtInits[0].opts, opts, 'init options forwarded verbatim');
  assertEq(fills, ['filled'], 'fillTbody called with the tbody');
  assertTrue(doc.body.children[0].className.includes('dt-toolbar'), 'mobile toolbar set up after init');
  console.log('PASS refresh_fresh_init');
})();
""",
    "refresh_restores_state": r"""
(function refresh_restores_state() {
  reset();
  buildTableTable();
  const tbody = makeEl();
  docRegistry.set('#t tbody', tbody);
  const optsIn = { paging: true, lengthChange: true, order: [[1, 'asc']] };
  const seeded = $( '#t' ).DataTable(optsIn);   // pre-existing DataTable
  seeded._search = 'alice'; seeded._page = 3; seeded._length = 50; seeded._order = [[1, 'asc']];
  const fills = [];
  refreshDataTable('#t', optsIn, (tb) => { fills.push('filled'); });
  assertTrue(seeded.destroyed, 'old table destroyed');
  const dt = dts.get('#t');
  assertTrue(dt !== seeded, 'a new handle was created');
  assertEq(dt._page, 3, 'page restored');
  assertEq(dt._length, 50, 'page length restored');
  assertEq(dt._order, [[1, 'asc']], 'sort order restored');
  assertEq(dt._search, 'alice', 'search term restored');
  assertEq(dt._draw, false, 'standing redraw used');
  assertEq(fills.length, 1, 'fresh fill happened');
  console.log('PASS refresh_restores_state');
})();
""",
    "refresh_length_change_false": r"""
(function refresh_length_change_false() {
  reset();
  buildTableTable();
  const tbody = makeEl();
  docRegistry.set('#t tbody', tbody);
  const optsIn = { paging: true, lengthChange: false };
  const seeded = $( '#t' ).DataTable(optsIn);
  seeded._search = ''; seeded._page = 0; seeded._length = 50; seeded._order = [];
  refreshDataTable('#t', optsIn, () => {});
  const dt = dts.get('#t');
  assertEq(dt._length, 10, 'length untouched when lengthChange is false');
  console.log('PASS refresh_length_change_false');
})();
""",
}


def _run_js(scenario_names: list[str]) -> str:
    """Run the extracted functions + harness + scenarios in node; return stdout."""
    script = (
        HARNESS
        + "\n"
        + _extracted_functions()
        + "\n"
        + "\n".join(SCENARIOS[n] for n in scenario_names)
    )
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(script)
        path = f.name
    try:
        proc = subprocess.run(["node", path], capture_output=True, text=True, timeout=120)
    finally:
        Path(path).unlink(missing_ok=True)
    assert proc.returncode == 0, f"node failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    return proc.stdout


@lru_cache(maxsize=1)
def _extracted_functions() -> str:
    """Extract the shipped functions from the RENDERED base.html template."""
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    context = {
        "app_name": "Test",
        "club_name": "Club",
        "api_docs_enabled": True,
        "date_format": "dd/MM/yyyy",
        "timezone": "UTC",
        "version_info": {
            "version": "1.0.0",
            "git_commit": "dev",
            "build_date": "development",
            "github_url": "https://github.com/reserve85/EloRankingSystem",
            "release_url": "https://github.com/reserve85/EloRankingSystem/releases/tag/v1.0.0",
        },
        "user": SimpleNamespace(username="tester", role=SimpleNamespace(value="USER"), active=True),
    }
    html = env.get_template("base.html").render(**context)
    return (
        _extract_function(html, "setupMobileTableSearch")
        + "\n"
        + _extract_function(html, "refreshDataTable")
    )


def _extract_function(src: str, name: str) -> str:
    """Extract ``function <name>(...) { ... }`` with balanced-brace scanning."""
    marker = f"function {name}("
    start = src.find(marker)
    assert start != -1, f"function {name} not found in rendered base.html"
    brace = src.find("{", start)
    assert brace != -1, f"no opening brace for {name}"
    depth = 0
    for i in range(brace, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start : i + 1]
    raise AssertionError(f"unbalanced braces in {name}")


class TestMobileTableSearch:
    def test_no_filter_is_noop(self):
        _run_js(["no_filter_is_noop"])

    def test_toolbar_rebuild_order(self):
        _run_js(["toolbar_rebuild_order"])

    def test_magnifier_toggles_search(self):
        _run_js(["magnifier_toggles_search"])

    def test_prefilled_search_auto_opens(self):
        _run_js(["prefilled_search_auto_opens"])

    def test_rebuild_is_idempotent(self):
        _run_js(["rebuild_is_idempotent"])


class TestRefreshDataTable:
    def test_fresh_init_runs_fill_and_toolbar(self):
        _run_js(["refresh_fresh_init"])

    def test_restores_state_after_destroy(self):
        _run_js(["refresh_restores_state"])

    def test_length_change_false_keeps_default_length(self):
        _run_js(["refresh_length_change_false"])
