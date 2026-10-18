"""Agent: Codex-faisal/T2. Content-only contract validation."""
import json
import re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def validate(data):
    assert data['schema_version'] == 1 and data['status'] == 'PROPOSED'
    source = (ROOT / 'scripts/game_state.gd').read_text()
    buyers = data['buyers']
    assert len(buyers) == len({b['id'] for b in buyers}) == 10
    assert {b['id'] for b in buyers} == {'bargain','local','first','nerd','parent','influencer','lowballer','whale','commuter','contractor'}
    baseline = source.split('const BUYER_TYPES := {')[1].split('const REVIEW_NAMES')[0]
    originals = re.findall(r'"(\w+)": \{"title": "([^"]+)", "budget": ([\d.]+), "likes": \[(.*?)\], "tolerance": ([\d.]+)', baseline)
    assert len(originals) == 8
    for b in buyers:
        assert .5 <= b['budget'] <= 1.5 and .5 <= b['tolerance'] <= 1.5
        assert b['likes'] and set(b['likes']) <= {'discount','features','history','extras','test_drive'}
        assert set(b['dialogue']) == {'arrival','concern','accept','walk'}
        assert all(line.strip() for line in b['dialogue'].values())
    by_id = {b['id']: b for b in buyers}
    for key,title,budget,likes,tolerance in originals:
        b = by_id[key]
        assert (b['title'], b['budget'], b['tolerance'], b['likes']) == (title,float(budget),float(tolerance),re.findall(r'"(.*?)"',likes))
    assert len(data['marco']) == len({m['id'] for m in data['marco']}) == 24
    for m in data['marco']:
        assert m['trigger'].strip() and m['line'].strip()
        assert m['cooldown'] in {'once_per_day','once_per_save'}
    rivals = data['rivals']
    assert len(rivals) == len({r['id'] for r in rivals}) == 6
    original_names = re.findall(r'"(.*?)"', source.split('const RIVALS := [')[1].split(']')[0])
    assert [r['name'] for r in rivals if r['existing']] == original_names
    for r in rivals:
        assert r['preferred_classes'] and set(r['preferred_classes']) <= {'economy','sport','suv','truck','exotic'}
        assert set(r['dialogue']) == {'opening','outbid','stop'}
        assert all(line.strip() for line in r['dialogue'].values())

if __name__ == '__main__':
    validate(json.loads((ROOT / 'content/t2/people.json').read_text()))
    print('PASS: 10 buyers / 40 lines; 24 Marco triggers; 6 rivals / 18 lines; source canon and dialogue coverage')
