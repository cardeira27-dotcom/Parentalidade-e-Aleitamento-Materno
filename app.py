import streamlit as st
import sqlite3
import pandas as pd
from fpdf import FPDF

st.set_page_config(page_title="Painel Delphi - Enfermagem", layout="wide")

USER_CREDENTIALS = {
    "P01": "codigo123", "P02": "codigo456", "P03": "codigo789", 
    "P04": "codigo000", "P05": "codigo111", "P06": "codigo222",
    "teste1": "teste1", "teste2": "teste2", "teste3": "teste3", 
    "teste4": "teste4", "teste5": "teste5", "teste6": "teste6"
}
ADMIN_CODE = "investigador2026"

MAIN_GROUP = ["P01", "P02", "P03", "P04", "P05", "P06"]
TEST_GROUP = ["teste1", "teste2", "teste3", "teste4", "teste5", "teste6"]

LISTA_24_AFIRMACOES = [
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

def generate_pdf(expert_id, round_num, respostas, afirmacoes_dict):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, txt=f"Relatorio de Respostas - Ronda {round_num}", ln=True, align='C')
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, txt=f"Perito: {expert_id}", ln=True)
    pdf.ln(10)
    for idx, dados in respostas.items():
        af_texto = afirmacoes_dict.get(idx, f"Afirmacao {idx}")
        pdf.set_font("Arial", 'B', 10)
        pdf.multi_cell(0, 8, txt=f"[{idx}] {af_texto} - Nota: {dados['score']}")
        pdf.set_font("Arial", size=10)
        pdf.multi_cell(0, 8, txt=f"Justificacao: {dados['just'] if dados['just'] else 'N/A'}")
        pdf.ln(3)
    return pdf.output(dest='S').encode('latin-1')

def init_db():
    conn = sqlite3.connect("delphi_data.db")
    conn.execute('CREATE TABLE IF NOT EXISTS respostas (expert_id TEXT, round_num INTEGER, statement_id INTEGER, score INTEGER, justification TEXT, PRIMARY KEY (expert_id, round_num, statement_id))')
    conn.execute('CREATE TABLE IF NOT EXISTS afirmacoes (id INTEGER PRIMARY KEY AUTOINCREMENT, texto TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)')
    
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM afirmacoes')
    if c.fetchone()[0] == 0:
        for af in LISTA_24_AFIRMACOES:
            c.execute('INSERT INTO afirmacoes (texto) VALUES (?)', (af,))
            
    c.execute('SELECT COUNT(*) FROM config')
    if c.fetchone()[0] == 0:
        c.execute('INSERT INTO config VALUES ("scale_min", "1")')
        c.execute('INSERT INTO config VALUES ("scale_max", "5")')
        c.execute('INSERT INTO config VALUES ("mandatory_scores", "1,5")')
    
    conn.commit()
    conn.close()

init_db()

def get_config():
    conn = sqlite3.connect("delphi_data.db")
    df_conf = pd.read_sql_query("SELECT * FROM config", conn)
    conn.close()
    conf_dict = dict(zip(df_conf['chave'], df_conf['valor']))
    return int(conf_dict.get('scale_min', 1)), int(conf_dict.get('scale_max', 5)), conf_dict.get('mandatory_scores', '1,5')

def get_afirmacoes():
    conn = sqlite3.connect("delphi_data.db")
    df_af = pd.read_sql_query("SELECT * FROM afirmacoes", conn)
    conn.close()
    return dict(zip(df_af['id'], df_af['texto']))

if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'submetido_sucesso' not in st.session_state: st.session_state.submetido_sucesso = False

if not st.session_state.logged_in:
    st.title("Login - Estudo Delphi")
    u, c = st.text_input("ID de Perito"), st.text_input("Código de Acesso", type="password")
    if st.button("Entrar"):
        if u in USER_CREDENTIALS and USER_CREDENTIALS[u] == c:
            st.session_state.logged_in = True; st.session_state.user = u; st.session_state.submetido_sucesso = False; st.rerun()
        elif u == "admin" and c == ADMIN_CODE:
            st.session_state.logged_in = True; st.session_state.user = "ADMIN"; st.rerun()
        else: st.error("Credenciais inválidas.")
else:
    scale_min, scale_max, mandatory_str = get_config()
    mandatory_list = [int(x.strip()) for x in mandatory_str.split(",") if x.strip().isdigit()]
    AFIRMACOES = get_afirmacoes()
    
    if st.session_state.user != "ADMIN":
        expert_id = st.session_state.user
        st.sidebar.title(f"Perito: {expert_id}")
        if st.sidebar.button("Logout"): 
            st.session_state.logged_in = False
            st.session_state.submetido_sucesso = False
            st.rerun()
        
        conn = sqlite3.connect("delphi_data.db")
        df_all = pd.read_sql_query("SELECT * FROM respostas", conn)
        
        current_group = MAIN_GROUP if expert_id in MAIN_GROUP else TEST_GROUP
        ja_r1 = not df_all[(df_all['expert_id'] == expert_id) & (df_all['round_num'] == 1)].empty
        ja_r2 = not df_all[(df_all['expert_id'] == expert_id) & (df_all['round_num'] == 2)].empty
        
        df_r1_group = df_all[(df_all['round_num'] == 1) & (df_all['expert_id'].isin(current_group))]
        completed_r1_count = df_r1_group['expert_id'].nunique()
        all_group_finished = (completed_r1_count >= len(current_group))
        
        if not ja_r1: round_num = 1
        elif ja_r2: round_num = 3
        else: round_num = 2 if all_group_finished else "espera_r2"
            
        if round_num == 3:
            st.success("🎉 Estudo concluído. Obrigado!")
        elif round_num == "espera_r2":
            st.info(f"⏳ **Obrigado por submeter a Ronda 1!**\n\nA Ronda 2 só ficará disponível quando todos os 6 elementos do seu grupo concluírem a Ronda 1. Concluídos: **{completed_r1_count}/6**.")
        else:
            st.header(f"Ronda {round_num}")
            if st.session_state.submetido_sucesso:
                st.success("Submetido com sucesso!")
                st.download_button(f"Baixar PDF (Ronda {round_num})", data=st.session_state.pdf_bytes, file_name=f"ronda_{round_num}_{expert_id}.pdf")
            else:
                scale_options = list(range(scale_min, scale_max + 1))
                if round_num == 1:
                    with st.form("r1"):
                        respostas = {}
                        for af_id, af_text in AFIRMACOES.items():
                            st.markdown(f"**{af_text}**")
                            s = st.radio(f"Nota para questão {af_id}", scale_options, key=f"s_{af_id}", horizontal=True)
                            j = st.text_area(f"Justificação {af_id}", key=f"j_{af_id}")
                            respostas[af_id] = {"score": s, "just": j, "obr": (s in mandatory_list)}
                            st.divider()
                        if st.form_submit_button("Submeter"):
                            if any(d['obr'] and not d['just'] for d in respostas.values()): 
                                st.error(f"Justificação obrigatória para as notas: {mandatory_list}.")
                            else:
                                for idx, d in respostas.items(): 
                                    conn.execute('INSERT OR REPLACE INTO respostas VALUES (?, ?, ?, ?, ?)', (expert_id, 1, idx, d['score'], d['just']))
                                conn.commit()
                                st.session_state.pdf_bytes = generate_pdf(expert_id, 1, respostas, AFIRMACOES)
                                st.session_state.submetido_sucesso = True
                                st.rerun()
                else:
                    df_r1 = df_all[df_all['round_num'] == 1]
                    div = []
                    for af_id in AFIRMACOES.keys():
                        scores_item = df_r1[df_r1['statement_id'] == af_id]['score']
                        if not scores_item.empty:
                            high_scores = (scores_item >= (scale_max - 1)).mean()
                            if high_scores < 0.8: div.append(af_id)
                    
                    if not div:
                        st.success("Parabéns! Todas as afirmações atingiram consenso.")
                    else:
                        with st.form("r2"):
                            respostas_r2 = {}
                            for idx in div:
                                af_text = AFIRMACOES.get(idx, "")
                                voto_ant = df_r1[(df_r1['expert_id'] == expert_id) & (df_r1['statement_id'] == idx)]['score'].values
                                voto_ant = voto_ant[0] if len(voto_ant) > 0 else scale_min
                                outros = ", ".join(map(str, df_r1[(df_r1['statement_id'] == idx) & (df_r1['expert_id'] != expert_id)]['score'].tolist()))
                                
                                st.markdown(f"### {af_text}")
                                st.markdown(f"👤 Seu voto R1: `{voto_ant}` | 👥 Outros: `{outros}`")
                                
                                try:
                                    default_idx = scale_options.index(int(voto_ant))
                                except ValueError:
                                    default_idx = 0
                                    
                                s = st.radio(f"Novo voto {idx}", scale_options, key=f"s2_{idx}", horizontal=True, index=default_idx)
                                j = st.text_area(f"Justificação {idx}", key=f"j2_{idx}")
                                respostas_r2[idx] = {"score": s, "just": j, "obr": (s in mandatory_list)}
                                st.divider()
                            if st.form_submit_button("Submeter"):
                                if any(d['obr'] and not d['just'] for d in respostas_r2.values()): 
                                    st.error(f"Justificação obrigatória para as notas: {mandatory_list}.")
                                else:
                                    for idx, d in respostas_r2.items(): 
                                        conn.execute('INSERT OR REPLACE INTO respostas VALUES (?, ?, ?, ?, ?)', (expert_id, 2, idx, d['score'], d['just']))
                                    conn.commit()
                                    st.session_state.pdf_bytes = generate_pdf(expert_id, 2, respostas_r2, AFIRMACOES)
                                    st.session_state.submetido_sucesso = True
                                    st.rerun()
        conn.close()
    else:
        # --- ÁREA DO ADMINISTRADOR ---
        st.sidebar.title("Painel Admin")
        if st.sidebar.button("Logout"): 
            st.session_state.logged_in = False
            st.session_state.submetido_sucesso = False
            st.rerun()
            
        st.title("Painel do Investigador")
        
        tab1, tab2, tab3 = st.tabs(["📊 Respostas e Relatórios", "📝 Gerir Afirmações", "⚙️ Configurar Escala e Regras"])
        
        conn = sqlite3.connect("delphi_data.db")
        
        with tab1:
            df_adm = pd.read_sql_query("SELECT * FROM respostas", conn)
            st.dataframe(df_adm, use_container_width=True)
            if not df_adm.empty:
                csv = df_adm.to_csv(index=False).encode('utf-8')
                st.download_button("Exportar Excel (CSV)", data=csv, file_name='dados.csv')
                st.markdown("---")
                st.subheader("PDF Individual")
                u_sel = st.selectbox("Perito", list(USER_CREDENTIALS.keys()))
                r_sel = st.selectbox("Ronda", [1, 2])
                if st.button("Gerar PDF"):
                    df_p = df_adm[(df_adm['expert_id'] == u_sel) & (df_adm['round_num'] == r_sel)]
                    if not df_p.empty:
                        d = {int(r['statement_id']): {"score": int(r['score']), "just": r['justification']} for _, r in df_p.iterrows()}
                        st.download_button("Baixar PDF", data=generate_pdf(u_sel, r_sel, d, AFIRMACOES), file_name=f"res_{u_sel}_r{r_sel}.pdf")
                    else: st.warning("Sem dados.")
                    
        with tab2:
            st.subheader("Gerir Afirmações")
            
            # Botão para carregar as 24 oficiais automaticamente
            if st.button("🔄 Carregar as 24 Afirmações Oficiais"):
                conn.execute("DELETE FROM afirmacoes")
                for af in LISTA_24_AFIRMACOES:
                    conn.execute("INSERT INTO afirmacoes (texto) VALUES (?)", (af,))
                conn.commit()
                st.success("As 24 afirmações oficiais foram carregadas com sucesso!")
                st.rerun()
                
            st.markdown("---")
            nova_af = st.text_area("Adicionar Nova Afirmação Individual")
            if st.button("Adicionar Afirmação"):
                if nova_af.strip():
                    conn.execute("INSERT INTO afirmacoes (texto) VALUES (?)", (nova_af,))
                    conn.commit()
                    st.success("Afirmação adicionada com sucesso!")
                    st.rerun()
                else:
                    st.error("O texto não pode estar vazio.")
                    
            st.markdown("---")
            st.subheader("Lista de Afirmações Atuais")
            df_af_list = pd.read_sql_query("SELECT * FROM afirmacoes", conn)
            for _, row in df_af_list.iterrows():
                col1, col2 = st.columns([8, 1])
                with col1:
                    st.write(f"**ID {row['id']}**: {row['texto']}")
                with col2:
                    if st.button("❌ Apagar", key=f"del_{row['id']}"):
                        conn.execute("DELETE FROM afirmacoes WHERE id = ?", (row['id'],))
                        conn.commit()
                        st.rerun()
                        
        with tab3:
            st.subheader("Configuração da Escala de Likert e Obrigatoriedade")
            s_min = st.number_input("Valor Mínimo da Escala", value=scale_min)
            s_max = st.number_input("Valor Máximo da Escala", value=scale_max)
            m_scores = st.text_input("Valores que exigem justificação obrigatória (separados por vírgula)", value=mandatory_str)
            
            if st.button("Guardar Configurações"):
                conn.execute("INSERT OR REPLACE INTO config (chave, valor) VALUES ('scale_min', ?)", (str(s_min),))
                conn.execute("INSERT OR REPLACE INTO config (chave, valor) VALUES ('scale_max', ?)", (str(s_max),))
                conn.execute("INSERT OR REPLACE INTO config (chave, valor) VALUES ('mandatory_scores', ?)", (m_scores,))
                conn.commit()
                st.success("Configurações guardadas com sucesso!")
                st.rerun()
                
        conn.close()
