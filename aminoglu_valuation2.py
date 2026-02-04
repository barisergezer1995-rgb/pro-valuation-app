import streamlit as st
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Amınoğlu Değerleme", page_icon="🦄", layout="wide")

# --- BAŞLIK ---
st.title("🚀 Amınoğlu Değerleme (v3.0 - Stabil)")
st.markdown("İskontolanmış Nakit Akışı (DCF) ve Akıllı Startup Analizi")

# --- YAN MENÜ ---
with st.sidebar:
    st.header("⚙️ Parametreler")
    ticker = st.text_input("Hisse Sembolü (Örn: MRK, NVDA, THYAO.IS)", value="MRK").upper()
    
    st.subheader("İnce Ayarlar")
    forecast_years = st.slider("Tahmin Yılı", 3, 10, 5)
    perpetual_growth = st.slider("Sonsuz Büyüme (g)", 0.5, 4.0, 2.5, 0.1) / 100
    wacc_manual = st.checkbox("WACC'ı Manuel Gir")
    
    if wacc_manual:
        wacc_input = st.slider("WACC Oranı (%)", 5.0, 20.0, 9.0, 0.5) / 100
    else:
        wacc_input = None
    
    st.markdown("---")
    st.subheader("🦄 Değerleme Modu")
    
    force_startup = st.checkbox("Startup Modunu Zorla")
    if force_startup:
        sector_multiple = st.slider("Sektör Çarpanı (Price/Sales)", 1.0, 50.0, 5.0, 0.5)
    else:
        sector_multiple = 5.0

# --- YARDIMCI: Güvenli Veri Okuma ---
def safe_float(val):
    try:
        if val is None or np.isnan(val): return 0.0
        return float(val)
    except:
        return 0.0

# --- VERİ ÇEKME FONKSİYONU (Robust) ---
@st.cache_data(ttl=3600)
def get_data(symbol):
    stock = yf.Ticker(symbol)
    data = {}
    
    try:
        # 1. YÖNTEM: fast_info (Daha hızlı, daha az banlanır)
        # Yahoo'nun yeni API yapısı burayı daha çok seviyor
        current_price = stock.fast_info.get('last_price', None)
        shares = stock.fast_info.get('shares', None)
        
        # Fiyat yoksa history'den zorla
        if current_price is None or np.isnan(safe_float(current_price)):
            hist = stock.history(period="1d")
            if not hist.empty:
                current_price = hist['Close'].iloc[-1]
            else:
                return None, "Fiyat verisi çekilemedi."

        # Tabloları Çek
        bs = stock.balance_sheet
        is_stmt = stock.financials
        
        if bs.empty or is_stmt.empty:
            return None, "Finansal tablolar boş (Yahoo Engeli)."

        # --- VERİLERİ DOLDUR ---
        data['ticker'] = symbol
        data['long_name'] = symbol
        data['currency'] = stock.fast_info.get('currency', 'USD')
        data['current_price'] = safe_float(current_price)
        data['shares'] = safe_float(shares) / 1e6 # Milyon adet
        
        if data['shares'] <= 0: data['shares'] = 1.0 # Bölme hatası önlemi

        # Beta (Bazen info'da olur, yoksa 1.0 al)
        try:
            data['beta'] = stock.info.get('beta', 1.0)
        except:
            data['beta'] = 1.0

        # Tablodan Veriler (İlk sütun en günceldir)
        data['total_debt'] = safe_float(bs.iloc[:, 0].get('Total Debt')) / 1e6
        data['cash'] = safe_float(bs.iloc[:, 0].get('Cash And Cash Equivalents')) / 1e6
        data['revenue'] = safe_float(is_stmt.iloc[:, 0].get('Total Revenue')) / 1e6
        data['ebit'] = safe_float(is_stmt.iloc[:, 0].get('EBIT')) / 1e6
        
        # Eğer EBIT yoksa (Banka/Sigorta vs), Operating Income dene
        if data['ebit'] == 0:
            data['ebit'] = safe_float(is_stmt.iloc[:, 0].get('Operating Income')) / 1e6

        data['growth_start'] = 0.10 # Varsayılan %10 başlat, aşağıda düzelteceğiz
        data['company_age'] = 10    # Varsayılan
        
        # Marj
        if data['revenue'] > 0:
            data['ebit_margin'] = data['ebit'] / data['revenue']
        else:
            data['ebit_margin'] = 0.15 # Gelir yoksa varsayılan marj
        
        # Vergi Oranı
        pretax = safe_float(is_stmt.iloc[:, 0].get('Pretax Income'))
        tax = safe_float(is_stmt.iloc[:, 0].get('Tax Provision'))
        if pretax > 0:
            data['tax_rate'] = tax / pretax
        else:
            data['tax_rate'] = 0.21
            
        return data, None

    except Exception as e:
        return None, f"Veri Hatası: {str(e)}"

# --- HESAPLAMA MOTORU (Optimize Edilmiş) ---
def calculate_dcf(data, years, g, manual_wacc=None, multiple=None):
    # 1. AKILLI WACC
    rf = 0.040 # %4.0
    rm = 0.050 # %5.0
    
    # Beta Düzeltme (0.6 ile 1.5 arasına sıkıştır)
    # Çok düşük beta (0.1) veya çok yüksek beta (3.0) DCF'i bozar.
    raw_beta = safe_float(data.get('beta', 1.0))
    beta = max(0.6, min(raw_beta, 1.5))
    
    cost_equity = rf + beta * rm
    
    market_cap = data['shares'] * data['current_price']
    total_val = market_cap + data['total_debt']
    if total_val <= 0: total_val = market_cap if market_cap > 0 else 1.0
    
    # Ağırlıklar
    w_e = market_cap / total_val
    w_d = data['total_debt'] / total_val
    
    cost_debt = 0.06 # Ortalama borç maliyeti
    effective_tax = min(max(data['tax_rate'], 0.15), 0.30) # Vergiyi %15-%30 bandına çek
    
    wacc = (w_e * cost_equity) + (w_d * cost_debt * (1 - effective_tax))
    
    # WACC FRENİ: %7'nin altı veya %13'ün üstü şüphelidir, düzelt.
    if manual_wacc:
        wacc = manual_wacc
    else:
        wacc = max(0.07, min(wacc, 0.13))
        
    # 2. BÜYÜME ve TERMİNAL KİLİDİ
    # g, WACC'tan büyük olamaz. Olursa patlar.
    # Güvenlik marjı olarak g'yi WACC - %1.5 seviyesine çekeriz.
    adjusted_g = g
    if adjusted_g >= wacc:
        adjusted_g = wacc - 0.015
        
    # 3. PROJEKSİYON (Mean Reversion / Ortalamaya Dönüş)
    # Şirket zarar ediyorsa veya marjı çok düşükse, 5 yılda %15 marja yükseleceğini varsay.
    current_margin = data['ebit_margin']
    target_margin = max(current_margin, 0.15) 
    
    margins = np.linspace(current_margin, target_margin, years)
    growth_rates = np.linspace(0.08, adjusted_g, years) # %8 ile başla, g'ye düş
    
    fcffs = []
    last_rev = data['revenue']
    
    for i in range(years):
        gr = growth_rates[i]
        rev = last_rev * (1 + gr)
        
        projected_margin = margins[i]
        ebit = rev * projected_margin
        
        nopat = ebit * (1 - effective_tax)
        reinvestment = nopat * 0.20 # %20 yeniden yatırım (Standart)
        
        fcff = nopat - reinvestment
        fcffs.append(fcff)
        last_rev = rev
        
    # 4. DEĞERLEME
    discount_factors = [1 / ((1 + wacc) ** (y + 1)) for y in range(years)]
    pv_fcff = np.sum(np.array(fcffs) * np.array(discount_factors))
    
    # Terminal Değer
    terminal_val = (fcffs[-1] * (1 + adjusted_g)) / (wacc - adjusted_g)
    # Terminal değer negatif olamaz
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
    with st.spinner('Veriler analiz ediliyor...'):
        fetched_data, error = get_data(ticker)
        
        # Veri çekilemezse MANUEL GİRİŞİ aç
        if error:
            st.warning(f"⚠️ Otomatik veri çekilemedi ({error}). Lütfen aşağıdan manuel girin.")
            with st.expander("📝 Manuel Veri Girişi", expanded=True):
                with st.form("manual_entry"):
                    c1, c2 = st.columns(2)
                    m_price = c1.number_input("Güncel Fiyat", value=100.0)
                    m_shares = c2.number_input("Hisse Adedi (Milyon)", value=1000.0)
                    m_rev = c1.number_input("Yıllık Ciro (Milyon)", value=50000.0)
                    m_ebit = c2.number_input("EBIT (Faiz Vergi Öncesi Kar)", value=8000.0)
                    m_debt = c1.number_input("Toplam Borç (Milyon)", value=10000.0)
                    m_cash = c2.number_input("Nakit (Milyon)", value=5000.0)
                    
                    if st.form_submit_button("Hesapla"):
                        fetched_data = {
                            'ticker': ticker, 'long_name': ticker, 'currency': 'USD',
                            'current_price': m_price, 'shares': m_shares, 'beta': 1.0,
                            'total_debt': m_debt, 'cash': m_cash, 'revenue': m_rev,
                            'ebit': m_ebit, 'ebit_margin': m_ebit/m_rev if m_rev else 0,
                            'tax_rate': 0.21
                        }
                        error = None
        
        # Veri varsa hesapla
        if fetched_data and not error:
            data = fetched_data
            
            # Mod Seçimi
            is_loss_making = data['ebit'] < 0
            use_startup = force_startup or is_loss_making
            
            dcf_val, used_wacc, flows, mult_val = calculate_dcf(
                data, forecast_years, perpetual_growth, wacc_input,
                sector_multiple if use_startup else None
            )
            
            # --- GÖSTERGE PANELİ ---
            col1, col2, col3 = st.columns(3)
            col1.metric("Piyasa Fiyatı", f"{data['current_price']:.2f} {data['currency']}")
            
            final_val = mult_val if use_startup else dcf_val
            label = "Startup Değeri (P/S)" if use_startup else "Adil Değer (DCF)"
            
            col2.metric(label, f"{final_val:.2f} {data['currency']}")
            
            upside = (final_val / data['current_price']) - 1
            col3.metric("Potansiyel", f"%{upside*100:.1f}", 
                        delta_color="normal" if upside > 0 else "inverse")
            
            # Grafik
            st.bar_chart(pd.DataFrame({"Gelecek Nakit Akışı": flows}))
            
            st.info(f"ℹ️ **Analiz Notu:** Hesaplamada WACC: %{used_wacc*100:.1f} kullanıldı.")
            if use_startup:
                st.success("Bu şirket zarar ettiği veya başlangıç aşamasında olduğu için Ciro Çarpanı ile değerlendi.")

