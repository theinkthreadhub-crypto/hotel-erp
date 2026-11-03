import urllib.request
import time

time.sleep(10)
for path in ['hotel_erp.html', 'horeca-icon-dark.png', 'sw.js', 'manifest.json']:
    url = f'https://hotel.setupro.in/{path}?_v={int(time.time())}'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Cache-Control': 'no-cache'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
            age = resp.headers.get('age')
            print(f'{path:25}: Status {resp.status}, Size {len(data)}, Age: {age}')
    except Exception as e:
        print(f'{path:25}: {e}')

