import streamlit as st
import sqlite3
import pandas as pd
from fpdf import FPDF

# Configuração da Página
st.set_page_config(page_title="Painel Delphi", layout="wide")

USER_CREDENTIALS = {"P01": "codigo123", "P02": "codigo456", "P03": "codigo789", "P04": "codigo000", "P05": "codigo111", "P06": "codigo222"}
ADMIN_CODE = "investigador2026"

# --- FUNÇÃO GERADOR PDF ---
def generate_pdf(expert_id, round_num, respostas):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, txt=f"Relatorio de Respostas - Ronda {round_num}", ln=True, align='C')
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, txt=f"Perito: {expert_id}", ln=True)
    pdf.ln(10)
    for idx, dados in respostas.items():
        pdf.set_font("Arial", 'B', 10)
        pdf.multi_cell(0, 8, txt=f"Afirmacao {idx}: Nota {dados['score']}")
        pdf.set_font("Arial", size=10)
        pdf.multi_cell(0, 8, txt=f"Justificacao: {dados['just'] if dados['just'] else 'N/A'}")
        pdf.ln(3)
    return pdf.output(dest='S').encode('latin-1')

# --- DB ---
def get_db_connection():
    conn = sqlite3.connect("delphi_data.db")
    conn.execute('CREATE TABLE IF NOT EXISTS respostas (expert_id TEXT, round_num INTEGER, statement_id INTEGER, score INTEGER, justification TEXT, PRIMARY KEY (expert_id, round_num, statement_id))')
    return conn

# --- AFIRMAÇÕES ---
AFIRMACOES = [
    "O enfermeiro deve incluir o pai como parceiro ativo no plano de cuidados de amamentação, definindo tarefas logísticas específicas desde o pré-parto.",
    "A consulta de preparação para a parentalidade deve reservar momentos exclusivos de treino prático dirigidos ao pai, focando-se no apoio instrumental e emocional.",
    "O enfermeiro deve avaliar as competências de 'trabalho de equipa parental' e promover a negociação de papéis entre o casal para prevenir a exaustão materna.",
    "É necessário validar o papel do pai durante a consulta de aleitamento, reconhecendo a sua necessidade de suporte e inclusão na díade mãe-bebé.",
    "O enfermeiro deve aplicar sistematicamente ferramentas de avaliação familiar (genograma/ecomapa) para mapear a rede de suporte e identificar potenciais influenciadores (avós/sogras).",
    "As sessões educativas devem promover a integração de figuras transgeracionais, clarificando mitos e alinhando conselhos práticos com a evidência científica atual.",
    "A intervenção de enfermagem deve capacitar as avós/sogras para atuarem como promotoras e facilitadoras da amamentação, valorizando o seu saber experiencial.",
    "Devem ser identificadas precocemente as pressões familiares dissonantes, atuando o enfermeiro como mediador na gestão de expectativas da família alargada.",
    "O enfermeiro deve realizar uma avaliação multidimensional da família (dimensões da coesão e flexibilidade) e não apenas técnica sobre a pega do bebé.",
    "A intervenção deve ser contínua e proativa, garantindo o seguimento desde o pré-parto até ao pós-parto, com maior intensidade nos primeiros 15 dias de vida.",
    "O foco da consulta deve incidir na promoção da autoeficácia materna, utilizando estratégias de resolução de problemas e treino de competências práticas.",
    "A prática clínica deve adotar formatos híbridos (presencial e digital) que permitam o acompanhamento contínuo e a rápida resposta a dúvidas dos pais.",
    "Quando a rede de apoio informal é fraca ou ausente, o enfermeiro deve intensificar o número de contactos (presenciais ou remotos) como estratégia de compensação.",
    "O enfermeiro deve assumir um papel de 'apoio substituto', facilitando a ligação dos casais isolados a grupos de suporte comunitário ou pares.",
    "O enfermeiro deve promover espaços de reflexão clínica sobre a reorganização da vida do casal, focando na partilha equitativa de tarefas domésticas.",
    "A literacia em saúde deve incluir estratégias de comunicação conjugal para assegurar que o apoio emocional é efetivamente percebido pelo outro elemento do casal.",
    "Famílias com níveis extremos de coesão (muito ligadas/aglutinadas) devem ser sinalizadas como de risco aumentado para exaustão parental no aleitamento.",
    "O enfermeiro deve realizar rastreio de saúde mental materna e paterna, considerando que a baixa satisfação conjugal é um preditor de abandono do AME.",
    "Em caso de transição para leite adaptado por motivos clínicos ou de dor, a intervenção de enfermagem deve ser empática, focada em mitigar o sentimento de falha parental.",
    "É responsabilidade do enfermeiro treinar técnicas de extração, conservação e gestão do leite materno antes do regresso da mãe à vida profissional.",
    "Os cursos de parentalidade devem substituir a componente puramente teórica por treinos de simulação (posicionamentos, manuseamento, sinais de fome).",
    "As intervenções de educação para a saúde devem ser personalizadas às necessidades imediatas da fase de vida do bebé, abandonando o modelo 'estanque' de aulas.",
    "O treino de competências de aleitamento deve ser executado até que os pais demonstrem confiança na técnica e na gestão da dor (pega correta).",
    "As orientações fornecidas pelos diferentes níveis de cuidados (hospital/centro de saúde) devem ser unificadas, evitando mensagens contraditórias."
]

# --- LOGIN ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if not st.session_state.logged_in:
    st.title("Login - Estudo Delphi")
    u, c = st.text_input("ID"), st.text_input("Código", type="password")
    if st.button("Entrar"):
        if u in USER_CREDENTIALS and USER_CREDENTIALS[u] == c:
            st.session_state.logged_in = True; st.session_state.user = u; st.rerun()
        elif u == "admin" and c == ADMIN_CODE:
            st.session_state.logged_in = True; st.session_state.user = "ADMIN"; st.rerun()
        else: st.error("Erro")
else:
    if st.session_state.user != "ADMIN":
        expert_id = st.session_state.user
        st.sidebar.title(f"Perito: {expert_id}")
        if st.sidebar.button("Logout"): st.session_state.logged_in = False; st.rerun()
        
        conn = get_db_connection()
        # Verificar ronda automática
        df_user = pd.read_sql_query("SELECT MAX(round_num) as last_round FROM respostas WHERE expert_id = ?", conn, params=(expert_id,))
        last_round = df_user['last_round'].iloc[0]
        round_num = 1 if last_round is None else 2
        
        if round_num > 2:
            st.success("Obrigado! Estudo concluído para si.")
        else:
            st.header(f"Ronda {round_num}")
            with st.form("form"):
                respostas = {}
                for i, af in enumerate(AFIRMACOES):
                    st.markdown(f"**{af}**")
                    s = st.radio(f"Nota {i+1}", [1, 2, 3, 4, 5], key=f"s_{i}", horizontal=True)
                    j = st.text_area(f"Justificação {i+1}", key=f"j_{i}")
                    respostas[i+1] = {"score": s, "just": j, "obr": (s==1 or s==5)}
                    st.divider()
                if st.form_submit_button("Submeter"):
                    if any(d['obr'] and not d['just'] for d in respostas.values()): st.error("Justificação obrigatória (1 ou 5).")
                    else:
                        for idx, d in respostas.items():
                            conn.execute('INSERT OR REPLACE INTO respostas VALUES (?, ?, ?, ?, ?)', (expert_id, round_num, idx, d['score'], d['just']))
                        conn.commit()
                        st.session_state.pdf = generate_pdf(expert_id, round_num, respostas)
                        st.session_state.download_data = (expert_id, round_num, respostas)
                        st.rerun()
            
            if 'download_data' in st.session_state:
                st.success("Submetido!")
                st.download_button("Baixar PDF", data=st.session_state.pdf, file_name=f"ronda_{round_num}_{expert_id}.pdf")
        conn.close()
    else:
        st.title("Admin")
        conn = get_db_connection()
        st.dataframe(pd.read_sql_query("SELECT * FROM respostas", conn))
        conn.close()
