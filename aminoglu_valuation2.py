import streamlit as st
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Amınoğlu Değerleme", page_icon="⚖️", layout="wide")

# --- BAŞLIK ---
st.title("⚖️ Amınoğlu Değerleme (Wall Street Modu)")
st.markdown("Dengeli, Gerçekçi ve Profesyonel Analiz")

# --- YAN MENÜ ---
with st.sidebar:
    st.header("⚙️ Parametreler")
    ticker = st.text_input("Hisse Sembolü (Örn: LMT, ASELS.IS)", value="LMT").upper()
    
    st.subheader("İnce Ayarlar")
    forecast_years = st.slider("Tahmin Yılı", 5, 10, 10) # 10 Yıl standarttır
    perpetual_growth = st.slider("Sonsuz Büyüme (g)", 1.5, 4.0, 2.5, 0.1) / 100
    
    wacc_manual = st.checkbox("WACC'ı Manuel Gir")
    if wacc_manual:
        wacc_input = st.slider("WACC Oranı (%)", 4.0, 15.0, 8.0, 0.5) / 100
    else:
        wacc_input = None
    
    st.markdown("---")
    st.subheader("🦄 Değerleme Modu")
    
    force_startup = st.checkbox("Startup Modunu Zorla")
    if force_startup:
        sector_multiple = st.slider("Sektör Çarpanı (P/S)", 1.0, 50.0, 5.0, 0.5)
    else:
        sector_multiple = 5.0

# --- GÜVENLİ VERİ OKUMA ---
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
        # Hızlı veri çekme
        current_price = stock.fast_info.get('last_price', None)
        shares = stock.fast_info.get('shares', None)
        
        if current_price is None or np.isnan(safe_float(current_price)):
            hist = stock.history(period="1d")
            if not hist.empty:
                current_price = hist['Close'].iloc[-1]
            else:
                return None, "Fiyat verisi çekilemedi."

        bs = stock.balance_sheet
        is_stmt = stock.financials
        
        if bs.empty or is_stmt.empty:
            return None, "Finansal tablolar boş (Yahoo Engeli)."

        data['ticker'] = symbol
        data['long_name'] = symbol
        data['currency'] = stock.fast_info.get('currency', 'USD')
        data['current_price'] = safe_float(current_price)
        data['shares'] = safe_float(shares) / 1e6 
        if data['shares'] <= 0: data['shares'] = 1.0

        # Beta Önemli: LMT gibi hisselerde Beta düşüktür, bunu doğru almalıyız.
        try:
            data['beta'] = stock.info.get('beta', 1.0)
        except:
            data['beta'] = 1.0

        data['total_debt'] = safe_float(bs.iloc[:, 0].get('Total Debt')) / 1e6
        data['cash'] = safe_float(bs.iloc[:, 0].get('Cash And Cash Equivalents')) / 1e6
        data['revenue'] = safe_float(is_stmt.iloc[:, 0].get('Total Revenue')) / 1e6
        data['ebit'] = safe_float(is_stmt.iloc[:, 0].get('EBIT')) / 1e6
        
        if data['ebit'] == 0:
            data['ebit'] = safe_float(is_stmt.iloc[:, 0].get('Operating Income')) / 1e6

        data['growth_start'] = 0.08 # %8 ile başlat (Makul)
        data['company_age'] = 10    
        
        if data['revenue'] > 0:
            data['ebit_margin'] = data['ebit'] / data['revenue']
        else:
            data['ebit_margin'] = 0.15
        
        # Vergi
        pretax = safe_float(is_stmt.iloc[:, 0].get('Pretax Income'))
        tax = safe_float(is_stmt.iloc[:, 0].get('Tax Provision'))
        if pretax > 0:
            data['tax_rate'] = tax / pretax
        else:
            data['tax_rate'] = 0.21
            
        return data, None

    except Exception as e:
        return None, f"Veri Hatası: {str(e)}"

# --- HESAPLAMA MOTORU (DENGELİ MOD) ---
def calculate_dcf(data, years, g, manual_wacc=None, multiple=None):
    # 1. WACC HESABI (Dengeli)
    rf = 0.040 # %4.0 Risksiz Faiz
    rm = 0.050 # %5.0 Piyasa Primi
    
    # Beta Düzeltme: LMT'nin betası 0.5-0.7 gibidir. Bunu olduğu gibi kabul etmeliyiz.
    # Önceki kod bunu 1.0'a zorluyordu, o yüzden LMT değersiz çıkıyordu.
    raw_beta = safe_float(data.get('beta', 1.0))
    # Beta'yı 0.6 ile 1.6 arasına alalım (Çok aşırı uçları törpüle)
    beta = max(0.6, min(raw_beta, 1.6))
    
    cost_equity = rf + beta * rm
    
    market_cap = data['shares'] * data['current_price']
    total_val = market_cap + data['total_debt']
    if total_val <= 0: total_val = market_cap if market_cap > 0 else 1.0
    
    w_e = market_cap / total_val
    w_d = data['total_debt'] / total_val
    
    cost_debt = 0.055 
    effective_tax = 0.21 
    
    wacc = (w_e * cost_equity) + (w_d * cost_debt * (1 - effective_tax))
    
    if manual_wacc:
        wacc = manual_wacc
    else:
        # Otomatik WACC Ayarı:
        # WACC'ın %6'nın altına inmesine izin verme (En güvenli şirket bile risksiz değildir)
        # Ama LMT gibi şirketler için %7-8 gayet normaldir.
        wacc = max(0.06, wacc)

    # 2. BÜYÜME AYARI (Altın Oran)
    # WACC ile g arasında %1.0 fark bırak.
    # Bu, ne çok iyimser (0.2%) ne çok kötümser (1.5%) olur.
    adjusted_g = g
    if adjusted_g >= wacc - 0.01:
        adjusted_g = wacc - 0.01

    # 3. PROJEKSİYON
    # Marjları sabitleme veya uçurma.
    # Eğer mevcut marj pozitifse, onu koru.
    current_margin = data['ebit_margin']
    target_margin = current_margin # Mevcut durumu koru (LMT için en doğrusu)
    
    # Eğer şirket zarar ediyorsa veya marjı çok düşükse (%5 altı), %10'a çıkar
    if current_margin < 0.05:
        target_margin = 0.10
        
    margins = np.linspace(current_margin, target_margin, years)
    growth_rates = np.linspace(0.06, adjusted_g, years) # %6'dan başla, g'ye in
    
    fcffs = []
    last_rev = data['revenue']
    
    for i in range(years):
        gr = growth_rates[i]
        rev = last_rev * (1 + gr)
        
        projected_margin = margins[i]
        ebit = rev * projected_margin
        
        nopat = ebit * (1 - effective_tax)
        
        # Yeniden yatırım: Dengeli %20
        reinvestment = nopat * 0.20 
        
        fcff = nopat - reinvestment
        fcffs.append(fcff)
        last_rev = rev
        
    # 4. DEĞERLEME
    discount_factors = [1 / ((1 + wacc) ** (y + 1)) for y in range(years)]
    pv_fcff = np.sum(np.array(fcffs) * np.array(discount_factors))
    
    terminal_val = (fcffs[-1] * (1 + adjusted_g)) / (wacc - adjusted_g)
    if terminal_val < 0: terminal_val = 0
        
    pv_terminal = terminal_val / ((1 + wacc) ** years)
    
    enterprise_val = pv_fcff + pv_terminal
    equity_val = enterprise_val - data['total_debt'] + data['cash']
    
    dcf_price = equity_val / data['shares']
    if dcf_price < 0: dcf_price = 0
    
    # Çarpan
    multiple_price = 0.0
    if multiple:
        multiple_price = (data['revenue'] * multiple) / data['shares']
        
    return dcf_price, wacc, fcffs, multiple_price

# --- ARAYÜZ ---
if st.button("Analizi Başlat", type="primary"):
    with st.spinner('Analiz yapılıyor...'):
        fetched_data, error = get_data(ticker)
        
        if error:
            st.warning(f"⚠️ Veri çekilemedi ({error}). Manuel giriş yapın:")
            with st.expander("📝 Manuel Giriş", expanded=True):
                with st.form("manual"):
                    c1, c2 = st.columns(2)
                    m_price = c1.number_input("Fiyat", value=100.0)
                    m_shares = c2.number_input("Hisse (Milyon)", value=1000.0)
                    m_rev = c1.number_input("Ciro (Milyon)", value=50000.0)
                    m_ebit = c2.number_input("EBIT", value=8000.0)
                    m_debt = c1.number_input("Borç", value=5000.0)
                    m_cash = c2.number_input("Nakit", value=2000.0)
                    if st.form_submit_button("Hesapla"):
                        fetched_data = {
                            'ticker': ticker, 'long_name': ticker, 'currency': 'USD',
                            'current_price': m_price, 'shares': m_shares, 'beta': 0.7,
                            'total_debt': m_debt, 'cash': m_cash, 'revenue': m_rev,
                            'ebit': m_ebit, 'ebit_margin': m_ebit/m_rev if m_rev else 0,
                            'tax_rate': 0.21
                        }
                        error = None
        
        if fetched_data and not error:
            data = fetched_data
            is_loss_making = data['ebit'] < 0
            use_startup = force_startup or is_loss_making
            
            dcf_val, used_wacc, flows, mult_val = calculate_dcf(
                data, forecast_years, perpetual_growth, wacc_input,
                sector_multiple if use_startup else None
            )
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Piyasa Fiyatı", f"{data['current_price']:.2f} {data['currency']}")
            
            final_val = mult_val if use_startup else dcf_val
            label = "Startup Değeri" if use_startup else "Adil Değer (DCF)"
            
            col2.metric(label, f"{final_val:.2f} {data['currency']}")
            
            upside = (final_val / data['current_price']) - 1
            col3.metric("Potansiyel", f"%{upside*100:.1f}", 
                        delta_color="normal" if upside > 0 else "inverse")
            
            st.bar_chart(pd.DataFrame({"Nakit Akışı": flows}))
            st.info(f"ℹ️ WACC: %{used_wacc*100:.2f} | Beta: {data.get('beta', 1.0):.2f}")
