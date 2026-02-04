import streamlit as st
import numpy as np
import pandas as pd
import yfinance as yf
import requests
import datetime

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Amınoğlu Ultra Boğa", page_icon="🛡️", layout="wide")

# --- BAŞLIK ---
st.title("🛡️ Amınoğlu Ultra Boğa Değerleme A.Ş. (v15.0)")
st.markdown("""
**Muhafazakar & Gerçekçi:** Canlı faiz oranlarını kullanır, güvenlik marjı bırakır. 
*Faizler yükseldiğinde hisse değerlerinin düşmesi normaldir.*
""")

# --- YAN MENÜ ---
with st.sidebar:
    st.header("🔍 Analiz")
    ticker = st.text_input("Hisse Sembolü", value="LMT").upper()
    
    st.markdown("---")
    st.subheader("🔑 API Ayarları")
    default_key = "XcQER6LvWluszHZVly18nqMMxz8Xj1GO"
    api_key = st.text_input("FMP API Key", value=default_key, type="password")
    
    st.info("Mod: **MUHAFAZAKAR** (Güvenlik Marjı Aktif)")

# --- YARDIMCI ---
def safe_float(val):
    try:
        if val is None or np.isnan(val): return 0.0
        return float(val)
    except:
        return 0.0

# --- 1. CANLI FAİZ ORANI (RISK FREE RATE) ---
@st.cache_data(ttl=3600)
def get_live_risk_free_rate(currency="USD"):
    try:
        if currency == "USD":
            # ABD 10 Yıllık Devlet Tahvili (^TNX)
            tnx = yf.Ticker("^TNX")
            rate = tnx.fast_info.get('last_price', None)
            
            if rate is None:
                hist = tnx.history(period="1d")
                rate = hist['Close'].iloc[-1] if not hist.empty else 4.2
            
            # Yahoo bunu tam sayı verir (örn: 4.2), biz yüzde yapalım
            return rate / 100
        
        elif currency == "TRY":
            # Türkiye için "Makul/Muhafazakar" Beklenti
            # Şu an %45 olsa da, model uzun vadeyi (10 yıl) ölçer.
            # 10 Yıllık ortalama beklenti %30 civarıdır (Muhafazakar)
            return 0.30
            
        else:
            return 0.04 # Euro vs.

    except:
        return 0.045 # Veri yoksa %4.5 al (Muhafazakar)

# --- 2. VERİ ÇEKME MOTORU (HİBRİT) ---
def get_data_hybrid(symbol, key):
    # .IS (BIST) Kontrolü
    if ".IS" in symbol:
        return get_data_yahoo(symbol)
    
    # ABD için FMP
    data, err = get_data_fmp(symbol, key)
    if data: return data, None
    
    # FMP patlarsa Yahoo
    return get_data_yahoo(symbol)

def get_data_fmp(symbol, key):
    BASE_URL = "https://financialmodelingprep.com/stable"
    try:
        res = requests.get(f"{BASE_URL}/quote?symbol={symbol}&apikey={key}", timeout=2).json()
        if not res: return None, "FMP Bulamadı"
        quote = res[0]
        
        prof = requests.get(f"{BASE_URL}/profile?symbol={symbol}&apikey={key}").json()[0]
        inc = requests.get(f"{BASE_URL}/income-statement?symbol={symbol}&limit=1&apikey={key}").json()[0]
        bal = requests.get(f"{BASE_URL}/balance-sheet-statement?symbol={symbol}&limit=1&apikey={key}").json()[0]

        data = {
            'source': 'FMP (Resmi)',
            'ticker': symbol,
            'currency': prof.get('currency', 'USD'),
            'current_price': safe_float(quote.get('price')),
            'shares': safe_float(quote.get('marketCap')) / safe_float(quote.get('price')) / 1e6,
            'beta': safe_float(prof.get('beta', 1.0)),
            'total_debt': safe_float(bal.get('totalDebt')) / 1e6,
            'cash': safe_float(bal.get('cashAndCashEquivalents')) / 1e6,
            'revenue': safe_float(inc.get('revenue')) / 1e6,
            'ebit': safe_float(inc.get('operatingIncome')) / 1e6,
        }
        data['ebit_margin'] = data['ebit'] / data['revenue'] if data['revenue'] else 0.10
        return data, None
    except:
        return None, "FMP Hatası"

def get_data_yahoo(symbol):
    try:
        s = yf.Ticker(symbol)
        p = s.fast_info.get('last_price', None)
        if not p:
            h = s.history(period="1d")
            p = h['Close'].iloc[-1] if not h.empty else None
        
        if not p: return None, "Fiyat Yok"
            
        try:
            bs = s.balance_sheet
            ist = s.financials
            debt = safe_float(bs.iloc[:,0].get('Total Debt'))/1e6 if not bs.empty else 0
            cash = safe_float(bs.iloc[:,0].get('Cash And Cash Equivalents'))/1e6 if not bs.empty else 0
            rev = safe_float(ist.iloc[:,0].get('Total Revenue'))/1e6 if not ist.empty else 0
            ebit = safe_float(ist.iloc[:,0].get('EBIT'))/1e6 if not ist.empty else 0
            if ebit==0: ebit = safe_float(ist.iloc[:,0].get('Operating Income'))/1e6
        except:
            debt, cash, rev, ebit = 0, 0, 0, 0
            
        data = {
            'source': 'Yahoo (Yedek)',
            'ticker': symbol,
            'currency': s.fast_info.get('currency', 'TRY' if ".IS" in symbol else 'USD'),
            'current_price': safe_float(p),
            'shares': safe_float(s.fast_info.get('shares', 1e6))/1e6,
            'beta': 1.0,
            'total_debt': debt, 'cash': cash, 'revenue': rev, 'ebit': ebit,
            'ebit_margin': ebit/rev if rev else 0.10
        }
        return data, None
    except:
        return None, "Yahoo Hatası"

# --- 3. MUHAFAZAKAR HESAPLAMA MOTORU ---
def calculate_conservative(data):
    # 1. CANLI FAİZ (Zemin)
    rf = get_live_risk_free_rate(data['currency'])
    
    # 2. PİYASA RİSK PRİMİ (Standart)
    # Boğa modunda %4.5 almıştık. Muhafazakar modda standart %6.0 alıyoruz.
    rm = 0.06 
    
    # 3. BETA (Risk Katsayısı)
    # Şirketin riskini küçümseme. Beta 0.8'in altındaysa bile en az 0.8 al.
    beta = data.get('beta', 1.0)
    beta = max(0.8, beta) 
    
    cost_equity = rf + (beta * rm)
    
    # Borç Maliyeti (Risk Free + Spread)
    # Faizler yüksekse borçlanmak pahalıdır.
    cost_debt = rf + 0.025 # %2.5 Spread ekle
    tax_rate = 0.21
    
    # WACC
    market_cap = data['shares'] * data['current_price']
    total_val = market_cap + data['total_debt']
    if total_val <= 0: total_val = 1.0
    w_e = market_cap / total_val
    w_d = data['total_debt'] / total_val
    
    wacc = (w_e * cost_equity) + (w_d * cost_debt * (1 - tax_rate))
    
    # FREN YOK! 
    # Faizler %5 ise ve risk primiyle WACC %10 çıkıyorsa, %10 olarak kalsın.
    # Şirketi yapay olarak değerli göstermiyoruz.
    
    # 4. GÜVENLİK MARJI (Growth vs WACC Gap)
    # Boğa modunda %1.5 fark bırakmıştık. 
    # Burada en az %3.0 veya %3.5 FARK OLMALI.
    # Sonsuz büyüme (g) genelde GSYH büyümesi kadardır (%2.5 - %3.0).
    perpetual_g = 0.025 
    
    if data['currency'] == 'TRY':
        perpetual_g = 0.10 # TR Enflasyonuna göre muhafazakar büyüme
        
    # Eğer WACC ile g birbirine çok yakınsa, g'yi düşür.
    safety_margin = 0.035 # %3.5 Güvenlik marjı
    if wacc - perpetual_g < safety_margin:
        perpetual_g = wacc - safety_margin

    # 5. YATIRIM ORANI (Reinvestment)
    # Şirketler hayatta kalmak için yatırım yapmalıdır.
    # Nakdin %35'i içeriye gider (Boğa modunda %10 idi).
    reinvestment_rate = 0.35 
    
    # 6. PROJEKSİYON
    years = 10
    
    # Marjları iyileştirme, mevcudu koru (veya sektör ortalamasına çek)
    current_margin = data.get('ebit_margin', 0.10)
    # Çok uçuk marj varsa (%40 üzeri), rekabet gelir düşer diye varsay
    target_margin = min(current_margin, 0.30) 
    
    margins = np.linspace(current_margin, target_margin, years)
    
    # Büyüme: İlk yıllar biraz hızlı, sonra terminale düş
    start_g = 0.08 if data['currency'] == 'USD' else 0.25
    growth_rates = np.linspace(start_g, perpetual_g, years)
    
    fcffs = []
    last_rev = data['revenue']
    
    for i in range(years):
        rev = last_rev * (1 + growth_rates[i])
        nopat = rev * margins[i] * (1 - tax_rate)
        
        # Ciddi yatırım oranı
        fcff = nopat * (1 - reinvestment_rate)
        fcffs.append(fcff)
        last_rev = rev
        
    term_val = fcffs[-1] * (1+perpetual_g) / (wacc - perpetual_g)
    pv = np.sum([f / ((1+wacc)**(i+1)) for i, f in enumerate(fcffs)]) + (term_val / ((1+wacc)**years))
    
    equity = pv - data['total_debt'] + data['cash']
    price = equity / data['shares']
    if price < 0: price = 0.0
    
    return price, fcffs, {"rf": rf, "wacc": wacc, "g": perpetual_g, "gap": wacc-perpetual_g}

# --- EKRAN ---
if st.button("MUHAFAZAKAR ANALİZ ET", type="primary"):
    with st.spinner('Faizler kontrol ediliyor, balonlar söndürülüyor...'):
        data, err = get_data_hybrid(ticker, api_key)
        
        if data:
            price, flows, metrics = calculate_conservative(data)
            
            # Üst Bilgi
            st.success(f"✅ Veri Kaynağı: **{data['source']}**")
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Piyasa Fiyatı", f"{data['current_price']:.2f} {data['currency']}")
            c2.metric("Muhafazakar Değer", f"{price:.2f} {data['currency']}")
            
            upside = (price / data['current_price']) - 1 if data['current_price'] else 0
            color = "normal" if upside > 0 else "inverse"
            c3.metric("Güvenlik Marjı", f"%{upside*100:.1f}", delta_color=color)
            
            st.markdown("---")
            
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Canlı Faiz (Risk Free)", f"%{metrics['rf']*100:.2f}")
            k2.metric("WACC (Maliyet)", f"%{metrics['wacc']*100:.2f}", help="Faizler yüksek olduğu için WACC yüksek çıkar.")
            k3.metric("Terminal Büyüme", f"%{metrics['g']*100:.2f}")
            k4.metric("Güvenlik Aralığı", f"%{metrics['gap']*100:.2f}", help="WACC ile Büyüme arasındaki fark. Ne kadar yüksekse o kadar güvenli.")
            
            st.bar_chart(flows)
            
            if upside < 0:
                st.warning(f"⚠️ **SONUÇ:** Bu modelle hisse **%{abs(upside*100):.1f} pahalı** görünüyor. Bunun sebebi yüksek faiz ortamında şirketin gelecekteki nakitlerinin bugünkü değerinin düşmesidir. Benjamin Graham olsa 'Bekle' derdi.")
            else:
                st.success(f"🎯 **FIRSAT:** Yüksek faize ve muhafazakar varsayımlara rağmen hisse hala iskontolu! Bu gerçek bir 'Değer Yatırımı' fırsatı olabilir.")

        else:
            st.error("Veri alınamadı. Manuel giriş gerekebilir.")
            with st.expander("Manuel Giriş", expanded=True):
                 with st.form("manual"):
                    c1, c2 = st.columns(2)
                    m_price = c1.number_input("Fiyat", value=100.0)
                    m_shares = c2.number_input("Hisse (Milyon)", value=100.0)
                    m_rev = c1.number_input("Ciro (Milyon)", value=10000.0)
                    m_ebit = c2.number_input("EBIT", value=2000.0)
                    m_debt = c1.number_input("Borç", value=1000.0)
                    m_cash = c2.number_input("Nakit", value=500.0)
                    if st.form_submit_button("HESAPLA"):
                        st.info("Hesaplama butonu yukarıda çalışır.")
