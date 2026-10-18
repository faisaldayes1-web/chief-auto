"""Agent: Codex-faisal/T2. Validate proposed data; does not load game saves."""
import json
import re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def validate(data):
    cars = data['cars']
    assert data['schema_version'] == 1 and data['status'] == 'PROPOSED'
    assert len(cars) == 40
    assert [c['id'] for c in cars] == [f'CA{i:02}' for i in range(1, 41)]
    assert len({c['model'] for c in cars}) == 40
    source = (ROOT / 'scripts/game_state.gd').read_text()
    block = source.split('const MODELS := [')[1].split('\n]')[0]
    baseline = re.findall(r'\["([^"]+)", "([^"]+)", (\d+), ([\d.]+)\]', block)
    assert len(baseline) == 17, 'Review changed source catalogue before updating contract'
    for i, c in enumerate(cars):
        assert c['cls'] in {'economy', 'sport', 'suv', 'truck', 'exotic'}
        assert type(c['base']) is int and 10000 <= c['base'] <= 500000
        assert .5 <= c['resale'] <= 1.5
        assert c['fault_profile'] in data['fault_profiles']
        assert c['existing'] == c['art_ready'] == (i < 17)
        if i < 17:
            n, cls, base, resale = baseline[i]
            assert (c['model'], c['cls'], c['base'], c['resale']) == (n, cls, int(base), float(resale))
    assert set(data['fault_profiles']) == set('ESUTVX')
    for p in data['fault_profiles'].values():
        assert set(p['weights']) == {'engine','transmission','body','interior','tires'}
        assert all(type(w) is int and 0 <= w <= 100 for w in p['weights'].values())
        assert sum(p['weights'].values()) == 100 and p['clue'].strip()
    assert data['fault_rules'] == {'draws': {'autobidz':[0,2], 'salvage':[1,3], 'dealer':[0,1], 'exotic':[0,1]}, 'flood_extra_draws':1, 'damage_per_draw':[15,35], 'day_one_draws':0, 'repeat_draws':'accumulate', 'true_condition_floor':0}

if __name__ == '__main__':
    validate(json.loads((ROOT / 'content/t2/cars.json').read_text()))
    print('PASS: 40 unique cars; 17 source tuples preserved; 6 normalized fault profiles; ranges and references')
