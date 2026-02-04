import streamlit as st
import numpy as np
import pandas as pd
import yfinance as yf

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Amınoğlu Hibrit", page_icon="🧠", layout="wide")

# --- BAŞLIK ---
st.title("🧠 Amınoğlu Hibrit Motor (Adaptive AI)")
st.markdown("Şirketin karakterini (Startup vs Holding) otomatik algılayan akıllı sistem.")

# --- YAN MENÜ ---
with st.sidebar:
    st.header("⚙️ Parametreler")
    ticker = st.text_input("Sembol", value="LMT").upper()
    
    st.subheader("Ayarlar")
    forecast_years = st.slider("Tahmin Yılı", 5, 15, 10)
    perpetual_growth = st.slider("Sonsuz Büyüme (g)", 1.5, 5.0, 2.5, 0.1) / 100
    
    wacc_manual = st.checkbox("WACC Manuel")
    if wacc_manual:
        wacc_input = st.slider("WACC (%)", 4.0, 20.0, 8.0, 0.5) / 100
    else:
        wacc_input = None

# --- YARDIMCI ---
def safe_float(val):
    try:
        if val is None or np.isnan(val): return 0.0
        return float(val)
    except:
        return 0.0

# --- VERİ ÇEKME ---
@st.cache_data(ttl=3600)
def get_data(symbol):
    stock = yf.Ticker(symbol)
    data = {}
    
    try:
        # Hızlı veri
        current_price = stock.fast_info.get('last_price', None)
        shares = stock.fast_info.get('shares', None)
        
        if current_price is None:
            hist = stock.history(period="1d")
            if not hist.empty:
                current_price = hist['Close'].iloc[-1]
            else:
                return None, "Fiyat yok."

        bs = stock.balance_sheet
        is_stmt = stock.financials
        
        if bs.empty or is_stmt.empty:
            return None, "Tablolar boş."

        # Temel Veriler
        data['ticker'] = symbol
        data['currency'] = stock.fast_info.get('currency', 'USD')
        data['current_price'] = safe_float(current_price)
        data['shares'] = safe_float(shares) / 1e6 
        if data['shares'] <= 0: data['shares'] = 1.0

        # KARAKTER ANALİZİ İÇİN GEREKLİ VERİLER
        # 1. Beta (Risk)
        data['beta'] = stock.info.get('beta', 1.0)
        
        # 2. Büyüme Hızı (Revenue Growth)
        # Yahoo'da bazen 'revenueGrowth' info içinde gelir
        data['revenue_growth'] = stock.info.get('revenueGrowth', 0.05) 
        
        # 3. Şirket Yaşı (Tahmini) - firstTradeDate yoksa history uzunluğuna bak
        first_trade = stock.info.get('firstTradeDateEpochUtc', None)
        if first_trade:
            # Timestamp'i yıla çevir
            import datetime
            ipo_year = datetime.datetime.fromtimestamp(first_trade).year
            data['age'] = datetime.datetime.now().year - ipo_year
        else:
            data['age'] = 15 # Bilinmiyorsa orta yaşlı varsay

        data['total_debt'] = safe_float(bs.iloc[:, 0].get('Total Debt')) / 1e6
        data['cash'] = safe_float(bs.iloc[:, 0].get('Cash And Cash Equivalents')) / 1e6
        data['revenue'] = safe_float(is_stmt.iloc[:, 0].get('Total Revenue')) / 1e6
        
        ebit = safe_float(is_stmt.iloc[:, 0].get('EBIT'))
        if ebit == 0: ebit = safe_float(is_stmt.iloc[:, 0].get('Operating Income'))
        data['ebit'] = ebit / 1e6
        
        if data['revenue'] > 0:
            data['ebit_margin'] = data['ebit'] / data['revenue']
        else:
            data['ebit_margin'] = 0.15
            
        return data, None

    except Exception as e:
        return None, str(e)

# --- AKILLI HESAPLAMA MOTORU ---
def calculate_dcf(data, years, g, manual_wacc):
    # --- ADIM 1: ŞİRKET TİPİNİ BELİRLE (PROFILING) ---
    # Bu kısım kodun beynidir.
    
    profile = "Standart"
    reinvestment_rate = 0.30 # Varsayılan %30
    
    age = data.get('age', 15)
    growth = data.get('revenue_growth', 0.05)
    beta = data.get('beta', 1.0)
    
    # MANTIK AĞACI
    if (growth > 0.15) or (age < 10):
        # Hızlı Büyüyen / Startup
        profile = "🚀 ROKET (Startup/Growth)"
        reinvestment_rate = 0.60 # Büyümek için çok harcamalı (%60)
        # Ama Startuplar daha hızlı büyür, g'yi artırabiliriz
        used_growth_start = max(growth, 0.15) 
        
    elif (beta < 0.85) and (age > 15):
        # Güvenli Liman / Temettücü (LMT, KO, JNJ)
        profile = "🐄 NAKİT İNEĞİ (Cash Cow)"
        reinvestment_rate = 0.10 # Az harcar, çok dağıtır (%10)
        used_growth_start = 0.04 # Yavaş büyür
        
    else:
        # Ortalama Sanayi (THY, Ford)
        profile = "🏭 STANDART SANAYİ"
        reinvestment_rate = 0.25 # Dengeli (%25)
        used_growth_start = 0.08
        
    # --- ADIM 2: WACC ---
    rf = 0.04
    rm = 0.05
    
    # Beta Düzeltmesi (LMT için beta düşük kalmalı)
    adjusted_beta = beta
    if profile == "🐄 NAKİT İNEĞİ (Cash Cow)":
        adjusted_beta = min(beta, 0.8) # Risk algısını düşür
    
    cost_equity = rf + adjusted_beta * rm
    
    market_cap = data['shares'] * data['current_price']
    total_val = market_cap + data['total_debt']
    if total_val <= 0: total_val = market_cap if market_cap > 0 else 1.0
    
    w_e = market_cap / total_val
    w_d = data['total_debt'] / total_val
    
    wacc = (w_e * cost_equity) + (w_d * 0.055 * (1 - 0.21))
    
    if manual_wacc: wacc = manual_wacc
    
    # Güvenlik kilidi (g vs wacc)
    if g >= wacc: g = wacc - 0.005

    # --- ADIM 3: PROJEKSİYON ---
    current_margin = data['ebit_margin']
    target_margin = current_margin
    
    # Startup ise marjlar zamanla iyileşir
    if profile == "🚀 ROKET (Startup/Growth)" and current_margin < 0.15:
        target_margin = 0.20 # Gelecekte %20 marja ulaşır
        
    margins = np.linspace(current_margin, target_margin, years)
    growth_rates = np.linspace(used_growth_start, g, years)
    
    fcffs = []
    last_rev = data['revenue']
    
    for i in range(years):
        rev = last_rev * (1 + growth_rates[i])
        ebit = rev * margins[i]
        nopat = ebit * (1 - 0.21)
        
        # Dinamik Yatırım Oranı Kullanımı
        reinvestment = nopat * reinvestment_rate
        
        fcff = nopat - reinvestment
        fcffs.append(fcff)
        last_rev = rev

    # --- ADIM 4: DEĞERLEME ---
    discount_factors = [1 / ((1 + wacc) ** (y + 1)) for y in range(years)]
    pv_fcff = np.sum(np.array(fcffs) * np.array(discount_factors))
    
    terminal_val = (fcffs[-1] * (1 + g)) / (wacc - g)
    if terminal_val < 0: terminal_val = 0
        
    pv_terminal = terminal_val / ((1 + wacc) ** years)
    
    enterprise_val = pv_fcff + pv_terminal
    equity_val = enterprise_val - data['total_debt'] + data['cash']
    
    dcf_price = equity_val / data['shares']
    if dcf_price < 0: dcf_price = 0
    
    return dcf_price, wacc, fcffs, profile, reinvestment_rate

# --- EKRAN ---
if st.button("ANALİZİ BAŞLAT", type="primary"):
    fetched_data, error = get_data(ticker)
    
    if error:
        st.error(error)
    elif fetched_data:
        data = fetched_data
        
        price, wacc, flows, profile_name, reinv_rate = calculate_dcf(
            data, forecast_years, perpetual_growth, wacc_input
        )
        
        # ÜST BİLGİ KARTI
        st.info(f"🧬 **Şirket Profili:** {profile_name} | **Strateji:** Kazancın %{reinv_rate*100:.0f}'u yatırıma gidiyor.")
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Piyasa Fiyatı", f"{data['current_price']:.2f} $")
        c2.metric("Adil Değer", f"{price:.2f} $")
        
        upside = (price / data['current_price']) - 1
        c3.metric("Potansiyel", f"%{upside*100:.1f}", delta_color="normal" if upside > 0 else "inverse")
        
        st.bar_chart(flows)
