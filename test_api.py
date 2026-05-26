import sys, json

raw = sys.stdin.read()
try:
    data = json.loads(raw)
    records = data.get('data', [])
    print('Total records:', len(records))
    if records:
        print('\nFields in first record:')
        for k, v in records[0].items():
            print(f'  {repr(k)}: {repr(v)}')
    else:
        print('Raw response:', raw[:500])
except Exception as e:
    print('Parse error:', e)
    print('Raw:', raw[:500])
