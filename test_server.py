import os
import sys
import time
import subprocess
import urllib.request

server_proc = subprocess.Popen([sys.executable, 'D:/dwonload dari crome/lomba gelar rasa/hasil sementara/gelar_rasa_dashboard/app.py'])
time.sleep(3)

try:
    for endpoint in ['/api/metadata', '/api/kpi', '/api/map_stations', '/api/time_series', '/api/diurnal', '/api/typology', '/api/wind_rose', '/api/drivers_correlation', '/api/health_lag', '/api/health_vulnerability', '/api/network_audit', '/api/priority_matrix']:
        url = f'http://127.0.0.1:5000{endpoint}'
        req = urllib.request.urlopen(url)
        print(f'{endpoint}: {req.status} OK')
    print("\nAll 12 endpoints responded with 200 OK!")
finally:
    server_proc.terminate()
