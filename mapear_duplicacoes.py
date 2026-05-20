import pathlib

root = pathlib.Path('backend')
dups = [('voice','voice_v2'),('memory','memory_v2'),
        ('autonomy','autonomy_v2'),('behavior','behavior_v2')]

print('=== DUPLICAÇÕES ===')
for v1, v2 in dups:
    h1, h2 = (root/v1).exists(), (root/v2).exists()
    status = 'DUP' if h1 and h2 else 'OK'
    print(f'  {status}: {v1}/ {"e " + v2 + "/" if h1 and h2 else ""}')

print('\n=== HTMLs FRONTEND ===')
for h in pathlib.Path('frontend').glob('*.html'):
    print(f'  {h.name}')

print('\n=== BATs RAIZ ===')
for b in pathlib.Path('.').glob('*.bat'):
    print(f'  {b.name}')

print('\n=== PYs RAIZ (legado) ===')
for p in pathlib.Path('.').glob('*.py'):
    print(f'  {p.name}')
