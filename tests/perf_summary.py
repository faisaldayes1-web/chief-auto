import json,glob,statistics as st,sys
def load(w): return [json.load(open(f)) for f in sorted(glob.glob(sys.argv[1]+f'/{w}-[0-9].json'))]
B,P=load('base'),load('perf')
print('runs',len(B),len(P))
def med(runs,i,k): return st.median(r['screens'][i][k] for r in runs)
names=[s['screen'] for s in B[0]['screens']]
print('| # | screen | switch call ms (base -> new) | worst frame after switch ms | avg frame ms | draw calls | texture MB |')
print('|---|---|---|---|---|---|---|')
for i,n in enumerate(names):
    vis='1st' if i<7 else '2nd'
    print(f"| {vis} | {n} | {med(B,i,'switch_call_ms'):.0f} -> {med(P,i,'switch_call_ms'):.0f} | {med(B,i,'settle_worst_ms'):.0f} -> {med(P,i,'settle_worst_ms'):.0f} | {med(B,i,'avg_ms'):.2f} -> {med(P,i,'avg_ms'):.2f} | {med(B,i,'draw_calls'):.0f} -> {med(P,i,'draw_calls'):.0f} | {med(B,i,'texture_mem_mb'):.0f} -> {med(P,i,'texture_mem_mb'):.0f} |")
for k in ['main_instantiate_ms','first_120_frames_worst_ms']:
    print(k, st.median(r[k] for r in B), '->', st.median(r[k] for r in P))
for k in ['vram_mb','static_mem_mb','orphans']:
    print(k,'peak', st.median(max(s[k] for s in r['screens']) for r in B),'->',st.median(max(s[k] for s in r['screens']) for r in P))
sw=lambda R:st.median(sum(s['switch_call_ms']+s['settle_worst_ms'] for s in r['screens']) for r in R)
print('sum of switch stalls (call + worst frame) over 14 switches', sw(B),'->',sw(P))
