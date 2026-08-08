import streamlit as st
import sqlite3
import pandas as pd
from fpdf import FPDF

st.set_page_config(page_title="Painel Delphi - Enfermagem", layout="wide")

ADMIN_CODE = "investigador2026"

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

def get_db_connection():
    conn = sqlite3.connect("delphi_data.db")
    # Tabela de respostas
    conn.execute('CREATE TABLE IF NOT EXISTS respostas (expert_id TEXT, round_num INTEGER, statement_id INTEGER, score INTEGER, justification TEXT, PRIMARY KEY (expert_id, round_num, statement_id))')
    # Tabela de utilizadores
    conn.execute('CREATE TABLE IF NOT EXISTS utilizadores (expert_id TEXT PRIMARY KEY, password TEXT)')
    
    # Inserir utilizadores base se a tabela estiver vazia
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM utilizadores")
    if c.fetchone()[0] == 0:
        utilizadores_base = [
            ("P01", "codigo123"), ("P02", "codigo456"), 
            ("P03", "codigo789"), ("P04", "codigo000"), 
            ("P05", "codigo111"), ("P06", "codigo222"),
            ("P07", "teste123")
        ]
        c.executemany('INSERT INTO utilizadores VALUES (?, ?)', utilizadores_base)
        conn.commit()
    return conn

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

if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'submetido_sucesso' not in st.session_state: st.session_state.submetido_sucesso = False

if not st.session_state.logged_in:
    st.title("Login - Estudo Delphi")
    u, c = st.text_input("ID de Perito"), st.text_input("Código de Acesso", type="password")
    
    if st.button("Entrar"):
        if u == "admin" and c == ADMIN_CODE:
            st.session_state.logged_in = True
            st.session_state.user = "ADMIN"
            st.rerun()
        else:
            # Verificar utilizador na base de dados
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT password FROM utilizadores WHERE expert_id = ?", (u,))
            row = cursor.fetchone()
            conn.close()
            
            if row and row[0] == c:
                st.session_state.logged_in = True
                st.session_state.user = u
                st.session_state.submetido_sucesso = False
                st.rerun()
            else:
                st.error("Credenciais inválidas.")
else:
    if st.session_state.user != "ADMIN":
        expert_id = st.session_state.user
        st.sidebar.title(f"Perito: {expert_id}")
        if st.sidebar.button("Logout"): 
            st.session_state.logged_in = False
            st.session_state.submetido_sucesso = False
            st.rerun()
        
        conn = get_db_connection()
        df_all = pd.read_sql_query("SELECT * FROM respostas", conn)
        
        ja_r1 = not df_all[(df_all['expert_id'] == expert_id) & (df_all['round_num'] == 1)].empty
        ja_r2 = not df_all[(df_all['expert_id'] == expert_id) & (df_all['round_num'] == 2)].empty
        
        if not ja_r1: round_num = 1
        elif not ja_r2: round_num = 2
        else: round_num = 3
            
        if round_num == 3:
            st.success("🎉 Já concluiu todas as rondas previstas para este estudo. Muito obrigado!")
        else:
            st.header(f"Ronda {round_num}")
            
            if st.session_state.submetido_sucesso:
                st.success(f"Ronda {round_num} submetida com sucesso!")
                st.download_button(
                    f"Baixar comprovativo em PDF (Ronda {round_num})", 
                    data=st.session_state.pdf_bytes, 
                    file_name=f"ronda_{round_num}_{expert_id}.pdf"
                )
            else:
                if round_num == 1:
                    st.info("Classifique cada afirmação de 1 a 5. A justificação é obrigatória se votar 1 ou 5.")
                    with st.form("form_r1"):
                        respostas = {}
                        for i, af in enumerate(AFIRMACOES):
                            st.markdown(f"**{af}**")
                            s = st.radio(f"Nota {i+1}", [1, 2, 3, 4, 5], key=f"s_{i}", horizontal=True)
                            j = st.text_area(f"Justificação {i+1}", key=f"j_{i}")
                            respostas[i+1] = {"score": s, "just": j, "obr": (s==1 or s==5)}
                            st.divider()
                        submitted_r1 = st.form_submit_button("Submeter Ronda 1")
                        
                    if submitted_r1:
                        if any(d['obr'] and not d['just'] for d in respostas.values()):
                            st.error("Atenção: A justificação é obrigatória nas respostas 1 ou 5.")
                        else:
                            for idx, d in respostas.items():
                                conn.execute('INSERT OR REPLACE INTO respostas VALUES (?, ?, ?, ?, ?)', (expert_id, 1, idx, d['score'], d['just']))
                            conn.commit()
                            st.session_state.pdf_bytes = generate_pdf(expert_id, 1, respostas)
                            st.session_state.submetido_sucesso = True
                            st.rerun()
                
                elif round_num == 2:
                    df_r1 = df_all[df_all['round_num'] == 1]
                    divergencias = []
                    for i in range(1, 25):
                        scores_item = df_r1[df_r1['statement_id'] == i]['score']
                        if not scores_item.empty:
                            if (scores_item >= 4).mean() < 0.8:
                                divergencias.append(i)
                    
                    if not divergencias:
                        st.success("Parabéns! Todas as afirmações atingiram consenso na Ronda 1.")
                    else:
                        st.info(f"Nesta Ronda 2, responda apenas às {len(divergencias)} afirmações sem consenso.")
                        with st.form("form_r2"):
                            respostas_r2 = {}
                            for idx in divergencias:
                                voto_antigo = df_r1[(df_r1['expert_id'] == expert_id) & (df_r1['statement_id'] == idx)]['score'].values[0]
                                outros_votos = df_r1[(df_r1['statement_id'] == idx) & (df_r1['expert_id'] != expert_id)]['score'].tolist()
                                outros_str = ", ".join(map(str, outros_votos)) if outros_votos else "Sem outros registos"
                                
                                st.markdown(f"### Afirmação {idx}: {AFIRMACOES[idx-1]}")
                                st.markdown(f"👤 **Na Ronda 1, o seu voto foi:** `{voto_antigo}`")
                                st.markdown(f"👥 **Os outros participantes responderam:** `{outros_str}` (anónimo)")
                                
                                s = st.radio(f"Novo voto (Afirmação {idx})", [1, 2, 3, 4, 5], key=f"s2_{idx}", horizontal=True, index=int(voto_antigo)-1)
                                j = st.text_area(f"Nova justificação (Afirmação {idx})", key=f"j2_{idx}")
                                respostas_r2[idx] = {"score": s, "just": j, "obr": (s==1 or s==5)}
                                st.divider()
                                
                            submitted_r2 = st.form_submit_button("Submeter Ronda 2")
                            
                        if submitted_r2:
                            if any(d['obr'] and not d['just'] for d in respostas_r2.values()):
                                st.error("Atenção: A justificação é obrigatória nas respostas 1 ou 5.")
                            else:
                                for idx, d in respostas_r2.items():
                                    conn.execute('INSERT OR REPLACE INTO respostas VALUES (?, ?, ?, ?, ?)', (expert_id, 2, idx, d['score'], d['just']))
                                conn.commit()
                                st.session_state.pdf_bytes = generate_pdf(expert_id, 2, respostas_r2)
                                st.session_state.submetido_sucesso = True
                                st.rerun()
        conn.close()
    else:
        st.title("Área de Investigador (Painel de Controlo)")
        st.sidebar.button("Logout", on_click=lambda: st.session_state.update(logged_in=False))
        
        # Criar os dois separadores (Tabs)
        tab1, tab2 = st.tabs(["📊 Ver Resultados (CSV)", "👥 Gerir Utilizadores"])
        
        conn = get_db_connection()
        
        with tab1:
            st.subheader("Tabela Geral de Respostas")
            df_admin = pd.read_sql_query("SELECT * FROM respostas", conn)
            st.dataframe(df_admin)
            if not df_admin.empty:
                csv = df_admin.to_csv(index=False).encode('utf-8')
                st.download_button("Exportar todos os dados para Excel (CSV)", data=csv, file_name='dados_estudo_delphi.csv', mime='text/csv')
                
        with tab2:
            st.subheader("Adicionar Novo Perito")
            with st.form("form_novo_user"):
                novo_id = st.text_input("ID do Perito (ex: P08)")
                nova_pass = st.text_input("Código de Acesso")
                if st.form_submit_button("Adicionar Utilizador"):
                    if novo_id and nova_pass:
                        try:
                            conn.execute("INSERT INTO utilizadores VALUES (?, ?)", (novo_id, nova_pass))
                            conn.commit()
                            st.success(f"Utilizador {novo_id} criado com sucesso!")
                        except sqlite3.IntegrityError:
                            st.error(f"Erro: O ID '{novo_id}' já existe na base de dados!")
                    else:
                        st.error("Por favor, preencha o ID e o Código.")
            
            st.subheader("Utilizadores Atualmente Registados")
            df_users = pd.read_sql_query("SELECT expert_id as 'ID de Perito' FROM utilizadores", conn)
            st.dataframe(df_users)
            
        conn.close()
