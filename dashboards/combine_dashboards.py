#!/usr/bin/env python3
import json
import copy
from pathlib import Path
import urllib.request

# Paths
ROOT = Path('/home/michey/llmd_aug2025/vllmbench/dashboards')
INFER_PATH = ROOT / 'inference-gateway-dashboard.json'
VLLM_PATH = ROOT / 'vllm-dashboard.json'
DCGM_PATH = ROOT / 'vllm-dcgm-sm-dashboard.json'
OUT_PATH = ROOT / 'kubecon-dashboard.json'

# Optional extra dashboards from llm-d repository (downloaded if missing)
# Source: https://github.com/llm-d/llm-d/tree/main/docs/monitoring/grafana/dashboards
EXTRA_CANDIDATES = [
  (
    'llm-d-diagnostic-drilldown-dashboard.json',
    'llm-d Diagnostic Drill-Down',
    'https://raw.githubusercontent.com/llm-d/llm-d/main/docs/monitoring/grafana/dashboards/llm-d-diagnostic-drilldown-dashboard.json',
  ),
  (
    'llm-d-failure-saturation-dashboard.json',
    'llm-d Failure Saturation',
    'https://raw.githubusercontent.com/llm-d/llm-d/main/docs/monitoring/grafana/dashboards/llm-d-failure-saturation-dashboard.json',
  ),
]


def load_json(path: Path):
  with path.open('r', encoding='utf-8') as f:
    return json.load(f)


def ensure_panels(obj):
  # Some exports may wrap dashboard under 'dashboard'
  if 'panels' in obj and isinstance(obj['panels'], list):
    return obj
  if 'dashboard' in obj and isinstance(obj['dashboard'], dict):
    return obj['dashboard']
  return obj


def collect_panels_with_offset(src_panels, section_title, y_offset, next_panel_id):
  """
  - Insert a row panel as section header at y_offset.
  - Rebase subsequent panels by subtracting min_y and adding y_offset+1.
  - Return new panels, updated y_offset (to stack next section), and next_panel_id.
  """
  new_panels = []

  # Section header row
  row_panel = {
    'type': 'row',
    'title': section_title,
    'gridPos': {'h': 1, 'w': 24, 'x': 0, 'y': y_offset},
    'id': next_panel_id,
  }
  next_panel_id += 1
  new_panels.append(row_panel)

  # Determine baseline y of source panels
  positioned = [p for p in src_panels if isinstance(p, dict) and 'gridPos' in p and isinstance(p['gridPos'], dict)]
  min_y = min((p['gridPos'].get('y', 0) for p in positioned), default=0)

  # Sort by y then x to preserve order visually
  positioned.sort(key=lambda p: (p['gridPos'].get('y', 0), p['gridPos'].get('x', 0)))

  max_y_plus_h = y_offset + 1

  for p in positioned:
    p2 = copy.deepcopy(p)
    # Renumber id
    p2['id'] = next_panel_id
    next_panel_id += 1

    # Rebase y
    g = p2.get('gridPos', {})
    g = {'h': g.get('h', 1), 'w': g.get('w', 24), 'x': g.get('x', 0), 'y': g.get('y', 0)}
    g['y'] = (g.get('y', 0) - min_y) + (y_offset + 1)
    p2['gridPos'] = g

    new_panels.append(p2)
    max_y_plus_h = max(max_y_plus_h, g['y'] + g.get('h', 1))

  # Next section starts after the last panel's bottom
  new_y_offset = max_y_plus_h + 1
  return new_panels, new_y_offset, next_panel_id


def merge_templating_lists(*lists):
  by_name = {}
  for lst in lists:
    if not isinstance(lst, list):
      continue
    for v in lst:
      if not isinstance(v, dict):
        continue
      name = v.get('name')
      if not name:
        continue
      # First definition wins; skip duplicates to avoid conflicts
      if name not in by_name:
        by_name[name] = v
  return list(by_name.values())


def fetch_if_missing(target_path: Path, url: str):
  if target_path.exists():
    return True
  try:
    print(f'Downloading {url} -> {target_path}')
    with urllib.request.urlopen(url) as resp:
      data = resp.read()
    target_path.write_bytes(data)
    return True
  except Exception as e:
    print(f'Warning: failed to download {url}: {e}')
    return False


def normalize_datasource_uids(dashboard_obj):
  """Replace any Prometheus datasource uid with ${DS_PROMETHEUS} across panels, targets, and templating."""
  def fix_ds(ds):
    if isinstance(ds, dict) and ds.get('type') == 'prometheus':
      ds['uid'] = '${DS_PROMETHEUS}'

  # Fix panel-level and target-level datasources
  for p in dashboard_obj.get('panels', []) or []:
    if isinstance(p, dict):
      fix_ds(p.get('datasource'))
      # Some row panels have nested 'panels' (collapsed); also handle recursively if present
      for tp in p.get('panels', []) or []:
        fix_ds(tp.get('datasource'))
        for t in tp.get('targets', []) or []:
          fix_ds(t.get('datasource'))
      for t in p.get('targets', []) or []:
        fix_ds(t.get('datasource'))

  # Fix templating variable datasources
  templ = dashboard_obj.get('templating', {})
  for v in templ.get('list', []) or []:
    ds = v.get('datasource')
    fix_ds(ds)

  return dashboard_obj


def main():
  infer = ensure_panels(load_json(INFER_PATH))
  vllm = ensure_panels(load_json(VLLM_PATH))
  dcgm = ensure_panels(load_json(DCGM_PATH))

  # Load optional extras; fetch from GitHub raw if missing
  extras = []
  for filename, fallback_title, raw_url in EXTRA_CANDIDATES:
    p = ROOT / filename
    if not p.exists():
      fetch_if_missing(p, raw_url)
    if p.exists():
      try:
        dj = ensure_panels(load_json(p))
        extras.append((dj, fallback_title))
      except Exception as e:
        print(f'Warning: failed to load {p}: {e}')
    else:
      print(f'Skip: optional extra dashboard not available: {p}')

  # Start assembling new dashboard
  out = {
    'annotations': infer.get('annotations', {'list': []}),
    'editable': True,
    'fiscalYearStartMonth': infer.get('fiscalYearStartMonth', 0),
    'graphTooltip': infer.get('graphTooltip', 0),
    'id': None,
    'links': [],
    'panels': [],
    'preload': False,
    'refresh': infer.get('refresh', ''),
    'schemaVersion': max(infer.get('schemaVersion', 1), vllm.get('schemaVersion', 1), dcgm.get('schemaVersion', 1), *[ex[0].get('schemaVersion', 1) for ex in extras] or [1]),
    'tags': list({*infer.get('tags', []), *vllm.get('tags', []), *dcgm.get('tags', []), *sum((ex[0].get('tags', []) for ex in extras), [])}),
    'templating': {'list': []},
    'time': infer.get('time', {'from': 'now-2d', 'to': 'now'}),
    'timepicker': infer.get('timepicker', {}),
    'timezone': infer.get('timezone', ''),
    'title': 'KubeCon Dashboard',
    'uid': None,
    'version': 1,
  }

  # Merge variables
  out['templating']['list'] = merge_templating_lists(
    infer.get('templating', {}).get('list', []),
    vllm.get('templating', {}).get('list', []),
    dcgm.get('templating', {}).get('list', []),
    *[ex[0].get('templating', {}).get('list', []) for ex in extras],
  )

  # Append sections
  y_offset = 0
  next_panel_id = 1

  # 1) Inference Gateway section
  infer_title = infer.get('title', 'Inference Gateway')
  section_panels, y_offset, next_panel_id = collect_panels_with_offset(
    infer.get('panels', []), f'Inference Gateway: {infer_title}', y_offset, next_panel_id
  )
  out['panels'].extend(section_panels)

  # 2) vLLM section
  vllm_title = vllm.get('title', 'vLLM Overview')
  section_panels, y_offset, next_panel_id = collect_panels_with_offset(
    vllm.get('panels', []), f'vLLM: {vllm_title}', y_offset, next_panel_id
  )
  out['panels'].extend(section_panels)

  # 3) DCGM section
  dcgm_title = dcgm.get('title', 'DCGM - SM Util & Occupancy')
  section_panels, y_offset, next_panel_id = collect_panels_with_offset(
    dcgm.get('panels', []), f'DCGM: {dcgm_title}', y_offset, next_panel_id
  )
  out['panels'].extend(section_panels)

  # 4) Optional extra sections
  for ex_obj, fallback_title in extras:
    ex_title = ex_obj.get('title') or fallback_title
    section_panels, y_offset, next_panel_id = collect_panels_with_offset(
      ex_obj.get('panels', []), ex_title, y_offset, next_panel_id
    )
    out['panels'].extend(section_panels)

  # Normalize datasource UIDs across the combined dashboard
  out = normalize_datasource_uids(out)

  # Write output
  with OUT_PATH.open('w', encoding='utf-8') as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
    f.write('\n')

  print(f'Wrote combined dashboard to {OUT_PATH}')


if __name__ == '__main__':
  main()
