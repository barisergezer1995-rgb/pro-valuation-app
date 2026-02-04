import streamlit as st
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Amınoğlu Değerleme", page_icon="🦄", layout="wide")

# --- BAŞLIK ---
st.title("🚀 Amınoğlu Değerleme Motoru (v2.0)")
st.markdown("İskontolanmış Nakit Akışı (DCF) ve Akıllı Startup Analizi")

# --- YAN MENÜ ---
with st.sidebar:
    st.header("⚙️ Parametreler")
    ticker = st.text_input("Hisse Sembolü (Örn: NVDA, UBER, THYAO.IS)", value="UBER").upper()
    
    st.subheader("İnce Ayarlar")
    forecast_years = st.slider("Tahmin Yılı", 3, 10, 5)
    perpetual_growth = st.slider("Sonsuz Büyüme (g)", 1.0, 5.0, 2.5, 0.1) / 100
    wacc_manual = st.checkbox("WACC'ı Manuel Gir")
    
    if wacc_manual:
        wacc_input = st.slider("WACC Oranı (%)", 5.0, 25.0, 10.0, 0.5) / 100
    else:
        wacc_input = None
    
    st.markdown("---")
    st.subheader("🦄 Değerleme Modu")
    
    # Burası dinamik olacak, aşağıda mantığı var
    force_startup = st.checkbox("Startup Modunu Zorla (Manuel)")
    if force_startup:
        sector_multiple = st.slider("Sektör Çarpanı (Price/Sales)", 1.0, 50.0, 5.0, 0.5)
    else:
        sector_multiple = 5.0

# --- FONKSİYONLAR ---
@st.cache_data(ttl=3600)
def get_data(symbol):
    # DÜZELTME: Session kısmını kaldırdık çünkü yeni yfinance sürümü bunu kendi yapıyor.
    stock = yf.Ticker(symbol)
    
    try:
        info = stock.info
    except Exception as e:
        # Eğer yine de hata alırsak kullanıcıya temiz bilgi verelim
        return None, f"Yahoo Finance bağlantı hatası: {str(e)}. (Lütfen sayfayı yenileyip tekrar deneyin)"

    if 'currentPrice' not in info:
        return None, "Veri bulunamadı. Sembolü kontrol edin veya Yahoo geçici engel koymuş olabilir."
        
    bs = stock.balance_sheet
    is_stmt = stock.financials
    
    if bs.empty or is_stmt.empty:
        return None, "Finansal tablolar eksik."
        
    # --- YAŞ HESAPLAMA ---
    first_trade_ts = info.get('firstTradeDateEpochUtc', None)
    
    if first_trade_ts:
        ipo_year = datetime.fromtimestamp(first_trade_ts).year
        current_year = datetime.now().year
        company_age = current_year - ipo_year
    else:
        company_age = 5
        
    # Veri Hazırlığı
    data = {
        'ticker': symbol,
        'long_name': info.get('longName', symbol),
        'currency': info.get('currency', 'USD'),
        'current_price': info.get('currentPrice', 0),
        'shares': info.get('sharesOutstanding', 0) / 1e6,
        'beta': info.get('beta', 1.0),
        'total_debt': bs.iloc[:, 0].get('Total Debt', 0) / 1e6 if not bs.empty else 0,
        'cash': bs.iloc[:, 0].get('Cash And Cash Equivalents', 0) / 1e6 if not bs.empty else 0,
        'revenue': is_stmt.iloc[:, 0].get('Total Revenue', 0) / 1e6 if not is_stmt.empty else 0,
        'ebit': is_stmt.iloc[:, 0].get('EBIT', 0) / 1e6 if not is_stmt.empty else 0,
        'growth_start': info.get('revenueGrowth', 0.15),
        'company_age': company_age
    }
    
    # Marjlar
    data['ebit_margin'] = data['ebit'] / data['revenue'] if data['revenue'] else 0.2
    
    pretax = is_stmt.iloc[:, 0].get('Pretax Income', 0) if not is_stmt.empty else 0
    tax = is_stmt.iloc[:, 0].get('Tax Provision', 0) if not is_stmt.empty else 0
    data['tax_rate'] = tax / pretax if pretax else 0.21
    
    return data, None

def calculate_dcf(data, years, g, manual_wacc=None, multiple=None):
    # 1. WACC
    rf = 0.042
    rm = 0.05
    cost_equity = rf + data['beta'] * rm
    
    market_cap = data['shares'] * data['current_price']
    total_val = market_cap + data['total_debt']
    
    cost_debt = 0.045
    w_e = market_cap / total_val if total_val > 0 else 1
    w_d = data['total_debt'] / total_val if total_val > 0 else 0
    
    wacc = (w_e * cost_equity) + (w_d * cost_debt * (1 - data['tax_rate']))
    if manual_wacc: wacc = manual_wacc
        
    # 2. DCF Projeksiyon
    growth_rates = np.linspace(data['growth_start'], 0.04, years)
    
    fcffs = []
    last_rev = data['revenue']
    
    for gr in growth_rates:
        rev = last_rev * (1 + gr)
        # Basit FCFF Tahmini
        ebit = rev * data['ebit_margin']
        nopat = ebit * (1 - data['tax_rate'])
        reinvestment = nopat * 0.25
        
        fcff = nopat - reinvestment
        fcffs.append(fcff)
        last_rev = rev

    discount_factors = [1 / ((1 + wacc) ** (y - 0.5)) for y in range(1, years+1)]
    pv_fcff = np.sum(np.array(fcffs) * np.array(discount_factors))

    terminal_val = (fcffs[-1] * (1 + g)) / (wacc - g)
    pv_terminal = terminal_val / ((1 + wacc) ** years)
    
    enterprise_val = pv_fcff + pv_terminal
    equity_val = enterprise_val - data['total_debt'] + data['cash']
    dcf_price = equity_val / data['shares']
    
    # 3. Çarpan (Multiple) Hesabı
    multiple_price = 0
    if multiple:
        implied_cap = data['revenue'] * multiple
        multiple_price = implied_cap / data['shares']

    return dcf_price, wacc, fcffs, multiple_price

# --- ANA EKRAN MANTIĞI ---
if st.button("Analizi Başlat", type="primary"):
    with st.spinner('Veriler analiz ediliyor...'):
        data, error = get_data(ticker)
        
        if error:
            st.error(error)
        else:
            # --- AKILLI MOD SEÇİMİ ---
            is_old_company = data['company_age'] > 15
            is_loss_making = data['ebit'] < 0
            
            # Hangi modu kullanacağız?
            use_startup_mode = False
            
            if force_startup:
                use_startup_mode = True
            elif is_loss_making and not is_old_company:
                use_startup_mode = True
            
            # Hesaplama
            dcf_val, used_wacc, flows, mult_val = calculate_dcf(
                data, forecast_years, perpetual_growth, wacc_input,
                 sector_multiple if use_startup_mode else None
            )
            
            # --- SONUÇLARI GÖSTER ---
            if is_old_company and is_loss_making:
                st.warning(f"⚠️ **UYARI:** Bu şirket {data['company_age']} yıldır piyasada ama zarar ediyor. Bu bir startup değil, 'Zor Durumda' şirket olabilir.")
            elif is_old_company:
                st.info(f"ℹ️ Şirket {data['company_age']} yaşında. Olgun bir şirket olduğu için Standart DCF kullanılıyor.")
            elif use_startup_mode:
                st.success(f"🦄 **STARTUP MODU AKTİF:** Şirket genç ({data['company_age']} yaşında) veya büyüme odaklı.")
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Güncel Fiyat", f"{data['current_price']:.2f} {data['currency']}")
            
            if use_startup_mode:
                final_val = mult_val
                label = "Adil Değer (P/S Çarpanı)"
                col2.metric(label, f"{final_val:.2f} {data['currency']}", help=f"{sector_multiple}x Ciro Çarpanı")
            else:
                final_val = dcf_val
                label = "Adil Değer (DCF)"
                col2.metric(label, f"{final_val:.2f} {data['currency']}")
            
            upside = (final_val / data['current_price']) - 1
            
            # Renkli Potansiyel Gösterimi
            delta_color = "normal" if upside > 0 else "inverse"
            col3.metric("Potansiyel", f"%{upside*100:.2f}", delta=f"{upside*100:.1f}%", delta_color=delta_color)

            # Grafik
            st.bar_chart(pd.DataFrame({"Yıl": range(1, len(flows)+1), "Nakit Akışı": flows}).set_index("Yıl"))
            
            with st.expander("Şirket Kimlik Kartı"):
                st.write(f"**Tam Adı:** {data['long_name']}")
                st.write(f"**Borsa Yaşı:** {data['company_age']} Yıl")
                st.write(f"**Durum:** {'Zarar Ediyor 🔻' if is_loss_making else 'Kârlı ✅'}")
