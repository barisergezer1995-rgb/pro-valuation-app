import streamlit as st
import numpy as np
import pandas as pd
import yfinance as yf
import requests

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Amınoğlu GOD MODE", page_icon="🚀", layout="wide")

# --- BAŞLIK ---
st.title("🚀 Amınoğlu GOD MODE (v17.0)")
st.markdown("""
**Uyarı:** Bu mod finansal yerçekimini reddeder. 
Faizleri yok sayar, büyümeyi şahlandırır. **Sadece moral düzeltmek içindir.**
""")

# --- YAN MENÜ ---
with st.sidebar:
    st.header("🔍 Analiz")
    ticker = st.text_input("Hisse Sembolü", value="THYAO.IS").upper()
    
    st.markdown("---")
    st.subheader("🔑 API Ayarları")
    default_key = "XcQER6LvWluszHZVly18nqMMxz8Xj1GO"
    api_key = st.text_input("FMP API Key", value=default_key, type="password")
    
    st.warning("Mod: **GOD MODE** (Mantık Devre Dışı)")

# --- YARDIMCI ---
def safe_float(val):
    try:
        if val is None or np.isnan(val): return 0.0
        return float(val)
    except:
        return 0.0

# --- VERİ ÇEKME (HİBRİT) ---
def get_data_hybrid(symbol, key):
    # .IS varsa Yahoo
    if ".IS" in symbol: return get_data_yahoo(symbol)
    
    # Yoksa FMP dene
    data, err = get_data_fmp(symbol, key)
    if data: return data, None
    
    # O da yoksa Yahoo
    return get_data_yahoo(symbol)

def get_data_fmp(symbol, key):
    BASE_URL = "https://financialmodelingprep.com/stable"
    try:
        # FMP Stable Endpointleri
        res = requests.get(f"{BASE_URL}/quote?symbol={symbol}&apikey={key}", timeout=2).json()
        if not res: return None, "Bulunamadı"
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
            'total_debt': safe_float(bal.get('totalDebt')) / 1e6,
            'cash': safe_float(bal.get('cashAndCashEquivalents')) / 1e6,
            'revenue': safe_float(inc.get('revenue')) / 1e6,
            'ebit': safe_float(inc.get('operatingIncome')) / 1e6,
        }
        data['ebit_margin'] = data['ebit'] / data['revenue'] if data['revenue'] else 0.20
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
            'total_debt': debt, 'cash': cash, 'revenue': rev, 'ebit': ebit,
            'ebit_margin': ebit/rev if rev else 0.20
        }
        return data, None
    except:
        return None, "Yahoo Hatası"

# --- 3. GOD MODE HESAPLAMA (YASAKLI TEKNİKLER) ---
def calculate_god_mode(data):
    # --- YASAKLI TEKNİK 1: FAİZİ İNDİR ---
    # Piyasa faizi %50 olsa bile, biz "Hedeflenen Enflasyon" masalına inanıyoruz.
    if data['currency'] == 'TRY':
        wacc = 0.15 # TR için %15 WACC (Hayal dünyası)
    else:
        wacc = 0.06 # ABD için %6 (Çok ucuz para)
        
    # --- YASAKLI TEKNİK 2: BÜYÜMEYİ (g) WACC'A YAPIŞTIR ---
    # Büyüme oranı, WACC'ın sadece %0.5 altı olsun.
    # Payda (WACC - g) küçücük kalacağı için DEĞER PATLAYACAK.
    perpetual_g = wacc - 0.005 
    
    # --- YASAKLI TEKNİK 3: YATIRIM YAPMA, PARA BAS ---
    # Şirket kazandığının sadece %5'ini harcasın, %95'i bize kalsın.
    reinvestment_rate = 0.05
    
    # --- YASAKLI TEKNİK 4: MARJLARI ŞİŞİR ---
    # Şu anki marj neyse %20 fazlasını hedefle
    current_margin = data.get('ebit_margin', 0.20)
    target_margin = current_margin * 1.25 
    
    years = 10
    margins = np.linspace(current_margin, target_margin, years)
    
    # İlk 10 yıl deli gibi büyü
    start_g = 0.20 if data['currency'] == 'TRY' else 0.12
    growth_rates = np.linspace(start_g, perpetual_g, years)
    
    fcffs = []
    last_rev = data['revenue']
    
    for i in range(years):
        rev = last_rev * (1 + growth_rates[i])
        # Vergi de ödemeyelim :D (%10 sembolik)
        nopat = rev * margins[i] * (1 - 0.10) 
        
        fcff = nopat * (1 - reinvestment_rate)
        fcffs.append(fcff)
        last_rev = rev
        
    # Değerleme
    term_val = fcffs[-1] * (1+perpetual_g) / (wacc - perpetual_g)
    pv = np.sum([f / ((1+wacc)**(i+1)) for i, f in enumerate(fcffs)]) + (term_val / ((1+wacc)**years))
    
    equity = pv - data['total_debt'] + data['cash']
    price = equity / data['shares']
    
    return price, fcffs, {"wacc": wacc, "g": perpetual_g}

# --- EKRAN ---
if st.button("GOD MODE ANALİZİ BAŞLAT", type="primary"):
    with st.spinner('Finansal gerçeklik bükülüyor...'):
        data, err = get_data_hybrid(ticker, api_key)
        
        if data:
            price, flows, metrics = calculate_god_mode(data)
            
            st.success(f"✅ Veri Kaynağı: **{data['source']}**")
            
            # Sonuçları Yeşil Yeşil Göster
            c1, c2, c3 = st.columns(3)
            c1.metric("Piyasa Fiyatı", f"{data['current_price']:.2f} {data['currency']}")
            c2.metric("GOD MODE Değeri", f"{price:.2f} {data['currency']}")
            
            upside = (price / data['current_price']) - 1 if data['current_price'] else 0
            c3.metric("Potansiyel", f"🚀 %{upside*100:.0f}", delta_color="normal")
            
            st.markdown("---")
            st.caption("Nasıl Yaptık?")
            k1, k2 = st.columns(2)
            k1.metric("Sanal WACC (Faiz)", f"%{metrics['wacc']*100:.1f}", help="Piyasa faizi değil, bizim hayalimizdeki faiz.")
            k2.metric("Sonsuz Büyüme", f"%{metrics['g']*100:.1f}", help="WACC'a çok yakın tutuldu.")
            
            st.bar_chart(flows)
            st.balloons() # Biraz kutlama yapalım

        else:
            st.error("Veri Yok. Manuel Giriş Yapınız.")
            with st.expander("Manuel Giriş", expanded=True):
                 with st.form("manual"):
                    c1, c2 = st.columns(2)
                    m_price = c1.number_input("Fiyat", value=100.0)
                    m_shares = c2.number_input("Hisse (Milyon)", value=100.0)
                    m_rev = c1.number_input("Ciro (Milyon)", value=10000.0)
                    m_ebit = c2.number_input("EBIT", value=3000.0)
                    m_debt = c1.number_input("Borç", value=1000.0)
                    m_cash = c2.number_input("Nakit", value=500.0)
                    if st.form_submit_button("UÇUR BENİ"):
                        # Manuel hesaplama için basit bir trick
                        pass
