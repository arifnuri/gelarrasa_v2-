"""
Gelar Rasa 2026 - Air Quality & Health Surveillance Dashboard Backend
Built with Python (Flask, Pandas, NumPy)
"""
import os
import json
import numpy as np
import pandas as pd
from flask import Flask, jsonify, render_template, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
PRECOMP_DIR = os.path.join(DATA_DIR, 'precomputed')

app = Flask(__name__, template_folder='templates', static_folder='static')

# -------------------------------------------------------------
# In-Memory Data Store (Loaded once at startup for instant API)
# -------------------------------------------------------------
print("[STARTUP] Loading clean datasets...")
df_merged = pd.read_csv(os.path.join(DATA_DIR, 'analysis_daily_merged.csv'))
df_merged['date'] = pd.to_datetime(df_merged['date'])
df_master = pd.read_csv(os.path.join(DATA_DIR, 'stations_master_clean.csv'))
df_quality = pd.read_csv(os.path.join(DATA_DIR, 'station_quality_report.csv'))
df_iku_city = pd.read_csv(os.path.join(DATA_DIR, 'iku_city_year.csv'))
df_iku_station = pd.read_csv(os.path.join(DATA_DIR, 'iku_station_year.csv'))

# Precomputed Diurnal & Wind Rose
with open(os.path.join(PRECOMP_DIR, 'diurnal.json'), 'r') as f:
    diurnal_cache = json.load(f)

with open(os.path.join(PRECOMP_DIR, 'wind_rose.json'), 'r') as f:
    wind_rose_cache = json.load(f)

print("[STARTUP] Datasets loaded successfully. Ready to serve!")

# -------------------------------------------------------------
# Helper Functions
# -------------------------------------------------------------
def filter_dataframe(df, island=None, site_type=None, station=None, season_karhutla=False):
    filtered = df.copy()
    if island and island != 'ALL':
        filtered = filtered[filtered['island'] == island]
    if site_type and site_type != 'ALL':
        filtered = filtered[filtered['site_type'].str.contains(site_type, case=False, na=False)]
    if station and station != 'ALL':
        filtered = filtered[filtered['location_id'] == station]
    if season_karhutla:
        # Months 7 to 10 (July to October)
        filtered = filtered[filtered['month'].isin([7, 8, 9, 10])]
    return filtered


# -------------------------------------------------------------
# Frontend Routes
# -------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')


# -------------------------------------------------------------
# API Endpoints
# -------------------------------------------------------------
@app.route('/api/metadata')
def get_metadata():
    """Return filter options and station catalog"""
    islands = sorted(df_master['island'].dropna().unique().tolist())
    site_types = [
        'Urban Background',
        'Traffic / Roadside',
        'Industrial Perimeter',
        'Peatland Buffer',
        'Regional / Clean Background'
    ]
    stations = []
    for _, r in df_master.iterrows():
        stations.append({
            'location_id': r['location_id'],
            'station_code': r['station_code'],
            'label': r['label'],
            'provinsi': r['provinsi'],
            'island': r['island'],
            'site_type': r['site_type'],
            'latitude': float(r['latitude_dd']),
            'longitude': float(r['longitude_dd']),
            'status': r['status'],
            'traffic_intensity': float(r['traffic_intensity_per_h']) if pd.notnull(r['traffic_intensity_per_h']) else 0,
            'distance_to_road': float(r['distance_to_road_m']) if pd.notnull(r['distance_to_road_m']) else 0,
            'notes': str(r['notes']) if pd.notnull(r['notes']) else ''
        })
    return jsonify({
        'islands': islands,
        'site_types': site_types,
        'stations': stations,
        'total_stations': len(stations),
        'period_start': '2024-01-01',
        'period_end': '2026-10-14'
    })


@app.route('/api/kpi')
def get_kpi():
    """Compute top executive KPI cards according to regulations (PP 22/2021 & WHO)"""
    island = request.args.get('island', 'ALL')
    site_type = request.args.get('site_type', 'ALL')
    station = request.args.get('station', 'ALL')
    karhutla = request.args.get('karhutla', 'false').lower() == 'true'

    df_sub = filter_dataframe(df_merged, island, site_type, station, karhutla)

    # 1. PM2.5 Mean & Max
    pm25_valid = df_sub['pm25'].dropna()
    pm25_mean = round(float(pm25_valid.mean()), 2) if len(pm25_valid) > 0 else 0.0
    pm25_max = round(float(pm25_valid.max()), 2) if len(pm25_valid) > 0 else 0.0

    # 2. Exceedances
    # PP 22/2021 threshold = 55 ug/m3
    # WHO 2021 threshold = 15 ug/m3
    total_days = len(pm25_valid)
    exceed_pp22 = int((pm25_valid > 55.0).sum())
    pct_exceed_pp22 = round((exceed_pp22 / total_days * 100), 1) if total_days > 0 else 0.0

    exceed_who = int((pm25_valid > 15.0).sum())
    pct_exceed_who = round((exceed_who / total_days * 100), 1) if total_days > 0 else 0.0

    # 3. IKU (Indeks Kualitas Udara)
    # Take latest eligible IKU from iku_station_year
    iku_sub = df_iku_station.copy()
    if island != 'ALL':
        iku_sub = iku_sub[iku_sub['island'] == island]
    if station != 'ALL':
        iku_sub = iku_sub[iku_sub['location_id'] == station]
    
    iku_valid = iku_sub['iku'].dropna()
    iku_mean = round(float(iku_valid.mean()), 1) if len(iku_valid) > 0 else 82.4

    # 4. Critical vs Cleanest station
    st_means = df_sub.groupby('station')['pm25'].mean().reset_index()
    if len(st_means) > 0:
        crit_row = st_means.loc[st_means['pm25'].idxmax()]
        clean_row = st_means.loc[st_means['pm25'].idxmin()]
        critical_station = f"{crit_row['station']} ({crit_row['pm25']:.1f} µg/m³)"
        cleanest_station = f"{clean_row['station']} ({clean_row['pm25']:.1f} µg/m³)"
    else:
        critical_station = "N/A"
        cleanest_station = "N/A"

    return jsonify({
        'pm25_mean': pm25_mean,
        'pm25_max': pm25_max,
        'pct_exceed_pp22': pct_exceed_pp22,
        'exceed_pp22_days': exceed_pp22,
        'pct_exceed_who': pct_exceed_who,
        'exceed_who_days': exceed_who,
        'total_observed_days': total_days,
        'iku_mean': iku_mean,
        'critical_station': critical_station,
        'cleanest_station': cleanest_station
    })


@app.route('/api/map_stations')
def get_map_stations():
    """Return geojson/markers for Leaflet map with statistics"""
    island = request.args.get('island', 'ALL')
    site_type = request.args.get('site_type', 'ALL')
    karhutla = request.args.get('karhutla', 'false').lower() == 'true'

    df_sub = filter_dataframe(df_merged, island, site_type, 'ALL', karhutla)

    # Compute per-location stats
    stats = df_sub.groupby('location_id').agg({
        'pm25': ['mean', 'max'],
        'resp': 'mean',
        'resp_admissions_under5': 'mean',
        'resp_admissions_over60': 'mean'
    }).reset_index()
    stats.columns = ['location_id', 'pm25_mean', 'pm25_max', 'resp_mean', 'under5_mean', 'over60_mean']

    # Merge with master station
    m = pd.merge(df_master, stats, on='location_id', how='left')

    features = []
    for _, r in m.iterrows():
        mean_pm = round(float(r['pm25_mean']), 1) if pd.notnull(r['pm25_mean']) else 0.0
        # Categorize ISPU
        if mean_pm <= 15.5:
            cat = 'BAIK'
            color = '#10B981' # emerald
        elif mean_pm <= 55.4:
            cat = 'SEDANG'
            color = '#3B82F6' # blue
        elif mean_pm <= 150.4:
            cat = 'TIDAK SEHAT'
            color = '#F59E0B' # amber
        elif mean_pm <= 250.4:
            cat = 'SANGAT TIDAK SEHAT'
            color = '#EF4444' # red
        else:
            cat = 'BERBAHAYA'
            color = '#881337' # maroon

        features.append({
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
            'marker_color': color
        })

    return jsonify(features)


@app.route('/api/time_series')
def get_time_series():
    """Return aggregated time-series for trend chart with PP22 and WHO threshold"""
    island = request.args.get('island', 'ALL')
    site_type = request.args.get('site_type', 'ALL')
    station = request.args.get('station', 'ALL')
    freq = request.args.get('freq', 'D') # 'D' or 'M'
    karhutla = request.args.get('karhutla', 'false').lower() == 'true'

    df_sub = filter_dataframe(df_merged, island, site_type, station, karhutla)

    if freq == 'M':
        # Group by Year-Month
        df_sub['ym'] = df_sub['date'].dt.to_period('M').astype(str)
        g = df_sub.groupby('ym').agg({
            'pm25': 'mean',
            'pm10': 'mean',
            'no2': 'mean',
            'so2': 'mean'
        }).reset_index()
        dates = g['ym'].tolist()
        pm25 = [round(float(v), 2) if pd.notnull(v) else None for v in g['pm25']]
        pm10 = [round(float(v), 2) if pd.notnull(v) else None for v in g['pm10']]
        no2 = [round(float(v), 2) if pd.notnull(v) else None for v in g['no2']]
        so2 = [round(float(v), 2) if pd.notnull(v) else None for v in g['so2']]
    else:
        # Group by date
        g = df_sub.groupby('date').agg({
            'pm25': 'mean',
            'pm10': 'mean',
            'no2': 'mean',
            'so2': 'mean'
        }).reset_index()
        # Compute 7-day moving average
        g['pm25_ma7'] = g['pm25'].rolling(window=7, min_periods=1).mean()
        dates = g['date'].dt.strftime('%Y-%m-%d').tolist()
        pm25 = [round(float(v), 2) if pd.notnull(v) else None for v in g['pm25_ma7']]
        pm10 = [round(float(v), 2) if pd.notnull(v) else None for v in g['pm10']]
        no2 = [round(float(v), 2) if pd.notnull(v) else None for v in g['no2']]
        so2 = [round(float(v), 2) if pd.notnull(v) else None for v in g['so2']]

    return jsonify({
        'dates': dates,
        'pm25': pm25,
        'pm10': pm10,
        'no2': no2,
        'so2': so2,
        'pp22_limit': 55.0,
        'who_limit': 15.0
    })


@app.route('/api/diurnal')
def get_diurnal():
    """Return 24h x 7d heatmap data"""
    station = request.args.get('station', 'ALL')
    if station in diurnal_cache:
        data = diurnal_cache[station]
    else:
        data = diurnal_cache['ALL']
    return jsonify(data)


@app.route('/api/typology')
def get_typology():
    """Return distribution of PM2.5 across site types"""
    island = request.args.get('island', 'ALL')
    karhutla = request.args.get('karhutla', 'false').lower() == 'true'

    df_sub = filter_dataframe(df_merged, island, 'ALL', 'ALL', karhutla)

    # Simplified categorization for high level view
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

    df_sub['site_group'] = df_sub['site_type'].apply(simplify_site)
    res = []
    order = ['Clean / Remote Baseline', 'Urban Background', 'Traffic / Roadside', 'Industrial Perimeter', 'Peatland Buffer (Gambut)']
    for grp in order:
        vals = df_sub[df_sub['site_group'] == grp]['pm25'].dropna()
        if len(vals) > 0:
            res.append({
                'group': grp,
                'mean': round(float(vals.mean()), 2),
                'median': round(float(vals.median()), 2),
                'p25': round(float(vals.quantile(0.25)), 2),
                'p75': round(float(vals.quantile(0.75)), 2),
                'p95': round(float(vals.quantile(0.95)), 2),
                'max': round(float(vals.max()), 2)
            })
    return jsonify(res)


@app.route('/api/wind_rose')
def get_wind_rose():
    """Return polar wind rose data"""
    station = request.args.get('station', 'ALL')
    if station in wind_rose_cache:
        data = wind_rose_cache[station]
    else:
        data = wind_rose_cache['ALL']
    return jsonify(data)


@app.route('/api/drivers_correlation')
def get_drivers():
    """Calculate correlations between PM2.5 and meteorological/traffic variables"""
    island = request.args.get('island', 'ALL')
    site_type = request.args.get('site_type', 'ALL')
    station = request.args.get('station', 'ALL')
    karhutla = request.args.get('karhutla', 'false').lower() == 'true'

    df_sub = filter_dataframe(df_merged, island, site_type, station, karhutla)

    # Merge distance_to_road & traffic_intensity from master
    df_with_m = pd.merge(df_sub, df_master[['location_id', 'distance_to_road_m', 'traffic_intensity_per_h']], on='location_id', how='left')

    cols = ['temperature_c', 'humidity_pct', 'wind_speed_ms', 'traffic_intensity_per_h', 'distance_to_road_m']
    corr_dict = {}
    for col in cols:
        c = df_with_m[['pm25', col]].dropna().corr().iloc[0, 1]
        corr_dict[col] = round(float(c), 3) if pd.notnull(c) else 0.0

    # Sample scatter points (max 150 points for fast UI render)
    sample_df = df_with_m.sample(min(150, len(df_with_m)), random_state=42)
    scatter_temp = [{'x': round(float(r['temperature_c']), 1), 'y': round(float(r['pm25']), 1)} for _, r in sample_df.iterrows() if pd.notnull(r['temperature_c']) and pd.notnull(r['pm25'])]
    scatter_traffic = [{'x': round(float(r['traffic_intensity_per_h']), 1), 'y': round(float(r['pm25']), 1)} for _, r in sample_df.iterrows() if pd.notnull(r['traffic_intensity_per_h']) and pd.notnull(r['pm25'])]

    return jsonify({
        'correlations': corr_dict,
        'scatter_temp': scatter_temp,
        'scatter_traffic': scatter_traffic
    })


@app.route('/api/health_lag')
def get_health_lag():
    """Distributed lag correlation analysis from Lag 0 to Lag 7"""
    island = request.args.get('island', 'ALL')
    station = request.args.get('station', 'ALL')

    df_sub = filter_dataframe(df_merged, island, 'ALL', station, False).sort_values(['location_id', 'date'])

    lags = list(range(0, 8))
    health_vars = {
        'resp_admissions_under5': 'Balita (<5 Thn)',
        'resp_admissions_over60': 'Lansia (>60 Thn)',
        'asthma_emergency_cases': 'Darurat Asma',
        'copd_admissions': 'Rawat Inap PPOK',
        'cvd': 'Kardiovaskular (CVD)',
        'death': 'Mortalitas (Death)'
    }

    result = {k: [] for k in health_vars.keys()}
    for lag in lags:
        df_lag = df_sub.copy()
        df_lag['pm25_lag'] = df_lag.groupby('location_id')['pm25'].shift(lag)
        for var in health_vars.keys():
            c = df_lag[['pm25_lag', var]].dropna().corr().iloc[0, 1]
            result[var].append(round(float(c), 3) if pd.notnull(c) else 0.0)

    return jsonify({
        'lags': [f'Lag {i}' for i in lags],
        'series': result,
        'labels': health_vars
    })


@app.route('/api/health_vulnerability')
def get_health_vulnerability():
    """Compare Under 5 vs Over 60 admissions across air quality levels"""
    island = request.args.get('island', 'ALL')
    station = request.args.get('station', 'ALL')

    df_sub = filter_dataframe(df_merged, island, 'ALL', station, False)

    bins = [0, 15, 55, 1000]
    labels = ['Baik (≤15 µg/m³)', 'Sedang (15–55 µg/m³)', 'Tidak Sehat (>55 µg/m³)']
    df_sub['aq_level'] = pd.cut(df_sub['pm25'], bins=bins, labels=labels)

    g = df_sub.groupby('aq_level', observed=False).agg({
        'resp_admissions_under5': 'mean',
        'resp_admissions_over60': 'mean',
        'asthma_emergency_cases': 'mean',
        'copd_admissions': 'mean',
        'death': 'mean'
    }).reset_index()

    return jsonify({
        'categories': labels,
        'under5': [round(float(x), 2) for x in g['resp_admissions_under5']],
        'over60': [round(float(x), 2) for x in g['resp_admissions_over60']],
        'asthma': [round(float(x), 2) for x in g['asthma_emergency_cases']],
        'copd': [round(float(x), 2) for x in g['copd_admissions']],
        'death': [round(float(x), 2) for x in g['death']]
    })


@app.route('/api/network_audit')
def get_network_audit():
    """Audit station health, reliability, and coverage"""
    status_counts = df_quality['status'].value_counts().to_dict()
    
    # Island coverage breakdown
    island_summary = df_master.groupby('island').agg({
        'station_code': 'count',
        'distance_to_road_m': 'mean',
        'traffic_intensity_per_h': 'mean'
    }).reset_index()
    island_summary.columns = ['island', 'station_count', 'avg_road_dist', 'avg_traffic']

    stations_audit = []
    for _, r in df_quality.iterrows():
        stations_audit.append({
            'location_id': r['location_id'],
            'label': r['label'],
            'island': r['island'],
            'site_type': r['site_type'],
            'status': r['status'],
            'coverage_pm25': round(float(r['coverage_pm25']) * 100, 1),
            'coverage_days': round(float(r['coverage_days_pm25']) * 100, 1) if pd.notnull(r['coverage_days_pm25']) else 0.0,
            'frozen_hours': int(r['frozen_hours']),
            'overrange_hours': int(r['overrange_hours']),
            'baseline_pm25': float(r['baseline_pm25'])
        })

    return jsonify({
        'status_counts': status_counts,
        'islands': island_summary.to_dict(orient='records'),
        'stations': stations_audit
    })


@app.route('/api/priority_matrix')
def get_priority_matrix():
    """Prescriptive Decision Matrix (Composite Priority Index) for new station expansion"""
    # 1. Existing station health burden vs sensor coverage
    m = pd.merge(df_master, df_quality[['location_id', 'coverage_days_pm25', 'frozen_hours', 'overrange_hours']], on='location_id')
    h_stats = df_merged.groupby('location_id').agg({
        'resp': 'mean',
        'resp_admissions_under5': 'mean',
        'pm25': 'mean'
    }).reset_index()
    m = pd.merge(m, h_stats, on='location_id', how='left')

    # Calculate gap score for existing stations (higher = needs urgent repair/re-calibration)
    existing_priorities = []
    for _, r in m.iterrows():
        resp_load = float(r['resp']) if pd.notnull(r['resp']) else 15.0
        cov = float(r['coverage_days_pm25']) if pd.notnull(r['coverage_days_pm25']) else 0.0
        frozen = int(r['frozen_hours'])
        overrange = int(r['overrange_hours'])
        pm_mean = float(r['pm25']) if pd.notnull(r['pm25']) else 30.0

        # Urgent need index: high disease burden + low coverage + frozen/overrange
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

    # Sort descending by gap score
    existing_priorities.sort(key=lambda x: x['gap_score'], reverse=True)

    # 2. Recommendations for brand NEW expansion locations
    new_locations_rec = [
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

    return jsonify({
        'existing_audit_priority': existing_priorities,
        'new_expansion_recommendations': new_locations_rec
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("\n===========================================================")
    print("[SERVER] Gelar Rasa 2026 Dashboard Server is running!")
    print(f"[SERVER] Local URL: http://127.0.0.1:{port}")
    print("===========================================================\n")
    app.run(host='0.0.0.0', port=port, debug=False)
