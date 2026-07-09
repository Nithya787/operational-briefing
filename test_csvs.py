import pandas as pd

files = {
    'auth_user': 'auth_user.csv',
    'api_profile': 'api_profile.csv',
    'api_collector': 'api_collector.csv',
    'api_store': 'api_store.csv',
    'api_company': 'api_company.csv',
    'api_systemevent': 'api_systemeventalert.csv',
    'api_deposit': 'api_deposit.csv',
    'api_service': 'api_olynsservice.csv',
    'api_csddropoff': 'api_csddropoff.csv',
    'api_csddropoffbag': 'api_csddropoffbag.csv',
}

for name, path in files.items():
    try:
        df = pd.read_csv(path, encoding='latin-1')
        print(f'OK: {name} — {len(df)} rows')
    except Exception as e:
        print(f'ERROR: {name} — {e}')