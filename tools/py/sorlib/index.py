"""Machine-readable views of a project for editors: `sor markers --json` (see cli.py).

Everything here only reshapes what model.py and markers.py already know: positions of items,
table rows, values and {references} in the spec files, and the code regions that serve them."""
import os

from .model import CODE, REF, VDEF

VERSION = 2  # of this JSON; the editor extension reads it


def region_dict(project, r):
    d = {'file': r.file, 'path': os.path.normpath(os.path.join(project.root, r.file)), 'start': r.start,
         'end': r.end, 'kind': r.kind, 'keys': r.keys, 'ids': r.ids}
    d['targetName'] = project.target_of(r.file)   # the target the file belongs to, or None (`target` below is something else)
    if r.kind == 'anchor':
        d['target'] = r.target   # the `code: path#name` text the region came from
    return d


def _mask(text):
    return CODE.sub(lambda m: ' ' * len(m.group()), text)


def _where(project, part, line, col=0, end=None):
    return {'file': part.rel, 'path': part.path, 'line': line, 'col': col, 'end': end}


def _locate(project, target, value_pos):
    """Where an id (item, row, part, or `item.value`) is defined in the spec files."""
    if target in value_pos:
        return value_pos[target]
    found = project.find(target)
    if found is None and '.' in target:
        base = target.rsplit('.', 1)[0]
        found = project.find(base)
    if found is None:
        return None
    kind, o = found
    if kind == 'part':
        return _where(project, o, 1)
    if kind == 'row':
        item = project.items.get(o.id.rsplit('/', 1)[0])
        for n, t in item.lines:
            if t.strip() == o.text:
                return _where(project, item.part, n)
        return _where(project, item.part, item.lineno)
    return _where(project, o.part, o.lineno)


def full_index(project, scan):
    """Items, rows, values, references and code regions of the whole project."""
    regions = [region_dict(project, r) for r in scan.regions]
    items, value_pos, refs = [], {}, []
    for part in project.parts.values():
        items.append({'id': part.key, 'kind': 'part', 'name': part.title, **_where(project, part, 1),
                      'regions': [i for i, r in enumerate(scan.regions) if part.key in r.keys]})
        for it in part.items.values():
            keys = [it.id]
            for n, text in it.lines:
                masked = _mask(text)
                for m in VDEF.finditer(masked):
                    value_pos[f'{it.id}.{m.group(1)}'] = _where(project, part, n, m.start(), m.end())
                    val = m.group(2)
                    if val.strip().startswith('='):
                        ref = val.strip()[1:].strip()
                        col = max(masked.find(ref, m.start(2)), m.start(2))
                        refs.append((it, n, col, col + len(ref), ref))
                for m in REF.finditer(masked):
                    refs.append((it, n, m.start(1), m.end(1), m.group(1).strip()))
            items.append({'id': it.id, 'kind': it.kind, 'section': it.section, 'name': it.name,
                          **_where(project, part, it.lineno, 0, None),
                          'endLine': it.lines[-1][0] if it.lines else it.lineno,
                          'regions': [i for i, r in enumerate(scan.regions) if it.id in r.keys]})
            for row in it.rows.values():
                line = next((n for n, t in it.lines if t.strip() == row.text), it.lineno)
                items.append({'id': row.id, 'kind': 'row', 'name': row.name,
                              **_where(project, part, line), 'endLine': line,
                              'regions': [i for i, r in enumerate(scan.regions) if row.id in r.keys]})
    out_refs = []
    for it, n, col, end, text in refs:
        hits = project.resolve(it.part.id, text)
        target = hits[0] if len(hits) == 1 else None
        out_refs.append({**_where(project, it.part, n, col, end), 'text': text, 'from': it.id,
                         'target': target, 'to': target and _locate(project, target, value_pos)})
    return {'version': VERSION, 'root': project.root, 'specDir': project.spec_dir, 'regions': regions,
            'items': items, 'refs': out_refs}


def at_line(project, scan, file, line, describe):
    """The regions around file:line and the clauses they serve, with the clause text."""
    out = []
    for r in scan.at(file, line):
        clauses = []
        for k in r.keys:
            clauses.append({'id': k, 'text': describe(project, k), 'where': _locate(project, k, {})})
        out.append({**region_dict(project, r), 'clauses': clauses})
    return {'version': VERSION, 'file': file, 'line': line, 'regions': out}


def for_id(project, scan, key, rows, found):
    return {'version': VERSION, 'id': key, 'exists': found is not None, 'regions': [region_dict(project, r) for r in rows]}
