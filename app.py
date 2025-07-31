# app.py - Versão Final com pyettj para Taxa Livre de Risco

import streamlit as st
import pandas as pd
import warnings
from datetime import date, datetime, timedelta
from urllib.error import URLError
from pyettj.ettj import get_ettj # NOVA IMPORTAÇÃO

# Ignorar avisos que podem poluir a saída
warnings.filterwarnings('ignore', category=FutureWarning)

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Calculadora de WACC",
    page_icon="📊",
    layout="centered"
)

# --- FUNÇÕES DE BUSCA DE DADOS (COM CACHE) ---
@st.cache_data
def get_beta_data():
    """Busca a tabela de Betas por setor do site do Damodaran."""
    try:
        url = 'https://www.stern.nyu.edu/~adamodar/pc/datasets/betas.xls'
        df = pd.read_excel(url, sheet_name='Industry Averages', skiprows=9)
        df.columns = df.columns.str.strip()
        df.dropna(how='all', inplace=True)
        df = df[['Industry Name', 'Beta']].dropna(subset=['Industry Name'])
        return df
    except Exception as e:
        st.error(f"Erro ao carregar dados de Beta: {e}")
        return pd.DataFrame()

@st.cache_data
def get_brazil_risk_premiums():
    """Busca o Prêmio de Risco (ERP) para o Brasil."""
    try:
        url = 'https://www.stern.nyu.edu/~adamodar/pc/datasets/ctryprem.xlsx'
        df = pd.read_excel(url, sheet_name='ERPs by country', header=6)
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
        brazil_data = df[df.iloc[:, 0] == 'Brazil']
        erp = brazil_data['Total Equity Risk Premium'].iloc[0]
        return erp
    except Exception as e:
        st.error(f"Erro ao carregar Prêmio de Risco: {e}")
        return None

# --- NOVA FUNÇÃO get_risk_free_rate USANDO pyettj ---
@st.cache_data
def get_risk_free_rate():
    """
    Busca a Taxa Livre de Risco usando a biblioteca pyettj para a curva prefixada.
    Busca o vértice mais próximo de 10 anos (2520 dias úteis).
    """
    dias_uteis_desejado = 2520  # Proxy para 10 anos
    data_consulta = datetime.today()
    ettj_df = None
    data_sucesso = None

    # Loop para encontrar o último dia com dados disponíveis (tenta os últimos 10 dias)
    for _ in range(10):
        try:
            data_str = data_consulta.strftime('%d/%m/%Y')
            ettj_df = get_ettj(data_str, curva='PRE')
            if not ettj_df.empty:
                data_sucesso = data_consulta
                break  # Para o loop se encontrar dados
        except Exception:
            pass  # Se der erro, tenta o dia anterior silenciosamente
        finally:
            data_consulta -= timedelta(days=1)
    
    # Se encontrou dados, processa
    if ettj_df is not None and not ettj_df.empty:
        try:
            coluna_prazo = 'Dias Corridos'
            coluna_taxa = 'DI x pré 252(2)(4)'
            
            ettj_df[coluna_prazo] = pd.to_numeric(ettj_df[coluna_prazo])
            
            # Estima o prazo em dias corridos
            dias_corridos_estimado = dias_uteis_desejado * (365 / 252)
            
            # Encontra o vértice mais próximo do prazo desejado
            indice_vertice_proximo = (ettj_df[coluna_prazo] - dias_corridos_estimado).abs().idxmin()
            vertice_encontrado = ettj_df.loc[indice_vertice_proximo]
            
            # Extrai os valores
            prazo_encontrado = int(vertice_encontrado[coluna_prazo])
            taxa_encontrada_pct = vertice_encontrado[coluna_taxa]
            
            # Converte a taxa para decimal para uso nos cálculos
            risk_free_rate = taxa_encontrada_pct / 100.0
            
            # Cria a string de informação para o usuário
            rf_info = f"Rf de {risk_free_rate:.2%} (Vértice PRE B3 de {prazo_encontrado} dias)"
            
            return risk_free_rate, rf_info, data_sucesso

        except Exception as e:
            st.error(f"Erro ao processar os dados da curva de juros da B3: {e}")
            return None, None, None
            
    # Se o loop terminar sem dados
    else:
        st.error("Não foi possível obter os dados da curva de juros da B3 para os últimos 10 dias.")
        return None, None, None

# --- O RESTANTE DO CÓDIGO PERMANECE IGUAL ---

# --- CARREGANDO DADOS ---
with st.spinner('Carregando dados de mercado... Por favor, aguarde.'):
    df_betas = get_beta_data()
    erp_brazil = get_brazil_risk_premiums()
    rf_rate, rf_info_str, data_base_rf = get_risk_free_rate()

# --- TÍTULO E DESCRIÇÃO COM LOGO ---
col1, col2 = st.columns([1, 4])
with col1:
    try:
        st.image("assets/logo.png", width=100)
    except FileNotFoundError:
        st.write("")
with col2:
    st.title("Calculadora de WACC")
    st.markdown("Ferramenta para calcular o Custo Médio Ponderado de Capital (WACC).")
st.markdown("---")

# Verifica se os dados essenciais foram carregados
if not df_betas.empty and erp_brazil is not None and rf_rate is not None:
    
    # --- SEÇÃO DE INPUTS COM 3 COLUNAS ---
    st.subheader("1. Insira os Parâmetros da Empresa")
    
    col_input1, col_input2, col_input3 = st.columns(3)

    with col_input1:
        industry_list = sorted(df_betas['Industry Name'].unique())
        selected_industry = st.selectbox(
            "Selecione o Setor:",
            industry_list,
            key="sector_selectbox"
        )
        debt_ratio_pct = st.number_input(
            "Proporção de Dívida (D/V) (%)",
            min_value=0.0, max_value=100.0, value=30.0, step=1.0, format="%.1f"
        )
        debt_ratio = debt_ratio_pct / 100.0
        
    with col_input2:
        cost_of_debt_pct = st.number_input(
            "Custo da Dívida (Kd) (%)",
            min_value=0.0, value=8.80, step=0.10, format="%.2f"
        )
        cost_of_debt = cost_of_debt_pct / 100.0
        
        tax_rate_pct = st.number_input(
            "Alíquota de Imposto (t) (%)",
            min_value=0.0, max_value=100.0, value=34.0, step=1.0, format="%.1f"
        )
        tax_rate = tax_rate_pct / 100.0

    with col_input3:
        size_premium_pct = st.number_input(
            "Prêmio de Tamanho (%)",
            min_value=0.0, value=0.0, step=0.1, format="%.2f"
        )
        size_premium = size_premium_pct / 100.0

    # --- CÁLCULOS ATUALIZADOS ---
    equity_ratio = 1 - debt_ratio
    beta = df_betas[df_betas['Industry Name'] == selected_industry]['Beta'].iloc[0]
    cost_of_equity = rf_rate + beta * erp_brazil + size_premium
    wacc = (equity_ratio * cost_of_equity) + (debt_ratio * cost_of_debt * (1 - tax_rate))

    # --- SEÇÃO DE RESULTADOS ---
    st.markdown("---")
    st.subheader("2. Resultados do Cálculo")
    
    res_col1, res_col2, res_col3 = st.columns(3)
    res_col1.metric("Custo do Equity (Re)", f"{cost_of_equity:.2%}")
    res_col2.metric("Custo da Dívida (após impostos)", f"{cost_of_debt * (1 - tax_rate):.2%}")
    res_col3.metric("WACC", f"{wacc:.2%}")
    
    # --- TABELA PARA COPIAR COM FONTES ---
    with st.expander("📋 Tabela para Copiar e Colar (Excel, Google Sheets)"):
        summary_data = {
            "Métrica": [
                "Data do Cálculo",
                "Data Base (Dados de Mercado)",
                "Taxa Livre de Risco (Rf)",
                "Prêmio de Risco de Mercado (ERP)",
                "Setor Selecionado",
                "Beta (β) do Setor",
                "Prêmio de Tamanho",
                "Proporção de Equity (E/V)",
                "Proporção de Dívida (D/V)",
                "Custo da Dívida (Kd)",
                "Alíquota de Imposto (t)",
                "CUSTO DE EQUITY (Re)",
                "WACC"
            ],
            "Valor": [
                date.today().strftime('%d/%m/%Y'),
                data_base_rf.strftime('%d/%m/%Y'),
                f"{rf_rate:.2%}",
                f"{erp_brazil:.2%}",
                selected_industry,
                f"{beta:.4f}",
                f"{size_premium:.2%}",
                f"{equity_ratio:.2%}",
                f"{debt_ratio:.2%}",
                f"{cost_of_debt:.2%}",
                f"{tax_rate:.2%}",
                f"{cost_of_equity:.2%}",
                f"{wacc:.2%}"
            ],
            "Fonte": [
                "Automático",
                "Automático",
                "B3 (via pyettj)",
                "Damodaran Online",
                "Input do Usuário",
                "Damodaran Online",
                "Input do Usuário",
                "Cálculo Interno",
                "Input do Usuário",
                "Input do Usuário",
                "Input do Usuário",
                "Cálculo Interno",
                "Cálculo Interno"
            ]
        }
        summary_df = pd.DataFrame(summary_data)
        st.dataframe(summary_df, hide_index=True, use_container_width=True)

    # --- DETALHAMENTO DAS FÓRMULAS ATUALIZADO ---
    with st.expander("🔎 Detalhamento das Fórmulas"):
        st.info(rf_info_str, icon="📄")
        st.subheader("Cálculo do Custo de Equity (Re)")
        st.latex(r'''R_e = R_f + (\beta \times ERP) + \text{Prêmio de Tamanho}''')
        st.latex(f"R_e = {rf_rate:.2%} + ({beta:.4f} \\times {erp_brazil:.2%}) + {size_premium:.2%} = \\textbf{{{cost_of_equity:.2%}}}")
        
        st.subheader("Cálculo do WACC")
        st.latex(r'''\text{WACC} = \left( \frac{E}{V} \times R_e \right) + \left( \frac{D}{V} \times R_d \times (1 - t) \right)''')
        st.latex(f"\\text{{WACC}} = ({equity_ratio:.0%} \\times {cost_of_equity:.2%}) + ({debt_ratio:.0%} \\times {cost_of_debt:.2%} \\times (1 - {tax_rate:.0%})) = \\textbf{{{wacc:.2%}}}")

else:
    st.warning("A aplicação não pode continuar pois um ou mais dados de mercado não foram carregados. Verifique as mensagens de erro acima.")
