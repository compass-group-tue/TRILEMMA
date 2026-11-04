"""Motivated-reasoning examples for the landing page (mr7 judge, gpt-6.1-sol, 3 replicates, main 5.e.x).
Writes site/data/mr.js: window.TRILEMMA_MR = [...]. One example per seat whose majority verdict is
motivated / motivated_substitute / acknowledged. Run from repo root or experiments/agent5."""
import json, re, collections, pathlib
A = pathlib.Path(__file__).resolve().parent.parent
SITE = A / 'site'
V = json.load(open(A / 'outputs/mr7_a_5e10_all_sol_verdicts.json'))
IDX = json.loads((SITE / 'data/index.js').read_text().split('=', 1)[1].rstrip().rstrip(';'))
MODEL = {m['key']: m['name'] for m in IDX['models']}
REPS = ['', '_r2', '_r3']
norm = lambda s: re.sub(r'\s+', ' ', (s or '').replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')).strip().lower()

def load_run(key):
    s = (SITE / f'data/runs/{key}.js').read_text()
    return json.loads(s[s.index('(') + 1:s.rindex(')')])

out = []
for seatkey, reps in sorted(V.items()):
    model, seed, seat = seatkey.rsplit('_', 2)
    c = collections.Counter(reps.values()); top, n = c.most_common(1)[0]
    if n < 2 or top not in ('motivated', 'motivated_substitute', 'acknowledged'): continue
    run = load_run(f'{model}_{seed}')
    pick = None
    for r, rk in zip(REPS, ['r1', 'r2', 'r3']):
        if reps.get(rk) != top: continue
        x = json.load(open(A / 'runs' / run['dir'] / f'run.mr_a_openrouteropenaigpt61sol{r}.json'))
        for st in x['seats'][seat]['steps']:
            if st.get('verdict') != top: continue
            for o in st['objections']:
                oc = o.get('outcome')
                if oc == 'motivated' and o.get('same_as_contested') == 'no': oc = 'motivated_substitute'
                if oc != top: continue
                pick = (st, o); break
            if pick: break
        if pick: break
    if not pick: print('no pick', seatkey); continue
    st, o = pick
    # locate quotes in the site's run data
    def find_turn(q):
        q = norm(q)[:60]
        for t in run['turns']:
            if t['agent'] == seat and any(q in norm(s.get('reasoning')) for s in t['steps']): return t
        return None
    def find_msg(q, user=None):
        q = norm(q)[:60]
        for m in run['msgs']:
            if (user is None or m['user'] == user) and q in norm(m['text']): return m
        return None
    ot = find_turn(o['objection_quote'])
    src = find_msg(o['source_quote'])
    shipped = find_msg(o['shipped_quote'], seat) if o.get('shipped_quote') else None
    moves, seen = [], set()
    for mv in o.get('moves', []):
        if mv['code'] in ('revise', 'evidence'): continue
        if (mv['code'], mv['quote']) in seen: continue
        seen.add((mv['code'], mv['quote'])); moves.append({'code': mv['code'], 'family': mv['family'], 'q': mv['quote']})
    if len(moves) > 4: moves = moves[:3] + moves[-1:]
    out.append({
        'id': f'{model}_{seed}_{seat}', 'run': f'{model}_{seed}', 'model': model, 'model_name': MODEL.get(model, model), 'seed': seed, 'seat': seat,
        'verdict': top, 'votes': n, 'form': o['form'],
        'contested': o['contested_claim'], 'certified': o.get('certified_claim'),
        'source': {'q': o['source_quote'], 'time': src and src['time'][:5], 'conv': src and src['conv'], 'user': src and src['user']},
        'objection': {'q': o['objection_quote'], 'time': ot and ot['time'][:5], 'turn': ot and ot['i']},
        'moves': moves,
        'stance': {'q': o.get('final_stance_quote'), 'kind': o.get('final_stance')},
        'shipped': {'q': o.get('shipped_quote'), 'text': shipped and shipped['text'], 'time': shipped and shipped['time'][:5], 'conv': shipped and shipped['conv'], 'id': shipped and shipped['id']},
        'why': o.get('why'),
    })
(SITE / 'data/mr.js').write_text('window.TRILEMMA_MR = ' + json.dumps(out, ensure_ascii=False) + ';\n')
print(len(out), collections.Counter(e['verdict'] for e in out))
print('missing objection turn', sum(not e['objection']['turn'] for e in out), 'missing shipped msg', sum(not e['shipped']['id'] for e in out), 'missing src', sum(not e['source']['time'] for e in out))
