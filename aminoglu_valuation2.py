import streamlit as st
import numpy as np
import pandas as pd
import yfinance as yf
import requests
import datetime

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Amınoğlu Ultimate", page_icon="🛡️", layout="wide")

# --- BAŞLIK ---
st.title("🛡️ Amınoğlu Ultimate Değerleme (v8.0)")
st.markdown("Hibrit Motor: FMP (Profesyonel) + Yahoo (Yedek) + Manuel (Son Çare)")

# --- YAN MENÜ ---
with st.sidebar:
    st.header("🔍 Analiz")
    ticker = st.text_input("Hisse Sembolü", value="LMT").upper()
    st.caption("Örn: AAPL, TSLA (FMP çeker) | THYAO.IS, ASELS.IS (Yahoo çeker)")

# --- AYARLAR ---
API_KEY_FMP = "XcQER6LvWluszHZVly18nqMMxz8Xj1GO" # Senin Key'in

# --- YARDIMCI ---
def safe_float(val):
    try:
        if val is None or np.isnan(val): return 0.0
        return float(val)
    except:
        return 0.0

# --- 1. KAYNAK: FMP API (ÖNCELİKLİ) ---
def get_data_fmp(symbol):
    try:
        # Profil ve Fiyat
        quote_url = f"https://financialmodelingprep.com/api/v3/quote/{symbol}?apikey={API_KEY_FMP}"
        profile_url = f"https://financialmodelingprep.com/api/v3/profile/{symbol}?apikey={API_KEY_FMP}"
        
        quote_res = requests.get(quote_url, timeout=3).json() # 3sn bekle
        if not quote_res or 'Error Message' in quote_res: return None # Bulamazsa çık
        
        quote = quote_res[0]
        prof_res = requests.get(profile_url, timeout=3).json()
        profile = prof_res[0] if prof_res else {}

        # Finansallar
        inc_url = f"https://financialmodelingprep.com/api/v3/income-statement/{symbol}?limit=1&apikey={API_KEY_FMP}"
        bal_url = f"https://financialmodelingprep.com/api/v3/balance-sheet-statement/{symbol}?limit=1&apikey={API_KEY_FMP}"
        
        inc_res = requests.get(inc_url, timeout=3).json()
        bal_res = requests.get(bal_url, timeout=3).json()
        
        if not inc_res or not bal_res: return None
        
        inc = inc_res[0]
        bal = bal_res[0]

        # Veri Paketleme
        data = {}
        data['source'] = "FMP (Resmi API)"
        data['ticker'] = symbol
        data['currency'] = profile.get('currency', 'USD')
        data['current_price'] = safe_float(quote.get('price'))
        
        mkt_cap = safe_float(quote.get('marketCap'))
        data['shares'] = (mkt_cap / data['current_price']) / 1e6 if data['current_price'] else 0
        if data['shares'] <= 0: data['shares'] = 1.0

        data['beta'] = safe_float(profile.get('beta', 1.0))
        data['revenue_growth'] = 0.08 # FMP tek sorguda growth vermiyor, varsayılan
        
        ipo_date = profile.get('ipoDate')
        if ipo_date:
            data['age'] = datetime.datetime.now().year - int(ipo_date.split('-')[0])
        else:
            data['age'] = 15

        data['total_debt'] = safe_float(bal.get('totalDebt')) / 1e6
        data['cash'] = safe_float(bal.get('cashAndCashEquivalents')) / 1e6
        data['revenue'] = safe_float(inc.get('revenue')) / 1e6
        data['ebit'] = safe_float(inc.get('operatingIncome')) / 1e6
        
        if data['revenue'] > 0:
            data['ebit_margin'] = data['ebit'] / data['revenue']
        else:
            data['ebit_margin'] = 0.15
            
        return data

    except:
        return None # Hata olursa sessizce None dön, Yahoo denensin

# --- 2. KAYNAK: YAHOO FINANCE (YEDEK) ---
def get_data_yahoo(symbol):
    try:
        stock = yf.Ticker(symbol)
        
        # Hızlı veri
        current_price = stock.fast_info.get('last_price', None)
        shares = stock.fast_info.get('shares', None)
        
        if current_price is None or np.isnan(safe_float(current_price)):
            # History dene
            hist = stock.history(period="1d")
            if not hist.empty:
                current_price = hist['Close'].iloc[-1]
            else:
                return None # Fiyat yoksa çık

        bs = stock.balance_sheet
        is_stmt = stock.financials
        
        if bs.empty or is_stmt.empty:
            return None # Tablo yoksa çık

        data = {}
        data['source'] = "Yahoo (Yedek)"
        data['ticker'] = symbol
        data['currency'] = stock.fast_info.get('currency', 'USD')
        data['current_price'] = safe_float(current_price)
        data['shares'] = safe_float(shares) / 1e6 
        if data['shares'] <= 0: data['shares'] = 1.0

        try:
            data['beta'] = stock.info.get('beta', 1.0)
            data['revenue_growth'] = stock.info.get('revenueGrowth', 0.05)
        except:
            data['beta'] = 1.0
            data['revenue_growth'] = 0.05
            
        first_trade = stock.info.get('firstTradeDateEpochUtc', None) if 'info' in dir(stock) else None
        if first_trade:
            data['age'] = datetime.datetime.now().year - datetime.datetime.fromtimestamp(first_trade).year
        else:
            data['age'] = 15

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
            
        return data

    except:
        return None

# --- ANA KONTROL MERKEZİ ---
@st.cache_data(ttl=3600)
def get_data_hybrid(symbol):
    # 1. Önce Kralı Dene (FMP)
    data = get_data_fmp(symbol)
    if data:
        return data, None
    
    # 2. Olmadı mı? Yedek Subayı Dene (Yahoo)
    data = get_data_yahoo(symbol)
    if data:
        return data, None
        
    # 3. Hiçbiri Olmadı
    return None, "Tüm kaynaklar tükendi."

# --- OTOPİLOT HESAPLAMA ---
def autopilot_dcf(data):
    age = data.get('age', 15)
    beta = data.get('beta', 1.0)
    
    # Karar Mekanizması
    if (age > 15) and (beta < 0.9): 
        profile = "🐄 NAKİT İNEĞİ (Cash Cow)"
        forecast_years = 7
        perpetual_g = 0.025
        reinvestment_rate = 0.05
        target_wacc_cap = 0.075
        used_beta = min(beta, 0.75) 

    elif (beta > 1.3) or (age < 10): 
        profile = "🚀 ROKET (High Growth)"
        forecast_years = 15
        perpetual_g = 0.035
        reinvestment_rate = 0.50
        target_wacc_cap = 0.12
        used_beta = max(beta, 1.2)

    else: 
        profile = "🏭 STANDART SANAYİ"
        forecast_years = 10
        perpetual_g = 0.030
        reinvestment_rate = 0.25
        target_wacc_cap = 0.10
        used_beta = beta

    rf = 0.04
    rm = 0.05
    cost_equity = rf + used_beta * rm
    
    market_cap = data['shares'] * data['current_price']
    total_val = market_cap + data['total_debt']
    if total_val <= 0: total_val = market_cap if market_cap > 0 else 1.0
    
    w_e = market_cap / total_val
    w_d = data['total_debt'] / total_val
    
    wacc = (w_e * cost_equity) + (w_d * 0.055 * (1 - 0.21))
    wacc = max(0.06, min(wacc, target_wacc_cap))
    
    if perpetual_g >= wacc: perpetual_g = wacc - 0.005

    current_margin = data['ebit_margin']
    target_margin = current_margin
    
    if profile == "🚀 ROKET (High Growth)" and current_margin < 0.20: target_margin = 0.25
    elif profile == "🐄 NAKİT İNEĞİ (Cash Cow)" and current_margin < 0.12: target_margin = 0.12

    margins = np.linspace(current_margin, target_margin, forecast_years)
    growth_rates = np.linspace(0.08, perpetual_g, forecast_years)
    
    fcffs = []
    last_rev = data['revenue']
    
    for i in range(forecast_years):
        rev = last_rev * (1 + growth_rates[i])
        ebit = rev * margins[i]
        nopat = ebit * (1 - 0.21)
        reinvestment = nopat * reinvestment_rate
        fcff = nopat - reinvestment
        fcffs.append(fcff)
        last_rev = rev

    discount_factors = [1 / ((1 + wacc) ** (y + 1)) for y in range(forecast_years)]
    pv_fcff = np.sum(np.array(fcffs) * np.array(discount_factors))
    
    terminal_val = (fcffs[-1] * (1 + perpetual_g)) / (wacc - perpetual_g)
    if terminal_val < 0: terminal_val = 0
    pv_terminal = terminal_val / ((1 + wacc) ** forecast_years)
    
    enterprise_val = pv_fcff + pv_terminal
    equity_val = enterprise_val - data['total_debt'] + data['cash']
    dcf_price = equity_val / data['shares']
    if dcf_price < 0: dcf_price = 0
    
    return dcf_price, fcffs, { "profile": profile, "wacc": wacc, "g": perpetual_g, "reinv": reinvestment_rate }

# --- EKRAN ---
if st.button("ANALİZ ET", type="primary"):
    with st.spinner('Hibrit Motor çalışıyor (FMP -> Yahoo)...'):
        fetched_data, error = get_data_hybrid(ticker)
        
        # MANUEL GİRİŞ (EĞER FMP VE YAHOO İKİSİ DE ÇÖKERSE)
        if error:
            st.warning("⚠️ Tüm veri kaynakları (FMP & Yahoo) yanıt vermedi. Manuel Giriş:")
            with st.form("manual"):
                c1, c2 = st.columns(2)
                m_price = c1.number_input("Fiyat ($)", value=100.0)
                m_shares = c2.number_input("Hisse (Milyon)", value=250.0)
                m_rev = c1.number_input("Ciro (Milyon $)", value=50000.0)
                m_ebit = c2.number_input("EBIT", value=8000.0)
                m_debt = c1.number_input("Borç", value=5000.0)
                m_cash = c2.number_input("Nakit", value=2000.0)
                
                st.caption("Otopilot için tahminler:")
                m_beta = c1.slider("Beta", 0.5, 2.0, 0.8)
                m_age = c2.slider("Yaş", 1, 100, 20)
                
                if st.form_submit_button("HESAPLA"):
                    fetched_data = {
                        'ticker': ticker, 'currency': 'USD', 'source': 'Manuel',
                        'current_price': m_price, 'shares': m_shares, 
                        'total_debt': m_debt, 'cash': m_cash, 'revenue': m_rev,
                        'ebit': m_ebit, 'ebit_margin': m_ebit/m_rev if m_rev else 0,
                        'beta': m_beta, 'age': m_age
                    }
                    error = None

        if fetched_data and not error:
            data = fetched_data
            price, flows, decisions = autopilot_dcf(data)
            
            # ÜST BİLGİ: Kaynak Gösterimi
            source = data.get('source', 'Bilinmiyor')
            if "FMP" in source:
                st.success(f"✅ Veri Kaynağı: **{source}** (En Güvenilir)")
            elif "Yahoo" in source:
                st.warning(f"⚠️ Veri Kaynağı: **{source}** (Yedek Sistem Devrede)")
            else:
                st.info(f"ℹ️ Veri Kaynağı: **{source}**")

            st.info(f"🧬 **Şirket Profili:** {decisions['profile']}")
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Piyasa Fiyatı", f"{data['current_price']:.2f} {data['currency']}")
            c2.metric("Otopilot Değeri", f"{price:.2f} {data['currency']}")
            
            upside = (price / data['current_price']) - 1 if data['current_price'] else 0
            c3.metric("Potansiyel", f"%{upside*100:.1f}", delta_color="normal" if upside > 0 else "inverse")
            
            with st.expander("Detaylar"):
                st.write(f"- WACC: %{decisions['wacc']*100:.2f}")
                st.write(f"- Büyüme (g): %{decisions['g']*100:.2f}")
                st.write(f"- Yatırım Oranı: %{decisions['reinv']*100:.0f}")
            
            st.bar_chart(flows)
