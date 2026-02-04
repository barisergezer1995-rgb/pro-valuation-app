import streamlit as st
import numpy as np
import pandas as pd
import yfinance as yf
import requests

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Amınoğlu Vizyon", page_icon="📈", layout="wide")

# --- BAŞLIK ---
st.title("📈 Amınoğlu Vizyon (v21.0)")
st.markdown("""
**Premium Görselleştirme:** Bar grafikleri çöpe atıldı. 
*Trend analizi için Fiyat Geçmişi ve Projeksiyonlar için Alan Grafiği eklendi.*
""")

# --- YAN MENÜ ---
with st.sidebar:
    st.header("🔍 Hisse Seçimi")
    ticker = st.text_input("Sembol", value="THYAO.IS").upper()
    
    st.markdown("---")
    st.subheader("🔑 API")
    default_key = "XcQER6LvWluszHZVly18nqMMxz8Xj1GO"
    api_key = st.text_input("FMP Key", value=default_key, type="password")
    
    st.success("Mod: **VİZYON** (Grafik İyileştirme Aktif)")

# --- YARDIMCI ---
def safe_float(val):
    try:
        if val is None or np.isnan(val): return 0.0
        return float(val)
    except:
        return 0.0

# --- VERİ ÇEKME (HİBRİT) ---
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

# --- GRAFİK İÇİN GEÇMİŞ VERİ ---
@st.cache_data(ttl=3600)
def get_stock_history(symbol):
    try:
        stock = yf.Ticker(symbol)
        # Son 1 Yıllık Veri
        hist = stock.history(period="1y")
        if hist.empty: return None
        return hist['Close']
    except:
        return None

# --- ANALİZ RAPORU ---
def analyze_company(data):
    report = {}
    
    # Borç
    net_debt = data['total_debt'] - data['cash']
    leverage = net_debt / data['ebit'] if data['ebit'] > 0 else 99
    
    if leverage < 0:
        report['debt_score'] = "MÜKEMMEL (Nakit Zengini)"
        report['debt_color'] = "green"
    elif leverage < 2:
        report['debt_score'] = "İYİ (Yönetilebilir)"
        report['debt_color'] = "green"
    elif leverage < 4:
        report['debt_score'] = "ORTA (Dikkat)"
        report['debt_color'] = "orange"
    else:
        report['debt_score'] = "RİSKLİ (Yüksek Borç)"
        report['debt_color'] = "red"

    # Marj
    margin = data['ebit_margin']
    if margin > 0.25: report['margin_score'] = "YÜKSEK (Lider)"
    elif margin > 0.10: report['margin_score'] = "STANDART"
    else: report['margin_score'] = "DÜŞÜK (Rekabetçi)"

    return report

# --- HESAPLAMA ---
def calculate_analyst_mode(data):
    if data['currency'] == 'TRY':
        wacc = 0.19 
        perpetual_g = 0.14
    else:
        wacc = 0.075 
        perpetual_g = 0.04
        
    reinvestment_rate = 0.15 
    years = 10
    
    current_margin = data.get('ebit_margin', 0.15)
    target_margin = max(current_margin, 0.22) 
    margins = np.linspace(current_margin, target_margin, years)
    growth_rates = np.linspace(0.18 if data['currency']=='TRY' else 0.12, perpetual_g, years)
    
    fcffs = []
    last_rev = data['revenue']
    
    for i in range(years):
        rev = last_rev * (1 + growth_rates[i])
        nopat = rev * margins[i] * 0.80 
        fcff = nopat * (1 - reinvestment_rate)
        fcffs.append(fcff)
        last_rev = rev
        
    term_val = fcffs[-1] * (1+perpetual_g) / (wacc - perpetual_g)
    pv = np.sum([f / ((1+wacc)**(i+1)) for i, f in enumerate(fcffs)]) + (term_val / ((1+wacc)**years))
    
    equity = pv - data['total_debt'] + data['cash']
    raw_dcf_price = equity / data['shares']
    if raw_dcf_price < 0: raw_dcf_price = 0.01

    raw_upside = (raw_dcf_price / data['current_price']) - 1
    
    if raw_upside >= 0:
        final_upside = raw_upside
    else:
        final_upside = -np.log1p(abs(raw_upside)) 
    
    final_price = data['current_price'] * (1 + final_upside)
    
    return final_price, final_upside, fcffs

# --- EKRAN TASARIMI ---
if st.button("ANALİZİ BAŞLAT", type="primary"):
    with st.spinner('Veriler ve Grafikler Hazırlanıyor...'):
        data, err = get_data_hybrid(ticker, api_key)
        history = get_stock_history(ticker)
        
        if data:
            target_price, upside, flows = calculate_analyst_mode(data)
            report = analyze_company(data)
            
            # --- 1. BLOK: FİYAT VE KARAR ---
            st.success(f"Analiz Edilen: **{data['ticker']}**")
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Piyasa Fiyatı", f"{data['current_price']:.2f} {data['currency']}")
            c2.metric("Adil Değer", f"{target_price:.2f} {data['currency']}")
            
            color = "normal" if upside > 0 else "inverse"
            c3.metric("Potansiyel", f"%{upside*100:.1f}", delta_color=color)
            
            # --- 2. BLOK: HİSSE PERFORMANS GRAFİĞİ (ÇİZGİ) ---
            st.markdown("### 📈 Son 1 Yıl Fiyat Hareketi")
            if history is not None:
                st.line_chart(history, use_container_width=True)
            else:
                st.warning("Grafik verisi çekilemedi.")
                
            st.markdown("---")

            # --- 3. BLOK: DETAYLI RAPOR ---
            col_L, col_R = st.columns(2)
            
            with col_L:
                st.markdown("#### 📝 Finansal Karne")
                st.write(f"**Borç Durumu:** {report['debt_score']}")
                if report['debt_color'] == 'green': st.progress(90)
                elif report['debt_color'] == 'orange': st.progress(50)
                else: st.progress(20)
                
                st.write(f"**Kârlılık:** {report['margin_score']}")
            
            with col_R:
                st.markdown("#### 🔮 Gelecek Beklentisi")
                if flows[-1] > flows[0]:
                    st.success("Pozitif Nakit Akışı Büyümesi Bekleniyor")
                else:
                    st.warning("Nakit Akışında Daralma Riski")
                
                st.write(f"**Hedef Marj:** %{data['ebit_margin']*1.2*100:.1f}")

            # --- 4. BLOK: PROJEKSİYON GRAFİĞİ (ALAN/DAĞ) ---
            st.markdown("### 🏔️ Gelecek Nakit Akışı Projeksiyonu")
            st.caption("Şirketin önümüzdeki 10 yılda üretmesi beklenen nakit (Milyon)")
            
            # Area Chart için DataFrame
            df_flows = pd.DataFrame(flows, columns=["Tahmini Nakit"])
            st.area_chart(df_flows, color="#00ff00" if upside > 0 else "#ff0000")

        else:
            st.error("Veri Yok. Manuel Giriş:")
            # ... Manuel giriş kısmı ...
