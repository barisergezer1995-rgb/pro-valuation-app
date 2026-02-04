import streamlit as st
import numpy as np
import pandas as pd
import yfinance as yf
import requests
import datetime

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Amınoğlu Realist", page_icon="⚖️", layout="wide")

# --- BAŞLIK ---
st.title("⚖️ Amınoğlu Realist (v16.0)")
st.markdown("""
**Dengeli Mod:** Türkiye için **Enflasyon Ayarlı**, ABD için **Canlı Faizli**.
*Ne Polyanna, Ne Cenaze Kaldırıcısı. Tam kararında.*
""")

# --- YAN MENÜ ---
with st.sidebar:
    st.header("🔍 Analiz")
    ticker = st.text_input("Hisse Sembolü", value="THYAO.IS").upper()
    
    st.markdown("---")
    st.subheader("🔑 API Ayarları")
    default_key = "XcQER6LvWluszHZVly18nqMMxz8Xj1GO"
    api_key = st.text_input("FMP API Key", value=default_key, type="password")
    
    st.success("Mod: **REALİST** (TR Enflasyon Koruması Aktif)")

# --- YARDIMCI ---
def safe_float(val):
    try:
        if val is None or np.isnan(val): return 0.0
        return float(val)
    except:
        return 0.0

# --- 1. CANLI FAİZ (RISK FREE RATE) ---
@st.cache_data(ttl=3600)
def get_live_risk_free_rate(currency="USD"):
    try:
        if currency == "USD":
            # ABD için canlı veriyi çek
            tnx = yf.Ticker("^TNX")
            rate = tnx.fast_info.get('last_price', None)
            if rate is None:
                hist = tnx.history(period="1d")
                rate = hist['Close'].iloc[-1] if not hist.empty else 4.2
            return rate / 100
        
        elif currency == "TRY":
            # KRİTİK AYAR: Türkiye için Politika Faizi (%50) ALINMAZ.
            # Uzun vadeli tahvil faizi veya makul getiri beklentisi alınır.
            # %22 ideal bir uzun vade beklentisidir.
            return 0.22
            
        else:
            return 0.035 # Euro

    except:
        return 0.04

# --- 2. VERİ ÇEKME MOTORU (HİBRİT) ---
def get_data_hybrid(symbol, key):
    if ".IS" in symbol:
        return get_data_yahoo(symbol)
    
    data, err = get_data_fmp(symbol, key)
    if data: return data, None
    
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
        data['ebit_margin'] = data['ebit'] / data['revenue'] if data['revenue'] else 0.15
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
            'ebit_margin': ebit/rev if rev else 0.15
        }
        return data, None
    except:
        return None, "Yahoo Hatası"

# --- 3. REALİST HESAPLAMA MOTORU (DENGELİ) ---
def calculate_balanced(data):
    # 1. FAİZ VE WACC AYARI
    rf = get_live_risk_free_rate(data['currency'])
    
    # Beta Düzeltmesi (0.8 ile 1.4 arasına sıkıştır)
    raw_beta = data.get('beta', 1.0)
    beta = max(0.8, min(raw_beta, 1.4))
    
    rm = 0.055 # %5.5 Piyasa Riski (Dengeli)
    cost_equity = rf + (beta * rm)
    
    # Borç Maliyeti
    cost_debt = rf + 0.02
    tax_rate = 0.25 if data['currency'] == 'TRY' else 0.21
    
    # WACC Hesabı
    market_cap = data['shares'] * data['current_price']
    total_val = market_cap + data['total_debt']
    if total_val <= 0: total_val = 1.0
    w_e = market_cap / total_val
    w_d = data['total_debt'] / total_val
    
    wacc = (w_e * cost_equity) + (w_d * cost_debt * (1 - tax_rate))
    
    # --- KRİTİK: TÜRKİYE ENFLASYON KORUMASI ---
    # Eğer WACC %30-40 çıkıyorsa bu model çalışmaz. 
    # TR için WACC'ı "Reel Getiri" seviyesine çekeceğiz.
    if data['currency'] == 'TRY':
        # TR için WACC tavanı %24.
        # Bu oran, şirketin enflasyon üzerinde getirmesi gereken makul yüktür.
        if wacc > 0.24: wacc = 0.24
        
        # TR için Büyüme tabanı %12 (Enflasyonel büyüme garantisi)
        # Şirket hiç iş yapmasa bile fiyatlara zam yaparak %12 büyür.
        perpetual_g = 0.12 
        
    else:
        # ABD için tavan %9.5
        if wacc > 0.095: wacc = 0.095
        # ABD için büyüme %2.5
        perpetual_g = 0.025

    # Güvenlik Kontrolü: WACC ile g arası çok darsa aç
    if wacc - perpetual_g < 0.02:
        perpetual_g = wacc - 0.02 # En az %2 fark olsun (Matematik patlamasın)

    # 2. YATIRIM ORANI (Reinvestment)
    # Boğa'da %10, Muhafazakar'da %35 idi.
    # Dengeli'de %20-25 arası.
    reinvestment_rate = 0.22 
    
    # 3. PROJEKSİYON
    years = 10
    
    # Marj: Mevcut marjı koru ama %10'un altındaysa %12'ye çek (İyileşme varsayımı)
    current_margin = data.get('ebit_margin', 0.15)
    target_margin = max(current_margin, 0.12)
    
    margins = np.linspace(current_margin, target_margin, years)
    
    # Büyüme: Başlangıç büyümesi TR için yüksek, ABD için normal
    start_g = 0.25 if data['currency'] == 'TRY' else 0.08
    growth_rates = np.linspace(start_g, perpetual_g, years)
    
    fcffs = []
    last_rev = data['revenue']
    
    for i in range(years):
        rev = last_rev * (1 + growth_rates[i])
        nopat = rev * margins[i] * (1 - tax_rate)
        
        fcff = nopat * (1 - reinvestment_rate)
        fcffs.append(fcff)
        last_rev = rev
        
    term_val = fcffs[-1] * (1+perpetual_g) / (wacc - perpetual_g)
    pv = np.sum([f / ((1+wacc)**(i+1)) for i, f in enumerate(fcffs)]) + (term_val / ((1+wacc)**years))
    
    equity = pv - data['total_debt'] + data['cash']
    price = equity / data['shares']
    if price < 0: price = 0.01
    
    return price, fcffs, {"wacc": wacc, "g": perpetual_g, "reinv": reinvestment_rate}

# --- EKRAN ---
if st.button("ANALİZ ET", type="primary"):
    with st.spinner('Piyasa verileri işleniyor...'):
        data, err = get_data_hybrid(ticker, api_key)
        
        if data:
            price, flows, metrics = calculate_balanced(data)
            
            # Kaynak
            st.success(f"✅ Veri Kaynağı: **{data['source']}**")
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Piyasa Fiyatı", f"{data['current_price']:.2f} {data['currency']}")
            c2.metric("Realist Değer", f"{price:.2f} {data['currency']}")
            
            upside = (price / data['current_price']) - 1 if data['current_price'] else 0
            color = "normal" if upside > 0 else "inverse"
            c3.metric("Potansiyel", f"%{upside*100:.1f}", delta_color=color)
            
            st.markdown("---")
            
            # Detaylar
            k1, k2, k3 = st.columns(3)
            k1.metric("Dengeli WACC", f"%{metrics['wacc']*100:.2f}", help="TR için %24, ABD için %9.5 ile sınırlandı.")
            k2.metric("Terminal Büyüme", f"%{metrics['g']*100:.2f}", help="TR için enflasyon, ABD için GSYH büyümesi.")
            k3.metric("Yatırım Oranı", f"%{metrics['reinv']*100:.0f}", help="Şirket kazancının %22'sini yatırıma ayırıyor.")
            
            st.bar_chart(flows)
            
            if data['currency'] == 'TRY':
                st.info("ℹ️ **Bilgi:** Türk hisseleri için WACC %24 ile sınırlandı ve Enflasyon büyümesi eklendi. Bu sayede 'Yüksek Faiz Yanılgısı' giderildi.")

        else:
            st.error("Veri alınamadı. Manuel giriş yapınız.")
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
