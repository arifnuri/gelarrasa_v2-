"""
Gelar Rasa 2026 - Static Standalone HTML Dashboard Generator
Processes all clean CSV datasets and compiles everything into a 
standalone, 100% serverless index.html that can be opened directly
by double-clicking in any browser (Chrome, Edge, Firefox).
"""
import os
import json
import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
PRECOMP_DIR = os.path.join(DATA_DIR, 'precomputed')

print("[BUILD] Loading datasets...")
df_merged = pd.read_csv(os.path.join(DATA_DIR, 'analysis_daily_merged.csv'))
df_merged['date'] = pd.to_datetime(df_merged['date'])
df_master = pd.read_csv(os.path.join(DATA_DIR, 'stations_master_clean.csv'))
df_quality = pd.read_csv(os.path.join(DATA_DIR, 'station_quality_report.csv'))
df_iku_station = pd.read_csv(os.path.join(DATA_DIR, 'iku_station_year.csv'))

# Load precomputed diurnal & wind rose
with open(os.path.join(PRECOMP_DIR, 'diurnal.json'), 'r') as f:
    diurnal_cache = json.load(f)

with open(os.path.join(PRECOMP_DIR, 'wind_rose.json'), 'r') as f:
    wind_rose_cache = json.load(f)

print("[BUILD] Computing analytics and summaries...")

# 1. Stations & Map features
stats = df_merged.groupby('location_id').agg({
    'pm25': ['mean', 'max'],
    'resp': 'mean',
    'resp_admissions_under5': 'mean',
    'resp_admissions_over60': 'mean'
}).reset_index()
stats.columns = ['location_id', 'pm25_mean', 'pm25_max', 'resp_mean', 'under5_mean', 'over60_mean']
m = pd.merge(df_master, stats, on='location_id', how='left')

stations_list = []
for _, r in m.iterrows():
    mean_pm = round(float(r['pm25_mean']), 1) if pd.notnull(r['pm25_mean']) else 0.0
    if mean_pm <= 15.5:
        cat = 'BAIK'
        color = '#10B981'
    elif mean_pm <= 55.4:
        cat = 'SEDANG'
        color = '#3B82F6'
    elif mean_pm <= 150.4:
        cat = 'TIDAK SEHAT'
        color = '#F59E0B'
    elif mean_pm <= 250.4:
        cat = 'SANGAT TIDAK SEHAT'
        color = '#EF4444'
    else:
        cat = 'BERBAHAYA'
        color = '#881337'

    stations_list.append({
        'location_id': r['location_id'],
        'station_code': r['station_code'],
        'label': r['label'],
        'provinsi': r['provinsi'],
        'kota_kabupaten': r['kota_kabupaten'],
        'karakteristik': r['karakteristik_wilayah'],
        'island': r['island'],
        'site_type': r['site_type'],
        'lat': float(r['latitude_dd']),
        'lng': float(r['longitude_dd']),
        'status': r['status'],
        'pm25_mean': mean_pm,
        'pm25_max': round(float(r['pm25_max']), 1) if pd.notnull(r['pm25_max']) else 0.0,
        'resp_mean': round(float(r['resp_mean']), 1) if pd.notnull(r['resp_mean']) else 0.0,
        'under5_mean': round(float(r['under5_mean']), 1) if pd.notnull(r['under5_mean']) else 0.0,
        'over60_mean': round(float(r['over60_mean']), 1) if pd.notnull(r['over60_mean']) else 0.0,
        'category': cat,
        'marker_color': color,
        'traffic_intensity': float(r['traffic_intensity_per_h']) if pd.notnull(r['traffic_intensity_per_h']) else 0,
        'distance_to_road': float(r['distance_to_road_m']) if pd.notnull(r['distance_to_road_m']) else 0
    })

# 2. Time Series (Daily 7-Day MA & Monthly)
def compute_ts(df_sub):
    # Daily 7-day MA
    g_d = df_sub.groupby('date').agg({'pm25': 'mean'}).reset_index()
    g_d['ma7'] = g_d['pm25'].rolling(7, min_periods=1).mean()
    # Monthly
    df_sub_m = df_sub.copy()
    df_sub_m['ym'] = df_sub_m['date'].dt.to_period('M').astype(str)
    g_m = df_sub_m.groupby('ym').agg({'pm25': 'mean'}).reset_index()

    return {
        'daily': {
            'dates': g_d['date'].dt.strftime('%Y-%m-%d').tolist(),
            'pm25': [round(float(v), 1) if pd.notnull(v) else None for v in g_d['ma7']]
        },
        'monthly': {
            'dates': g_m['ym'].tolist(),
            'pm25': [round(float(v), 1) if pd.notnull(v) else None for v in g_m['pm25']]
        }
    }

ts_all = compute_ts(df_merged)

# 3. Typology Distribution
def simplify_site(st):
    st = str(st).lower()
    if 'peatland' in st or 'gambut' in st:
        return 'Peatland Buffer (Gambut)'
    elif 'traffic' in st or 'roadside' in st:
        return 'Traffic / Roadside'
    elif 'industrial' in st:
        return 'Industrial Perimeter'
    elif 'clean' in st or 'remote' in st:
        return 'Clean / Remote Baseline'
    else:
        return 'Urban Background'

df_merged['site_group'] = df_merged['site_type'].apply(simplify_site)
order = ['Clean / Remote Baseline', 'Urban Background', 'Traffic / Roadside', 'Industrial Perimeter', 'Peatland Buffer (Gambut)']
typology_list = []
for grp in order:
    vals = df_merged[df_merged['site_group'] == grp]['pm25'].dropna()
    if len(vals) > 0:
        typology_list.append({
            'group': grp,
            'mean': round(float(vals.mean()), 1),
            'median': round(float(vals.median()), 1),
            'p25': round(float(vals.quantile(0.25)), 1),
            'p75': round(float(vals.quantile(0.75)), 1),
            'p95': round(float(vals.quantile(0.95)), 1),
            'max': round(float(vals.max()), 1)
        })

# 4. Driver Correlations & Scatter
df_drivers = pd.merge(df_merged, df_master[['location_id', 'distance_to_road_m', 'traffic_intensity_per_h']], on='location_id', how='left')
cols = ['temperature_c', 'humidity_pct', 'wind_speed_ms', 'traffic_intensity_per_h', 'distance_to_road_m']
correlations = {}
for col in cols:
    c = df_drivers[['pm25', col]].dropna().corr().iloc[0, 1]
    correlations[col] = round(float(c), 3) if pd.notnull(c) else 0.0

sample_df = df_drivers.sample(min(120, len(df_drivers)), random_state=42)
scatter_temp = [{'x': round(float(r['temperature_c']), 1), 'y': round(float(r['pm25']), 1)} for _, r in sample_df.iterrows() if pd.notnull(r['temperature_c']) and pd.notnull(r['pm25'])]
scatter_traffic = [{'x': round(float(r['traffic_intensity_per_h']), 1), 'y': round(float(r['pm25']), 1)} for _, r in sample_df.iterrows() if pd.notnull(r['traffic_intensity_per_h']) and pd.notnull(r['pm25'])]

# 5. Distributed Lag Correlations (0-7 Days)
health_vars = {
    'resp_admissions_under5': 'Balita (<5 Thn)',
    'resp_admissions_over60': 'Lansia (>60 Thn)',
    'asthma_emergency_cases': 'Darurat Asma',
    'copd_admissions': 'Rawat Inap PPOK',
    'cvd': 'Kardiovaskular (CVD)',
    'death': 'Mortalitas (Death)'
}
lag_results = {k: [] for k in health_vars.keys()}
for lag in range(0, 8):
    df_lag = df_merged.sort_values(['location_id', 'date']).copy()
    df_lag['pm25_lag'] = df_lag.groupby('location_id')['pm25'].shift(lag)
    for var in health_vars.keys():
        c = df_lag[['pm25_lag', var]].dropna().corr().iloc[0, 1]
        lag_results[var].append(round(float(c), 3) if pd.notnull(c) else 0.0)

# 6. Vulnerability Disparity
bins = [0, 15, 55, 1000]
labels = ['Baik (≤15 µg/m³)', 'Sedang (15–55 µg/m³)', 'Tidak Sehat (>55 µg/m³)']
df_merged['aq_level'] = pd.cut(df_merged['pm25'], bins=bins, labels=labels)
gv = df_merged.groupby('aq_level', observed=False).agg({
    'resp_admissions_under5': 'mean',
    'resp_admissions_over60': 'mean',
    'asthma_emergency_cases': 'mean',
    'copd_admissions': 'mean',
    'death': 'mean'
}).reset_index()
vuln_data = {
    'categories': labels,
    'under5': [round(float(x), 2) for x in gv['resp_admissions_under5']],
    'over60': [round(float(x), 2) for x in gv['resp_admissions_over60']],
    'asthma': [round(float(x), 2) for x in gv['asthma_emergency_cases']],
    'copd': [round(float(x), 2) for x in gv['copd_admissions']],
    'death': [round(float(x), 2) for x in gv['death']]
}

# 7. Audit & Decision Matrix
status_counts = df_quality['status'].value_counts().to_dict()
mq = pd.merge(df_master, df_quality[['location_id', 'coverage_days_pm25', 'frozen_hours', 'overrange_hours']], on='location_id')
h_stats = df_merged.groupby('location_id').agg({'resp': 'mean', 'pm25': 'mean'}).reset_index()
mq = pd.merge(mq, h_stats, on='location_id', how='left')

existing_priorities = []
for _, r in mq.iterrows():
    resp_load = float(r['resp']) if pd.notnull(r['resp']) else 15.0
    cov = float(r['coverage_days_pm25']) if pd.notnull(r['coverage_days_pm25']) else 0.0
    frozen = int(r['frozen_hours'])
    overrange = int(r['overrange_hours'])
    pm_mean = float(r['pm25']) if pd.notnull(r['pm25']) else 30.0

    gap_score = round(((1.0 - cov) * 40) + ((frozen / 500) * 20) + ((overrange / 200) * 15) + (pm_mean / 2), 1)

    action = "Pemantauan Standar"
    tier = "Tier 3 (Normal)"
    if r['status'] == 'EXCLUDED':
        action = "Reaktivasi Total / Penggantian Instrumen Sensor"
        tier = "Tier 1 (Sangat Mendesak)"
    elif r['status'] == 'CAUTION' or frozen > 1000:
        action = "Kalibrasi Ulang Sensor Beku & Audit Jalur Telemetri"
        tier = "Tier 1 (Sangat Mendesak)"
    elif overrange > 500:
        action = "Upgrade Sensor High-Range (Tahan Asap Karhutla Ekstrem)"
        tier = "Tier 2 (Peningkatan Kapasitas)"

    existing_priorities.append({
        'station': r['label'],
        'island': r['island'],
        'site_type': r['site_type'],
        'status': r['status'],
        'coverage_pct': round(cov * 100, 1),
        'resp_burden': round(resp_load, 1),
        'pm25_mean': round(pm_mean, 1),
        'gap_score': gap_score,
        'tier': tier,
        'recommendation': action
    })
existing_priorities.sort(key=lambda x: x['gap_score'], reverse=True)

new_expansion_recommendations = [
    {
        'region': 'Kepulauan Maluku (Ambon / Ternate)',
        'island': 'Maluku',
        'rationale': 'Defisit Geografis Total: 0 stasiun di dataset saat ini (Wilayah Buta Pemantauan Nasional).',
        'proposed_site': 'Urban Coastal Background',
        'priority': 'Prioritas 1 (Ekspansi Wilayah Buta)'
    },
    {
        'region': 'Nusa Tenggara (Kupang / Mataram)',
        'island': 'Nusa Tenggara',
        'rationale': 'Defisit Geografis Total: 0 stasiun di dataset saat ini, iklim kering dengan debu musiman.',
        'proposed_site': 'Regional Background / Savanna',
        'priority': 'Prioritas 1 (Ekspansi Wilayah Buta)'
    },
    {
        'region': 'Kalimantan Selatan (Kawasan Penyangga Gambut Banjar)',
        'island': 'Kalimantan',
        'rationale': 'Buffer hotspot kebakaran lahan gambut berulang yang langsung mengarah ke permukiman padat.',
        'proposed_site': 'Peatland Boundary / Agroforest',
        'priority': 'Prioritas 1 (Proteksi Karhutla)'
    },
    {
        'region': 'Sulawesi Tengah & Tenggara (Kawasan Smelter / Hilirisasi Nikel)',
        'island': 'Sulawesi',
        'rationale': 'Pertumbuhan kawasan industri berat yang belum terpantau oleh 2 stasiun Sulawesi saat ini.',
        'proposed_site': 'Industrial Perimeter',
        'priority': 'Prioritas 2 (Kawasan Industri Hilirisasi)'
    },
    {
        'region': 'Jawa Timur & Barat (Koridor Tol Padat Logistik Pantura)',
        'island': 'Jawa',
        'rationale': 'Densifikasi stasiun roadside untuk memantau emisi kendaraan berat harian secara spesifik.',
        'proposed_site': 'Traffic / Roadside Artery',
        'priority': 'Prioritas 3 (Optimasi Koridor Mobilitas)'
    }
]

# Assemble the MASTER DATA OBJECT
master_bundle = {
    'stations': stations_list,
    'time_series': ts_all,
    'diurnal': diurnal_cache,
    'wind_rose': wind_rose_cache,
    'typology': typology_list,
    'correlations': correlations,
    'scatter_temp': scatter_temp,
    'scatter_traffic': scatter_traffic,
    'lag_analysis': {
        'lags': [f'Lag {i}' for i in range(8)],
        'series': lag_results,
        'labels': health_vars
    },
    'vulnerability': vuln_data,
    'network_audit': {
        'status_counts': status_counts,
        'existing_priorities': existing_priorities,
        'new_expansion': new_expansion_recommendations
    }
}

# Write data.js for zero-server standalone file loading
data_js_path = os.path.join(BASE_DIR, 'data_store.js')
with open(data_js_path, 'w', encoding='utf-8') as f:
    f.write("window.GELAR_RASA_DATA = " + json.dumps(master_bundle, indent=2) + ";\n")

print(f"[BUILD] data_store.js generated successfully at {data_js_path}")
