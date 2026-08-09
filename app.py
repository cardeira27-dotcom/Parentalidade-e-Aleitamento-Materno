import streamlit as st
import sqlite3
import pandas as pd
from fpdf import FPDF
import io
import hashlib
import secrets
import datetime

st.set_page_config(page_title="Painel Delphi - Enfermagem", layout="wide")

ADMIN_CODE = "investigador2026"

def hash_password(password):
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
    return f"{salt}${pwd_hash}"

def verify_password(stored_password, provided_password, conn=None, user_id=None):
    if '$' not in stored_password:
        if stored_password == provided_password:
            if conn and user_id:
                new_hash = hash_password(provided_password)
                conn.execute("UPDATE utilizadores SET password = ? WHERE expert_id = ?", (new_hash, user_id))
                conn.commit()
            return True
        return False
    
    parts = stored_password.split('$')
    if len(parts) != 2: return False
    salt, pwd_hash = parts
    verify_hash = hashlib.pbkdf2_hmac('sha256', provided_password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
    return verify_hash == pwd_hash

def safe_txt(txt):
    return str(txt).encode('latin-1', 'replace').decode('latin-1')

def calcular_consenso_percentual(notas, escala_max):
    if len(notas) == 0:
        return 0.0
    cons_acc = (notas >= escala_max - 1).mean()
    cons_rej = (notas <= 2).mean()
    return max(cons_acc, cons_rej) * 100

def generate_expert_report_pdf(expert_id, conn, specific_round=None):
    pdf = FPDF()
    pdf.add_page()
    
    df_res = pd.read_sql_query("SELECT * FROM respostas WHERE expert_id=?", conn, params=(expert_id,))
    df_af = pd.read_sql_query("SELECT * FROM afirmacoes", conn)
    df_t = pd.read_sql_query("SELECT * FROM tempos_ronda WHERE expert_id=?", conn, params=(expert_id,))
    
    titulo = "Relatorio Completo de Respostas" if specific_round is None else f"Relatorio de Respostas - Ronda {specific_round}"
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, txt=safe_txt(titulo), ln=True, align='C')
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, txt=safe_txt(f"Perito: {expert_id}"), ln=True)
    pdf.ln(5)
    
    rondas_to_print = [specific_round] if specific_round else sorted(df_res['round_num'].unique())
    
    for r in rondas_to_print:
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 10, txt=safe_txt(f"--- RONDA {r} ---"), ln=True)
        
        t_row = df_t[df_t['round_num'] == r]
        if not t_row.empty:
            dur = t_row.iloc[0]['duration_seconds']
            mins, secs = divmod(int(dur), 60)
            pdf.set_font("Arial", 'I', 10)
            pdf.cell(0, 6, txt=safe_txt(f"Tempo gasto na ronda: {mins}m {secs}s"), ln=True)
        pdf.ln(3)
        
        df_r = df_res[df_res['round_num'] == r]
        for _, row in df_r.iterrows():
            stmt_id = row['statement_id']
            score = row['score']
            just = row['justification']
            texto_af = df_af[df_af['id'] == stmt_id]['texto'].values[0]
            
            pdf.set_font("Arial", 'B', 10)
            pdf.multi_cell(0, 6, txt=safe_txt(f"Afirmacao ID {stmt_id}: {texto_af}"))
            pdf.set_font("Arial", size=10)
            pdf.multi_cell(0, 6, txt=safe_txt(f"Nota: {score} | Justificacao: {just if just else 'N/A'}"))
            pdf.ln(3)
        pdf.ln(5)
        
    return pdf.output(dest='S').encode('latin-1')

def generate_admin_report_pdf(df_respostas, df_users, df_afirmacoes, escala_max, df_tempos):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, txt=safe_txt("Relatorio Global do Estudo Delphi"), ln=True, align='C')
    pdf.set_font("Arial", size=11)
    pdf.cell(0, 8, txt=safe_txt(f"Total de Peritos Registados: {len(df_users)}"), ln=True)
    pdf.cell(0, 8, txt=safe_txt(f"Total de Afirmacoes no Estudo: {len(df_afirmacoes)}"), ln=True)
    pdf.ln(10)
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, txt=safe_txt("Resumo Estatistico por Ronda:"), ln=True)
    
    if not df_respostas.empty:
        todas_rondas = sorted(df_respostas['round_num'].unique())
        for r in todas_rondas:
            pdf.ln(5)
            pdf.set_font("Arial", 'B', 11)
            pdf.cell(0, 8, txt=safe_txt(f"--- RONDA {r} ---"), ln=True)
            pdf.set_font("Arial", size=10)
            
            df_r = df_respostas[df_respostas['round_num'] == r]
            pivot = df_r.pivot(index='statement_id', columns='expert_id', values='score')
            
            for idx, row in pivot.iterrows():
                notas = row.dropna()
                if len(notas) > 0:
                    media = notas.mean()
                    cons = calcular_consenso_percentual(notas, escala_max)
                    pdf.multi_cell(0, 6, txt=safe_txt(f"Afirmacao ID {idx}: Media = {media:.2f} | Indice Consenso = {cons:.1f}%"))
            
            if not df_tempos.empty:
                df_t_r = df_tempos[df_tempos['round_num'] == r]
                if not df_t_r.empty:
                    media_tempo = df_t_r['duration_seconds'].mean()
                    mm, ss = divmod(int(media_tempo), 60)
                    pdf.ln(2)
                    pdf.cell(0, 6, txt=safe_txt(f"Tempo medio de resposta na Ronda {r}: {mm}m {ss}s"), ln=True)
    else:
        pdf.set_font("Arial", size=10)
        pdf.cell(0, 10, txt=safe_txt("Ainda nao existem respostas registadas no sistema."), ln=True)
        
    return pdf.output(dest='S').encode('latin-1')

def generate_ai_analysis_prompt(conn, escala_max):
    df_res = pd.read_sql_query("SELECT * FROM respostas", conn)
    df_users = pd.read_sql_query("SELECT * FROM utilizadores", conn)
    df_af = pd.read_sql_query("SELECT * FROM afirmacoes", conn)
    df_tempos = pd.read_sql_query("SELECT * FROM tempos_ronda", conn)
    
    if df_res.empty:
        return "Ainda não existem dados de respostas suficientes para gerar a análise para a IA."
        
    prompt = "Atue como um Investigador Doutorado especialista em Enfermagem e Metodologia Delphi. Analise criticamente os seguintes resultados obtidos num estudo Delphi sobre parentalidade e aleitamento materno:\n\n"
    prompt += f"- Total de Peritos Participantes: {len(df_users)}\n"
    prompt += f"- Total de Afirmações Avaliadas: {len(df_af)}\n"
    prompt += f"- Escala de Likert utilizada: 1 a {escala_max}\n"
    prompt += "- Limiar de Consenso definido: >= 80% das respostas nos valores mais altos ou mais baixos da escala.\n\n"
    
    prompt += "--- TEMPOS MÉDIOS DE RESPOSTA ---\n"
    if not df_tempos.empty:
        for r in sorted(df_tempos['round_num'].unique()):
            media_s = df_tempos[df_tempos['round_num'] == r]['duration_seconds'].mean()
            mm, ss = divmod(int(media_s), 60)
            prompt += f"- Ronda {r}: Tempo médio de resposta = {mm} minutos e {ss} segundos.\n"
    
    prompt += "\n--- DADOS QUANTITATIVOS E QUALITATIVOS POR RONDA ---\n"
    todas_rondas = sorted(df_res['round_num'].unique())
    for r in todas_rondas:
        prompt += f"\n### RONDA {r}\n"
        df_r = df_res[df_res['round_num'] == r]
        for _, af_row in df_af.iterrows():
            stmt_id = af_row['id']
            texto_af = af_row['texto']
            df_item = df_r[df_r['statement_id'] == stmt_id]
            if not df_item.empty:
                scores = df_item['score'].dropna()
                media = scores.mean() if len(scores) > 0 else 0
                std = scores.std() if len(scores) > 1 else 0
                consenso = calcular_consenso_percentual(scores, escala_max)
                
                prompt += f"- Afirmação {stmt_id}: \"{texto_af}\"\n"
                prompt += f"  * Média: {media:.2f} | Desvio Padrão: {std:.2f} | Consenso: {consenso:.1f}%\n"
                
                justs = df_item[df_item['justification'].str.strip() != '']['justification'].tolist()
                if justs:
                    prompt += f"  * Justificações qualitativas dos peritos: {'; '.join([f'\"{j}\"' for j in justs])}\n"
                    
    prompt += "\n--- INSTRUÇÕES PARA A TESE / ANÁLISE ---\n"
    prompt += "Com base nestes dados estruturados, elabore um texto académico formal para a secção de 'Discussão e Análise de Resultados' de uma tese de mestrado/doutoramento, estruturando a resposta em:\n"
    prompt += "1. Introdução geral à adesão do painel de peritos e análise dos tempos de resposta.\n"
    prompt += "2. Análise detalhada das afirmações que obtiveram consenso precoce (Ronda 1).\n"
    prompt += "3. Avaliação da dinâmica de convergência e evolução nas rondas seguintes.\n"
    prompt += "4. Integração crítica das justificações qualitativas dos peritos para explicar o posicionamento do grupo.\n"
    prompt += "5. Conclusões e contributos práticos para os cuidados de enfermagem."
    
    return prompt

def get_db_connection():
    conn = sqlite3.connect("delphi_v8.db")
    conn.execute('CREATE TABLE IF NOT EXISTS respostas (expert_id TEXT, round_num INTEGER, statement_id INTEGER, score INTEGER, justification TEXT, PRIMARY KEY (expert_id, round_num, statement_id))')
    conn.execute('CREATE TABLE IF NOT EXISTS utilizadores (expert_id TEXT PRIMARY KEY, password TEXT, must_change INTEGER DEFAULT 1)')
    conn.execute('CREATE TABLE IF NOT EXISTS afirmacoes (id INTEGER PRIMARY KEY AUTOINCREMENT, texto TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS tempos_ronda (expert_id TEXT, round_num INTEGER, start_time TEXT, duration_seconds INTEGER, PRIMARY KEY (expert_id, round_num))')
    
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM configuracoes WHERE chave='escala_max'")
    if c.fetchone()[0] == 0: c.execute("INSERT INTO configuracoes VALUES ('escala_max', '5')")
    
    c.execute("SELECT COUNT(*) FROM configuracoes WHERE chave='max_rondas'")
    if c.fetchone()[0] == 0: c.execute("INSERT INTO configuracoes VALUES ('max_rondas', '2')")
    
    c.execute("SELECT COUNT(*) FROM configuracoes WHERE chave='regra_justificacao'")
    if c.fetchone()[0] == 0: c.execute("INSERT INTO configuracoes VALUES ('regra_justificacao', 'Extremos (1 e Max)')")

    c.execute("SELECT COUNT(*) FROM configuracoes WHERE chave='ronda_ativa'")
    if c.fetchone()[0] == 0: c.execute("INSERT INTO configuracoes VALUES ('ronda_ativa', '1')")
    conn.commit()

    # Garantir que a escala configurada é sempre ímpar (se por acaso estava par, ajusta para 5)
    escala_atual = int(conn.execute("SELECT valor FROM configuracoes WHERE chave='escala_max'").fetchone()[0])
    if escala_atual not in [3, 5, 7, 9]:
        conn.execute("UPDATE configuracoes SET valor='5' WHERE chave='escala_max'")
        conn.commit()

    c.execute("SELECT COUNT(*) FROM utilizadores")
    if c.fetchone()[0] == 0:
        utilizadores_base = [
            ("P01", hash_password("codigo123"), 1), ("P02", hash_password("codigo456"), 1), 
            ("P03", hash_password("codigo789"), 1), ("P04", hash_password("codigo000"), 1), 
            ("P05", hash_password("codigo111"), 1), ("P06", hash_password("codigo222"), 1), 
            ("P07", hash_password("teste123"), 1)
        ]
        c.executemany('INSERT INTO utilizadores VALUES (?, ?, ?)', utilizadores_base)
        conn.commit()

    c.execute("SELECT COUNT(*) FROM afirmacoes")
    if c.fetchone()[0] == 0:
        afirmacoes_iniciais = [
            ("O enfermeiro deve incluir o pai como parceiro ativo no plano de cuidados de amamentação, definindo tarefas logísticas específicas desde o pré-parto.",),
            ("A consulta de preparação para a parentalidade deve reservar momentos exclusivos de treino prático dirigidos ao pai, focando-se no apoio instrumental e emocional.",),
            ("O enfermeiro deve avaliar as competências de 'trabalho de equipa parental' e promover a negociação de papéis entre o casal para prevenir a exaustão materna.",),
            ("É necessário validar o papel do pai durante a consulta de aleitamento, reconhecendo a sua necessidade de suporte e inclusão na díade mãe-bebé.",),
            ("O enfermeiro deve aplicar sistematicamente ferramentas de avaliação familiar (genograma/ecomapa) para mapear a rede de suporte e identificar potenciais influenciadores (avós/sogras).",),
            ("As sessões educativas devem promover a integração de figuras transgeracionais, clarificando mitos e alinhando conselhos práticos com a evidência científica atual.",),
            ("A intervenção de enfermagem deve capacitar as avós/sogras para atuarem como promotoras e facilitadoras da amamentação, valorizando o seu saber experiencial.",),
            ("Devem ser identificadas precocemente as pressões familiares dissonantes, atuando o enfermeiro como mediador na gestão de expectativas da família alargada.",),
            ("O enfermeiro deve realizar uma avaliação multidimensional da família (dimensões da coesão e flexibilidade) e não apenas técnica sobre a pega do bebé.",),
            ("A intervenção deve ser contínua e proativa, garantindo o seguimento desde o pré-parto até ao pós-parto, com maior intensidade nos primeiros 15 dias de vida.",),
            ("O foco da consulta deve incidir na promoção da autoeficácia materna, utilizando estratégias de resolução de problemas e treino de competências práticas.",),
            ("A prática clínica deve adotar formatos híbridos (presencial e digital) que permitam o acompanhamento contínuo e a rápida resposta a dúvidas dos pais.",),
            ("Quando a rede de apoio informal é fraca ou ausente, o enfermeiro deve intensificar o número de contactos (presenciais ou remotos) como estratégia de compensação.",),
            ("O enfermeiro deve assumir um papel de 'apoio substituto', facilitando a ligação dos casais isolados a grupos de suporte comunitário ou pares.",),
            ("O enfermeiro deve promover espaços de reflexão clínica sobre a reorganização da vida do casal, focando na partilha equitativa de tarefas domésticas.",),
            ("A literacia em saúde deve incluir estratégias de comunicação conjugal para assegurar que o apoio emocional é efetivamente percebido pelo outro elemento do casal.",),
            ("Famílias com níveis extremos de coesão (muito ligadas/aglutinadas) devem ser sinalizadas como de risco aumentado para exaustão parental no aleitamento.",),
            ("O enfermeiro deve realizar rastreio de saúde mental materna e paterna, considerando que a baixa satisfação conjugal é um preditor de abandono do AME.",),
            ("Em caso de transição para leite adaptado por motivos clínicos ou de dor, a intervenção de enfermagem deve ser empática, focada em mitigar o sentimento de falha parental.",),
            ("É responsabilidade do enfermeiro treinar técnicas de extração, conservação e gestão do leite materno antes do regresso da mãe à vida profissional.",),
            ("Os cursos de parentalidade devem substituir a componente puramente teórica por treinos de simulação (posicionamentos, manuseamento, sinais de fome).",),
            ("As intervenções de educação para a saúde devem ser personalizadas às necessidades imediatas da fase de vida do bebé, abandonando o modelo 'estanque' de aulas.",),
            ("O treino de competências de aleitamento deve ser executado até que os pais demonstrem confiança na técnica e na gestão da dor (pega correta).",),
            ("As orientações fornecidas pelos diferentes níveis de cuidados (hospital/centro de saúde) devem ser unificadas, evitando mensagens contraditórias.",)
        ]
        c.executemany("INSERT INTO afirmacoes (texto) VALUES (?)", afirmacoes_iniciais)
        conn.commit()
    return conn

def verificar_obrigatoriedade(score, escala_max, regra):
    if regra == "Extremos (1 e Max)": return score == 1 or score == escala_max
    elif regra == "Sempre obrigatória": return True
    elif regra == "Apenas notas baixas (1)": return score == 1
    elif regra == "Desativada (Opcional)": return False
    return score == 1 or score == escala_max

if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'submetido_sucesso' not in st.session_state: st.session_state.submetido_sucesso = False
if 'forcing_password_change' not in st.session_state: st.session_state.forcing_password_change = False
if 'submitted_round' not in st.session_state: st.session_state.submitted_round = 1

if st.session_state.forcing_password_change:
    st.title("Primeiro Acesso - Alteração de Palavra-Passe")
    st.info("Por razões de segurança, é obrigatório alterar a sua palavra-passe provisória antes de aceder ao estudo.")
    with st.form("form_change_pass"):
        nova_p1 = st.text_input("Nova Palavra-Passe", type="password")
        nova_p2 = st.text_input("Confirme a Nova Palavra-Passe", type="password")
        btn_alterar = st.form_submit_button("Atualizar Palavra-Passe e Entrar")
        if btn_alterar:
            if not nova_p1 or nova_p1 != nova_p2:
                st.error("As palavras-passe não coincidem ou estão vazias.")
            else:
                new_hash = hash_password(nova_p1)
                conn = get_db_connection()
                conn.execute("UPDATE utilizadores SET password = ?, must_change = 0 WHERE expert_id = ?", (new_hash, st.session_state.pending_user))
                conn.commit()
                conn.close()
                st.session_state.forcing_password_change = False
                st.session_state.logged_in = True
                st.session_state.user = st.session_state.pending_user
                st.success("Palavra-passe alterada com sucesso!")
                st.rerun()
    st.stop()

if not st.session_state.logged_in:
    st.title("Login - Estudo Delphi")
    u, c = st.text_input("ID de Perito"), st.text_input("Código de Acesso", type="password")
    if st.button("Entrar"):
        if u == "admin" and c == ADMIN_CODE:
            st.session_state.logged_in = True; st.session_state.user = "ADMIN"; st.rerun()
        else:
            conn = get_db_connection()
            row = conn.execute("SELECT password, must_change FROM utilizadores WHERE expert_id = ?", (u,)).fetchone()
            
            if row and verify_password(row[0], c, conn, u):
                if row[1] == 1:
                    st.session_state.pending_user = u
                    st.session_state.forcing_password_change = True
                    conn.close()
                    st.rerun()
                else:
                    conn.close()
                    st.session_state.logged_in = True; st.session_state.user = u; st.session_state.submetido_sucesso = False; st.rerun()
            else:
                conn.close()
                st.error("Credenciais inválidas.")
else:
    if st.session_state.user != "ADMIN":
        expert_id = st.session_state.user
        st.sidebar.title(f"Perito: {expert_id}")
        if st.sidebar.button("Logout"): 
            st.session_state.logged_in = False
            st.session_state.submetido_sucesso = False
            st.session_state.submitted_round = 1
            st.rerun()
        
        conn = get_db_connection()
        df_all = pd.read_sql_query("SELECT * FROM respostas", conn)
        df_af = pd.read_sql_query("SELECT * FROM afirmacoes ORDER BY id", conn)
        escala_max = int(conn.execute("SELECT valor FROM configuracoes WHERE chave='escala_max'").fetchone()[0])
        ponto_neutro = (escala_max + 1) // 2
        max_rondas = int(conn.execute("SELECT valor FROM configuracoes WHERE chave='max_rondas'").fetchone()[0])
        ronda_ativa = int(conn.execute("SELECT valor FROM configuracoes WHERE chave='ronda_ativa'").fetchone()[0])
        regra_just = conn.execute("SELECT valor FROM configuracoes WHERE chave='regra_justificacao'").fetchone()[0]
        escala_lista = list(range(1, escala_max + 1))
        
        rondas_feitas = df_all[df_all['expert_id'] == expert_id]['round_num'].unique()
        
        round_num = 1
        while round_num <= max_rondas:
            if round_num not in rondas_feitas:
                break
            round_num += 1
            
        if round_num > max_rondas:
            st.markdown("## 🎉 Muito obrigado pela sua participação.")
            st.info("Concluiu todas as rondas previstas para este estudo.")
            
            if st.session_state.submetido_sucesso:
                st.success(f"A sua última ronda (Ronda {st.session_state.submitted_round}) foi submetida e guardada com sucesso!")
                
            pdf_final = generate_expert_report_pdf(expert_id, conn)
            st.download_button("📄 Baixar Relatório Final (Todas as Rondas)", data=pdf_final, file_name=f"relatorio_final_{expert_id}.pdf", mime="application/pdf")
            
        elif round_num > ronda_ativa:
            st.info(f"⏳ Já concluiu as rondas disponíveis. A **Ronda {round_num}** ainda se encontra fechada pelo investigador. Por favor, aguarde que seja dada a ordem para avançar.")
            pdf_anteriores = generate_expert_report_pdf(expert_id, conn)
            st.download_button("📄 Baixar Respostas Anteriores (PDF)", data=pdf_anteriores, file_name=f"respostas_anteriores_{expert_id}.pdf", mime="application/pdf")
            
        else:
            st.header(f"Ronda {round_num}")
            if st.session_state.submetido_sucesso:
                r_msg = st.session_state.submitted_round
                st.success(f"Ronda {r_msg} submetida com sucesso!")
                pdf_submissao = generate_expert_report_pdf(expert_id, conn, specific_round=r_msg)
                st.download_button(f"Baixar comprovativo em PDF", data=pdf_submissao, file_name=f"ronda_{r_msg}_{expert_id}.pdf", mime="application/pdf")
            else:
                cursor = conn.cursor()
                cursor.execute("SELECT start_time FROM tempos_ronda WHERE expert_id=? AND round_num=?", (expert_id, round_num))
                row_tempo = cursor.fetchone()
                now_str = datetime.datetime.now().isoformat()
                if not row_tempo:
                    conn.execute("INSERT INTO tempos_ronda (expert_id, round_num, start_time, duration_seconds) VALUES (?, ?, ?, 0)", (expert_id, round_num, now_str))
                    conn.commit()
                    start_dt = datetime.datetime.now()
                else:
                    start_dt = datetime.datetime.fromisoformat(row_tempo[0])
                    
                elapsed = datetime.datetime.now() - start_dt
                mins, secs = divmod(int(elapsed.total_seconds()), 60)
                st.metric(label="⏱️ Tempo decorrido nesta ronda", value=f"{mins} min {secs} seg")
                st.divider()

                if round_num == 1:
                    st.info(f"Classifique de 1 a {escala_max} (ponto neutro: {ponto_neutro}). Regra de justificação: **{regra_just}**.")
                    with st.form("form_r1"):
                        respostas = {}
                        for _, row in df_af.iterrows():
                            idx = row['id']
                            st.markdown(f"**{row['texto']}**")
                            s = st.radio(f"Nota (ID:{idx})", escala_lista, key=f"s_{idx}", horizontal=True)
                            j = st.text_area(f"Justificação (ID:{idx})", key=f"j_{idx}")
                            
                            obr = verificar_obrigatoriedade(s, escala_max, regra_just)
                            respostas[idx] = {"score": s, "just": j, "obr": obr}
                            st.divider()
                        
                        if st.form_submit_button("Submeter Ronda 1"):
                            if any(d['obr'] and not d['just'].strip() for d in respostas.values()):
                                st.error("Atenção: Existem respostas que exigem justificação obrigatória segundo a regra configurada.")
                            else:
                                end_dt = datetime.datetime.now()
                                duration = int((end_dt - start_dt).total_seconds())
                                conn.execute("UPDATE tempos_ronda SET duration_seconds = ? WHERE expert_id = ? AND round_num = ?", (duration, expert_id, 1))
                                
                                for idx, d in respostas.items():
                                    conn.execute('INSERT OR REPLACE INTO respostas VALUES (?, ?, ?, ?, ?)', (expert_id, 1, idx, d['score'], d['just']))
                                conn.commit()
                                st.session_state.submitted_round = 1
                                st.session_state.submetido_sucesso = True
                                st.rerun()
                
                else: 
                    consensualizadas = []
                    divergencias = []
                    
                    for idx in df_af['id'].tolist():
                        alcancou_consenso = False
                        for prev_r in range(1, round_num):
                            scores_prev = df_all[(df_all['round_num'] == prev_r) & (df_all['statement_id'] == idx)]['score'].dropna()
                            if not scores_prev.empty:
                                if calcular_consenso_percentual(scores_prev, escala_max) >= 80.0:
                                    alcancou_consenso = True
                                    break
                        
                        if alcancou_consenso:
                            consensualizadas.append(idx)
                        else:
                            divergencias.append(idx)
                    
                    if not divergencias:
                        st.success(f"Parabéns! Todas as afirmações atingiram consenso nas rondas anteriores. Não existem pendências.")
                        pdf_completo = generate_expert_report_pdf(expert_id, conn)
                        st.download_button("📄 Baixar Relatório Completo", data=pdf_completo, file_name=f"relatorio_completo_{expert_id}.pdf", mime="application/pdf")
                    else:
                        st.info(f"Nesta Ronda {round_num}, as afirmações consensuais estão assinaladas. Responda apenas às {len(divergencias)} afirmações pendentes. Regra de justificação: **{regra_just}**.")
                        with st.form(f"form_r{round_num}"):
                            respostas_rn = {}
                            
                            for idx in df_af['id'].tolist():
                                texto_af = df_af[df_af['id'] == idx]['texto'].values[0]
                                
                                if idx in consensualizadas:
                                    st.markdown(f"### {texto_af}")
                                    st.success("✅ Afirmação consensualizada")
                                    st.divider()
                                else:
                                    ronda_anterior = round_num - 1
                                    df_ant = df_all[df_all['round_num'] == ronda_anterior]
                                    
                                    row_antigo = df_ant[(df_ant['expert_id'] == expert_id) & (df_ant['statement_id'] == idx)]
                                    voto_antigo = row_antigo['score'].values[0] if not row_antigo.empty else 1
                                    just_antiga = row_antigo['justification'].values[0] if not row_antigo.empty else ""
                                    
                                    scores_item_ant = df_ant[df_ant['statement_id'] == idx]['score'].dropna()
                                    media_grupo = scores_item_ant.mean() if not scores_item_ant.empty else 0.0
                                    
                                    outros_votos = df_ant[(df_ant['statement_id'] == idx) & (df_ant['expert_id'] != expert_id)]['score'].tolist()
                                    outros_str = ", ".join(map(str, outros_votos)) if outros_votos else "Sem registos"
                                    
                                    st.markdown(f"### {texto_af}")
                                    st.markdown(f"👤 **O seu voto anterior:** `{voto_antigo}` | 👥 **Média do grupo:** `{media_grupo:.2f}`")
                                    st.markdown(f"👥 **Respostas dos restantes peritos:** `{outros_str}`")
                                    
                                    # Verificar se a média do grupo está no ponto neutro (ex: 3 numa escala de 5, 4 numa escala de 7)
                                    is_media_neutra = (round(media_grupo) == ponto_neutro)
                                    
                                    quer_manter = "Sim"
                                    if is_media_neutra:
                                        quer_manter = st.radio(
                                            f"O conjunto de peritos classificou esta afirmação com não relevante. Quer manter a sua resposta? (ID:{idx})",
                                            ["Sim", "Não"],
                                            key=f"qm_{idx}",
                                            horizontal=True
                                        )
                                    
                                    if quer_manter == "Sim":
                                        index_voto = int(voto_antigo) - 1 if int(voto_antigo) in escala_lista else 0
                                        s = st.radio(f"Novo voto (ID:{idx})", escala_lista, key=f"sr_{idx}", horizontal=True, index=index_voto)
                                        j = st.text_area(f"Nova justificação (ID:{idx})", value=just_antiga, key=f"jr_{idx}")
                                        
                                        obr = verificar_obrigatoriedade(s, escala_max, regra_just)
                                        respostas_rn[idx] = {"score": s, "just": j, "obr": obr}
                                    else:
                                        # Se escolheu "Não", mantém a resposta anterior sem mostrar a escala
                                        st.info("🔒 Resposta anterior mantida (escala oculta por opção de não relevância).")
                                        respostas_rn[idx] = {"score": int(voto_antigo), "just": just_antiga, "obr": False}
                                        
                                    st.divider()
                                
                            if st.form_submit_button(f"Submeter Ronda {round_num}"):
                                if any(d['obr'] and not d['just'].strip() for d in respostas_rn.values()):
                                    st.error("Atenção: Existem respostas que exigem justificação obrigatória segundo a regra configurada.")
                                else:
                                    end_dt = datetime.datetime.now()
                                    duration = int((end_dt - start_dt).total_seconds())
                                    conn.execute("UPDATE tempos_ronda SET duration_seconds = ? WHERE expert_id = ? AND round_num = ?", (duration, expert_id, round_num))
                                    
                                    for idx, d in respostas_rn.items():
                                        conn.execute('INSERT OR REPLACE INTO respostas VALUES (?, ?, ?, ?, ?)', (expert_id, round_num, idx, d['score'], d['just']))
                                    conn.commit()
                                    st.session_state.submitted_round = round_num
                                    st.session_state.submetido_sucesso = True
                                    st.rerun()
        conn.close()
    else:
        st.title("Painel de Investigador")
        st.sidebar.button("Logout", on_click=lambda: st.session_state.update(logged_in=False))
        
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["📈 Módulo Estatístico", "📊 Respostas Brutas", "👥 Utilizadores", "📝 Afirmações", "⚙️ Configurações"])
        conn = get_db_connection()
        escala_max = int(conn.execute("SELECT valor FROM configuracoes WHERE chave='escala_max'").fetchone()[0])
        ponto_neutro = (escala_max + 1) // 2
        max_rondas = int(conn.execute("SELECT valor FROM configuracoes WHERE chave='max_rondas'").fetchone()[0])
        ronda_ativa = int(conn.execute("SELECT valor FROM configuracoes WHERE chave='ronda_ativa'").fetchone()[0])
        regra_just = conn.execute("SELECT valor FROM configuracoes WHERE chave='regra_justificacao'").fetchone()[0]
        
        with tab1:
            st.subheader("Matriz Estatística por Ronda")
            
            df_all_rep = pd.read_sql_query("SELECT * FROM respostas", conn)
            df_users_rep = pd.read_sql_query("SELECT * FROM utilizadores", conn)
            df_af_rep = pd.read_sql_query("SELECT * FROM afirmacoes", conn)
            df_tempos_rep = pd.read_sql_query("SELECT * FROM tempos_ronda", conn)
            
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                pdf_global_bytes = generate_admin_report_pdf(df_all_rep, df_users_rep, df_af_rep, escala_max, df_tempos_rep)
                st.download_button(
                    label="📄 Baixar Relatório Global do Estudo (PDF)",
                    data=pdf_global_bytes,
                    file_name="relatorio_global_estudo_delphi.pdf",
                    mime="application/pdf"
                )
            st.divider()

            st.subheader("⏱️ Tempos Médios de Resposta por Ronda")
            if not df_tempos_rep.empty:
                t_resumo = df_tempos_rep.groupby('round_num')['duration_seconds'].mean().reset_index()
                t_resumo['Tempo Médio'] = t_resumo['duration_seconds'].apply(lambda x: f"{int(x//60)} min {int(x%60)} seg")
                t_resumo.columns = ['Ronda', 'Segundos Médios', 'Tempo Médio Formatado']
                st.dataframe(t_resumo[['Ronda', 'Tempo Médio Formatado']], hide_index=True, use_container_width=True)
            else:
                st.info("Ainda não existem registos de tempos.")
            st.divider()

            with st.expander("🤖 Assistente de Análise Científica para Tese (Copiar para IA)", expanded=False):
                st.markdown("Copie o texto estruturado abaixo e cole-o no **ChatGPT** ou **Gemini** para obter uma interpretação crítica automática dos seus dados.")
                prompt_ia = generate_ai_analysis_prompt(conn, escala_max)
                st.text_area("Prompt Académico Pronto a Copiar:", value=prompt_ia, height=250)
            st.divider()

            df_all = df_all_rep
            if df_all.empty:
                st.warning("Ainda não existem respostas no estudo para gerar gráficos ou matrizes.")
            else:
                todas_rondas = sorted(df_all['round_num'].unique())
                for r in todas_rondas:
                    st.markdown(f"#### Resultados da RONDA {r}")
                    df_r = df_all[df_all['round_num'] == r]
                    pivot = df_r.pivot(index='statement_id', columns='expert_id', values='score')
                    stats = pd.DataFrame(index=pivot.index)
                    stats['Média'] = pivot.mean(axis=1).round(2)
                    stats['Desv. Padrão'] = pivot.std(axis=1).round(2)
                    
                    stats['Índice Consenso (%)'] = pivot.apply(lambda row: calcular_consenso_percentual(row.dropna(), escala_max), axis=1).round(1)
                    pivot.columns = [f"Perito {col}" for col in pivot.columns]
                    df_final = pd.concat([pivot, stats], axis=1)
                    df_final.index = [f"Afirmação {i}" for i in df_final.index]
                    
                    st.dataframe(df_final, use_container_width=True)
                    csv_matriz = df_final.to_csv(index_label="Afirmação").encode('utf-8')
                    st.download_button(f"Exportar Matriz Ronda {r} (Excel/CSV)", data=csv_matriz, file_name=f'matriz_estatistica_ronda_{r}.csv', mime='text/csv')
                
                st.divider()
                st.subheader("📈 Evolução Gráfica do Estudo")
                dados_graficos = []
                for r in todas_rondas:
                    df_r = df_all[df_all['round_num'] == r]
                    for stmt in df_r['statement_id'].unique():
                        notas = df_r[df_r['statement_id'] == stmt]['score'].dropna()
                        if len(notas) > 0:
                            media = notas.mean()
                            cons = calcular_consenso_percentual(notas, escala_max)
                            dados_graficos.append({"Ronda": f"Ronda {r}", "Afirmação": f"Afirmação {stmt}", "Média": media, "Consenso (%)": cons})
                
                df_graf = pd.DataFrame(dados_graficos)
                if not df_graf.empty:
                    st.markdown("**1. Quantidade de Afirmações com Consenso Alcançado (≥80%) por Ronda**")
                    cons_alcancado = df_graf[df_graf['Consenso (%)'] >= 80].groupby('Ronda').size()
                    if not cons_alcancado.empty: st.bar_chart(cons_alcancado)
                    else: st.info("Nenhuma afirmação atingiu 80% de consenso até ao momento.")
                    
                    colA, colB = st.columns(2)
                    with colA:
                        st.markdown("**2. Evolução da Média (por Afirmação)**")
                        st.line_chart(df_graf.pivot(index='Ronda', columns='Afirmação', values='Média'))
                    with colB:
                        st.markdown("**3. Evolução do Índice de Consenso % (por Afirmação)**")
                        st.line_chart(df_graf.pivot(index='Ronda', columns='Afirmação', values='Consenso (%)'))

        with tab2:
            st.subheader("Registo Bruto de Respostas e Tempos")
            df_all = pd.read_sql_query("SELECT * FROM respostas", conn)
            df_t = pd.read_sql_query("SELECT * FROM tempos_ronda", conn)
            st.markdown("**Respostas:**")
            st.dataframe(df_all, use_container_width=True)
            st.markdown("**Tempos de Resposta por Perito:**")
            st.dataframe(df_t, use_container_width=True)
            if not df_all.empty:
                st.download_button("Exportar Excel (Dados Brutos)", data=df_all.to_csv(index=False).encode('utf-8'), file_name='dados_estudo_brutos.csv', mime='text/csv')
                
        with tab3:
            st.subheader("Utilizadores Registados")
            df_users = pd.read_sql_query("SELECT expert_id as 'ID de Perito' FROM utilizadores", conn)
            st.dataframe(df_users, use_container_width=True)
            
            col1, col2 = st.columns(2)
            with col1:
                with st.form("form_add_user"):
                    novo_id = st.text_input("Novo ID (ex: P08)")
                    nova_pass = st.text_input("Código de Acesso")
                    if st.form_submit_button("Adicionar Perito"):
                        if novo_id and nova_pass:
                            try:
                                hashed_nova_pass = hash_password(nova_pass)
                                conn.execute("INSERT INTO utilizadores VALUES (?, ?, 1)", (novo_id, hashed_nova_pass))
                                conn.commit()
                                st.success(f"Criado o utilizador {novo_id} com password encriptada e pendente de alteração!")
                                st.rerun()
                            except: st.error("O ID já existe.")
            with col2:
                with st.form("form_del_user"):
                    del_id = st.selectbox("Selecione o ID a remover", df_users['ID de Perito'].tolist() if not df_users.empty else [])
                    if st.form_submit_button("Apagar Perito"):
                        if del_id: conn.execute("DELETE FROM utilizadores WHERE expert_id=?", (del_id,)); conn.commit(); st.success("Removido!"); st.rerun()
            
        with tab4:
            st.subheader("Gerir Afirmações")
            df_af = pd.read_sql_query("SELECT * FROM afirmacoes", conn)
            st.dataframe(df_af, hide_index=True, use_container_width=True)
            
            with st.form("form_add_af"):
                nova_af = st.text_area("Texto da nova afirmação")
                if st.form_submit_button("Adicionar Afirmação"):
                    if nova_af.strip(): conn.execute("INSERT INTO afirmacoes (texto) VALUES (?)", (nova_af,)); conn.commit(); st.success("Adicionada!"); st.rerun()
            
            with st.form("form_del_af"):
                del_af_id = st.selectbox("ID da afirmação a apagar", df_af['id'].tolist() if not df_af.empty else [])
                if st.form_submit_button("Apagar Afirmação Selecionada"):
                    conn.execute("DELETE FROM afirmacoes WHERE id=?", (del_af_id,)); conn.commit(); st.success("Apagada!"); st.rerun()

        with tab5:
            st.subheader("Configurações e Controlo de Rondas")
            
            st.markdown("### Controlo do Fluxo de Rondas")
            st.info(f"O estudo encontra-se atualmente a decorrer na **Ronda {ronda_ativa}** (de um total de {max_rondas} rondas configuradas).")
            if ronda_ativa < max_rondas:
                if st.button("🚀 Dar ordem para avançar para a Ronda Seguinte"):
                    conn.execute("UPDATE configuracoes SET valor=? WHERE chave='ronda_ativa'", (str(ronda_ativa + 1),))
                    conn.commit()
                    st.success(f"Estudo avançado com sucesso para a Ronda {ronda_ativa + 1}!")
                    st.rerun()
            else:
                st.warning("O estudo já atingiu o número máximo de rondas configurado.")
            st.divider()

            c1, c2, c3 = st.columns(3)
            with c1:
                with st.form("form_escala"):
                    st.markdown("**Escala Máxima (Apenas Ímpares)**")
                    escalas_impares = [3, 5, 7, 9]
                    idx_escala = escalas_impares.index(escala_max) if escala_max in escalas_impares else 1
                    nova_escala = st.selectbox("Valor máximo", escalas_impares, index=idx_escala)
                    if st.form_submit_button("Atualizar Escala"):
                        conn.execute("UPDATE configuracoes SET valor=? WHERE chave='escala_max'", (str(nova_escala),))
                        conn.commit()
                        st.success("Escala atualizada com sucesso!")
                        st.rerun()
            with c2:
                with st.form("form_rondas"):
                    st.markdown("Total de Rondas")
                    novas_rondas = st.number_input("Nº de Rondas", min_value=1, max_value=5, value=max_rondas)
                    if st.form_submit_button("Atualizar Rondas"):
                        conn.execute("UPDATE configuracoes SET valor=? WHERE chave='max_rondas'", (str(novas_rondas),)); conn.commit(); st.success("Atualizadas!"); st.rerun()
            with c3:
                with st.form("form_regra_just"):
                    st.markdown("**Regra de Justificação**")
                    opcoes_regra = ["Extremos (1 e Max)", "Sempre obrigatória", "Apenas notas baixas (1)", "Desativada (Opcional)"]
                    idx_regra = opcoes_regra.index(regra_just) if regra_just in opcoes_regra else 0
                    nova_regra = st.selectbox("Exigir justificação em:", opcoes_regra, index=idx_regra)
                    if st.form_submit_button("Atualizar Regra"):
                        conn.execute("UPDATE configuracoes SET valor=? WHERE chave='regra_justificacao'", (nova_regra,)); conn.commit(); st.success("Atualizada!"); st.rerun()
                    
        conn.close()
