from __future__ import annotations
import csv, io, re, requests
from services.symbols import US, SA

def discover_us():
    companies, warnings = {}, []
    for url in ('https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt', 'https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt'):
        try:
            res=requests.get(url,timeout=12,headers={'User-Agent':'Mozilla/5.0'})
            res.raise_for_status()
            directory = csv.DictReader(io.StringIO(res.text), delimiter='|')
            if 'Security Name' not in (directory.fieldnames or []):
                raise ValueError('Unexpected directory format')
            for row in directory:
                symbol=(row.get('Symbol') or row.get('ACT Symbol') or '').strip().upper()
                name=(row.get('Security Name') or '').strip()
                if not re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,12}',symbol) or not name: continue
                if row.get('ETF','N')=='Y' or row.get('Test Issue','N')=='Y': continue
                if row.get('Financial Status','N') in ('D','E','Q','G','H'): continue
                if any(word in name.lower() for word in (' warrant',' rights',' preferred',' depositary',' unit ')): continue
                companies[symbol.replace('.','-')]=name
        except Exception as exc:
            warnings.append(f'US directory unavailable: {str(exc)[:100]}')
    if not companies:
        warnings.append('Using limited built-in US symbols; full market coverage unavailable.')
    if warnings:
        companies = {**US, **companies}
    return companies,warnings

def discover_sa():
    companies, warnings={},[]
    for market in ('TASI','NOMU'):
        try:
            count_before = len(companies)
            offset=0
            for _ in range(15):
                res=requests.get('https://api.sahmk.sa/api/v1/companies/',params={'market':market,'limit':200,'offset':offset},timeout=12)
                res.raise_for_status()
                data=res.json()
                rows=data if isinstance(data,list) else data.get('results',data.get('data',[]))
                if isinstance(rows,dict): rows=rows.get('results',[])
                if not isinstance(rows, list):
                    raise ValueError('Unexpected directory format')
                if not rows:
                    break
                for row in rows:
                    if not isinstance(row,dict): continue
                    symbol=str(row.get('symbol') or row.get('ticker') or '').strip().upper().removesuffix('.SR')
                    kind=str(row.get('security_type') or 'equity').lower()
                    if re.fullmatch(r'\d{4,5}',symbol) and kind in ('equity','stock','common stock') and not row.get('is_etf',False) and str(row.get('status','active')).lower() not in ('inactive','delisted','suspended'):
                        companies[symbol+'.SR']=str(row.get('name_ar') or row.get('name_en') or row.get('name') or symbol)
                offset+=len(rows)
                if len(rows)<200: break
            if len(companies) == count_before:
                warnings.append(f'{market}: لم يُرجع الدليل رموزًا جديدة صالحة.')
        except Exception as exc:
            warnings.append(f'{market} directory unavailable: {str(exc)[:100]}')
    if not companies:
        warnings.append('Using limited built-in Saudi symbols; full market coverage unavailable.')
    if warnings:
        companies = {**SA, **companies}
    return companies,warnings

def discover(market):
    result,warnings={},[]
    if market in ('الأمريكي','السوقان معًا'):
        u,w=discover_us();result.update(u);warnings.extend(w)
    if market in ('السعودي','السوقان معًا'):
        u,w=discover_sa();result.update(u);warnings.extend(w)
    return result,warnings
