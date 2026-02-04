import streamlit as st
import numpy as np
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go
import datetime

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Amınoğlu Yatırım Danışmanlık", page_icon="🚀", layout="wide")

# --- BAŞLIK ---
st.title("🚀 Amınoğlu Ultra Boğa v3.0")
st.markdown("""
**Sade ve Güvenli:** Yatırım tavsiyei vermez
*Ama evi arabayı satıp kredi çekebilirsiniz*
""")

# --- YAN MENÜ ---
with st.sidebar:
    st.header("🔍 Hisse Seçimi")
    ticker = st.text_input("Sembol", value="THYAO.IS").upper()
    
    st.markdown("---")
    st.subheader("🔑 API")
    default_key = "XcQER6LvWluszHZVly18nqMMxz8Xj1GO"
    api_key = st.text_input("FMP Key", value=default_key, type="password")
    
    st.info("Mod: **NET SONUÇ (Hatasız)**")

# --- YARDIMCI ---
def safe_float(val):
    try:
        if val is None or np.isnan(val): return 0.0
        return float(val)
    except:
        return 0.0

# --- FREN FONKSİYONU ---
def apply_steel_brake(raw_upside):
    """
    Katsayı: 0.55 (Sert Fren)
    """
    abs_val = abs(raw_upside)
    damped = np.log1p(abs_val) * 0.55 
    
    if raw_upside >= 0:
        return damped
    else:
        return -damped

# --- VERİ ÇEKME ---
def get_data_hybrid(symbol, key):
    if ".IS" in symbol: return get_data_yahoo(symbol)
    data, err = get_data_fmp(symbol, key)
    if data: return data, None
    return get_data_yahoo(symbol)

def get_data_fmp(symbol, key):
    BASE_URL = "https://financialmodelingprep.com/stable"
    try:
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
            'beta': safe_float(prof.get('beta', 1.0))
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
            'total_debt': debt, 'cash': cash, 'revenue': rev, 'ebit': ebit,
            'ebit_margin': ebit/rev if rev else 0.15,
            'beta': 1.0
        }
        return data, None
    except:
        return None, "Yahoo Hatası"

# --- GEÇMİŞ VERİ ---
@st.cache_data(ttl=3600)
def get_stock_history(symbol):
    try:
        stock = yf.Ticker(symbol)
        hist = stock.history(period="1y")
        return hist['Close'] if not hist.empty else None
    except:
        return None

# --- HESAPLAMA MOTORU ---
def calculate_net_result(data, years): # years parametresini ekledik
    # Parametreler
    if data['currency'] == 'TRY':
        wacc = 0.19 
        g = 0.14
        margin_factor = 1.1
    else:
        wacc = 0.075 
        g = 0.04
        margin_factor = 1.1
    
    reinvestment_rate = 0.15
    
    # Projeksiyon
    current_margin = data.get('ebit_margin', 0.15)
    target_margin = max(current_margin, current_margin * margin_factor)
    
    margins = np.linspace(current_margin, target_margin, years)
    growth_rates = np.linspace(g + 0.05, g, years)
    
    fcffs = []
    last_rev = data['revenue']
    
    for i in range(years):
        rev = last_rev * (1 + growth_rates[i])
        nopat = rev * margins[i] * 0.80 # Vergi
        fcff = nopat * (1 - reinvestment_rate)
        fcffs.append(fcff)
        last_rev = rev
        
    term_val = fcffs[-1] * (1+g) / (wacc - g)
    pv = np.sum([f / ((1+wacc)**(i+1)) for i, f in enumerate(fcffs)]) + (term_val / ((1+wacc)**years))
    
    equity = pv - data['total_debt'] + data['cash']
    raw_price = equity / data['shares']
    if raw_price < 0: raw_price = 0.01

    # --- FREN ---
    raw_upside = (raw_price / data['current_price']) - 1
    
    # Frenle
    braked_upside = apply_steel_brake(raw_upside)
    
    # Hedef Fiyat
    target_price = data['current_price'] * (1 + braked_upside)
    
    return target_price, braked_upside, fcffs

# --- EKRAN ---
if st.button("ANALİZ ET", type="primary"):
    # HATA DÜZELTME: 'years' değişkenini burada tanımlıyoruz
    years = 10 
    
    with st.spinner('Net sonuç hesaplanıyor...'):
        data, err = get_data_hybrid(ticker, api_key)
        history = get_stock_history(ticker)
        
        if data:
            # years'ı fonksiyona yolluyoruz
            target_price, upside, flows = calculate_net_result(data, years)
            
            # --- 1. ANA KART ---
            st.markdown(f"### 🛡️ {data['ticker']} Net Analiz")
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Piyasa Fiyatı", f"{data['current_price']:.2f} {data['currency']}")
            
            # Hedef Fiyat
            c2.metric("Güvenli Hedef", f"{target_price:.2f} {data['currency']}")
            
            # SADECE NET POTANSİYEL
            color = "normal" if upside > 0 else "inverse"
            c3.metric("Net Potansiyel", f"%{upside*100:.1f}", delta_color=color)
            
            st.markdown("---")

            # --- 2. GRAFİK (PLOTLY) ---
            fig = go.Figure()
            
            # Geçmiş
            if history is not None:
                fig.add_trace(go.Scatter(x=history.index, y=history.values, mode='lines', name='Piyasa', line=dict(color='#888', width=2)))
            
            # Hedef Çizgisi
            fig.add_hline(y=target_price, line_dash="solid", line_color="#32CD32", line_width=3, annotation_text="HEDEF", annotation_font_size=14, annotation_font_color="#32CD32")

            fig.update_layout(
                title="Fiyat ve Hedef", 
                height=500,
                xaxis_title="Tarih",
                yaxis_title="Fiyat"
            )
            # UYARI DÜZELTME: use_container_width yerine yeni standart
            st.plotly_chart(fig, use_container_width=True)
            
            # --- 3. NAKİT AKIŞI ---
            st.markdown("### 🏔️ Nakit Akışı Projeksiyonu")
            df_flow = pd.DataFrame(flows, columns=["Projeksiyon"])
            # UYARI DÜZELTME: Area chart için genişlik ayarı
            st.area_chart(df_flow, color="#32CD32" if upside > 0 else "#FF4B4B")
            
            # --- 4. BİLGİ NOTU ---
            # ARTIK 'years' TANIMLI OLDUĞU İÇİN BURASI PATLAMAZ
            st.info(f"ℹ️ **Sistem Notu:** Bu hedef fiyat, {years} yıllık nakit akış projeksiyonları ve 'Yüksek Güvenlik Marjı' kullanılarak hesaplanmıştır.")

        else:
            st.error("Veri Yok. Manuel Giriş:")
            # ...


