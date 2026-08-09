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
    notas = notas[notas > 0] # Ignorar valores de exclusão (0)
    if len(notas) == 0: return 0.0
    ponto_neutro = (escala_max + 1) // 2
    cons_acc = (notas >= escala_max - 1).mean()
    cons_rej = (notas <= 2).mean() if escala_max > 3 else (notas == 1).mean()
    cons_neut = (notas == ponto_neutro).mean()
    return max(cons_acc, cons_rej, cons_neut) * 100

def generate_expert_report_pdf(expert_id, conn, specific_round=None):
    pdf = FPDF()
    pdf.add_page()
    df_res = pd.read_sql_query("SELECT * FROM respostas WHERE expert_id=?", conn, params=(expert_id,))
    df_af = pd.read_sql_query("SELECT * FROM afirmacoes", conn)
    df_t = pd.read_sql_query("SELECT * FROM tempos_ronda WHERE expert_id=?", conn, params=(expert_id,))
    
    titulo = "Relatorio Completo" if specific_round is None else f"Relatorio Ronda {specific_round}"
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, txt=safe_txt(titulo), ln=True, align='C')
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, txt=safe_txt(f"Perito: {expert_id}"), ln=True)
    pdf.ln(5)
    
    rondas = [specific_round] if specific_round else sorted(df_res['round_num'].unique())
    for r in rondas:
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 10, txt=safe_txt(f"--- RONDA {r} ---"), ln=True)
        t_row = df_t[df_t['round_num'] == r]
        if not t_row.empty:
            mins, secs = divmod(int(t_row.iloc[0]['duration_seconds']), 60)
            pdf.set_font("Arial", 'I', 10)
            pdf.cell(0, 6, txt=safe_txt(f"Tempo: {mins}m {secs}s"), ln=True)
        df_r = df_res[df_res['round_num'] == r]
        for _, row in df_r.iterrows():
            af_row = df_af[df_af['id'] == row['statement_id']]
            texto_af = af_row['texto'].values[0] if not af_row.empty else "Afirmacao removida"
            pdf.set_font("Arial", 'B', 10)
            pdf.multi_cell(0, 6, txt=safe_txt(f"Afirmacao ID {row['statement_id']}: {texto_af}"))
            pdf.set_font("Arial", size=10)
            nota_str = row['score'] if row['score'] > 0 else 'Não relevante para si (Excluída)'
            pdf.multi_cell(0, 6, txt=safe_txt(f"Nota: {nota_str} | Just: {row['justification'] if row['justification'] else 'N/A'}"))
            pdf.ln(3)
        pdf.ln(5)
    return pdf.output(dest='S').encode('latin-1')

def generate_admin_report_pdf(df_respostas, df_users, df_afirmacoes, escala_max, df_tempos):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, txt=safe_txt("Relatorio Global"), ln=True, align='C')
    pdf.set_font("Arial", size=11)
    pdf.cell(0, 8, txt=safe_txt(f"Peritos: {len(df_users)} | Afirmacoes: {len(df_afirmacoes)}"), ln=True)
    pdf.ln(10)
    if not df_respostas.empty:
        for r in sorted(df_respostas['round_num'].unique()):
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 8, txt=safe_txt(f"--- RONDA {r} ---"), ln=True)
            df_r = df_respostas[df_respostas['round_num'] == r]
            pivot = df_r.pivot(index='statement_id', columns='expert_id', values='score')
            for idx, row in pivot.iterrows():
                notas = row[row > 0].dropna()
                if len(notas) > 0:
                    cons = calcular_consenso_percentual(notas, escala_max)
                    pdf.multi_cell(0, 6, txt=safe_txt(f"Afirmacao {idx}: Media={notas.mean():.2f} | Consenso={cons:.1f}%"))
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
    prompt += "- Limiar de Consenso definido: >= 80% das respostas nos valores mais altos, mais baixos ou neutros da escala.\n\n"
    
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
                scores = df_item[df_item['score'] > 0]['score'].dropna()
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
    conn = sqlite3.connect("delphi_v20.db")
    conn.execute('CREATE TABLE IF NOT EXISTS respostas (expert_id TEXT, round_num INTEGER, statement_id INTEGER, score INTEGER, justification TEXT, PRIMARY KEY (expert_id, round_num, statement_id))')
    conn.execute('CREATE TABLE IF NOT EXISTS utilizadores (expert_id TEXT PRIMARY KEY, password TEXT, must_change INTEGER DEFAULT 1)')
    conn.execute('CREATE TABLE IF NOT EXISTS afirmacoes (id INTEGER PRIMARY KEY AUTOINCREMENT, texto TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS tempos_ronda (expert_id TEXT, round_num INTEGER, start_time TEXT, duration_seconds INTEGER, PRIMARY KEY (expert_id, round_num))')
    c = conn.cursor()
    for cfg in [('escala_max', '5'), ('max_rondas', '2'), ('regra_justificacao', 'Extremos (1 e Max)'), ('ronda_ativa', '1')]:
        c.execute("INSERT OR IGNORE INTO configuracoes VALUES (?, ?)", cfg)
    conn.commit()
    return conn

def verificar_obrigatoriedade(score, escala_max, regra):
    if score == 0: return False
    if regra == "Extremos (1 e Max)": return score == 1 or score == escala_max
    elif regra == "Sempre obrigatória": return True
    elif regra == "Apenas notas baixas (1)": return score == 1
    elif regra == "Desativada (Opcional)": return False
    return score == 1 or score == escala_max

if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'submetido_sucesso' not in st.session_state: st.session_state.submetido_sucesso = False
if 'forcing_password_change' not in st.session_state: st.session_state.forcing_password_change = False

if st.session_state.forcing_password_change:
    st.title("Primeiro Acesso - Nova Password")
    with st.form("form_change_pass"):
        nova_p1 = st.text_input("Nova Password", type="password")
        nova_p2 = st.text_input("Confirme Nova Password", type="password")
        if st.form_submit_button("Atualizar e Entrar"):
            if nova_p1 and nova_p1 == nova_p2:
                conn = get_db_connection()
                conn.execute("UPDATE utilizadores SET password = ?, must_change = 0 WHERE expert_id = ?", (hash_password(nova_p1), st.session_state.pending_user))
                conn.commit(); conn.close()
                st.session_state.forcing_password_change = False; st.session_state.logged_in = True; st.session_state.user = st.session_state.pending_user; st.rerun()
            else: st.error("Erro na password.")
    st.stop()

if not st.session_state.logged_in:
    st.title("Login - Estudo Delphi")
    u, c = st.text_input("ID de Perito"), st.text_input("Código", type="password")
    if st.button("Entrar"):
        if u == "admin" and c == ADMIN_CODE: st.session_state.logged_in = True; st.session_state.user = "ADMIN"; st.rerun()
        else:
            conn = get_db_connection()
            row = conn.execute("SELECT password, must_change FROM utilizadores WHERE expert_id = ?", (u,)).fetchone()
            if row and verify_password(row[0], c, conn, u):
                if row[1] == 1: st.session_state.pending_user = u; st.session_state.forcing_password_change = True; conn.close(); st.rerun()
                else: conn.close(); st.session_state.logged_in = True; st.session_state.user = u; st.rerun()
            else: conn.close(); st.error("Credenciais inválidas.")
else:
    if st.session_state.user != "ADMIN":
        expert_id = st.session_state.user
        st.sidebar.title(f"Perito: {expert_id}")
        if st.sidebar.button("Logout"): 
            st.session_state.logged_in = False
            st.session_state.submetido_sucesso = False
            st.rerun()
        
        conn = get_db_connection()
        escala_max = int(conn.execute("SELECT valor FROM configuracoes WHERE chave='escala_max'").fetchone()[0])
        ponto_neutro = (escala_max + 1) // 2
        max_rondas = int(conn.execute("SELECT valor FROM configuracoes WHERE chave='max_rondas'").fetchone()[0])
        ronda_ativa = int(conn.execute("SELECT valor FROM configuracoes WHERE chave='ronda_ativa'").fetchone()[0])
        regra_just = conn.execute("SELECT valor FROM configuracoes WHERE chave='regra_justificacao'").fetchone()[0]
        escala_lista = list(range(1, escala_max + 1))
        
        rondas_feitas = [r[0] for r in conn.execute("SELECT DISTINCT round_num FROM respostas WHERE expert_id = ?", (expert_id,)).fetchall()]
        round_num = 1
        while round_num <= max_rondas:
            if round_num not in rondas_feitas: break
            round_num += 1
            
        if st.session_state.submetido_sucesso:
            st.success(f"A sua submissão da Ronda {st.session_state.submitted_round} foi guardada com sucesso!")
            pdf_submissao = generate_expert_report_pdf(expert_id, conn, specific_round=st.session_state.submitted_round)
            st.download_button("📄 Baixar comprovativo em PDF", data=pdf_submissao, file_name=f"ronda_{st.session_state.submitted_round}_{expert_id}.pdf", mime="application/pdf")
            st.divider()
            st.info("Pode continuar no sistema para verificar se a ronda seguinte já se encontra disponível.")
            if st.button("Continuar ➡️"):
                st.session_state.submetido_sucesso = False
                st.rerun()

        elif round_num > max_rondas:
            st.markdown("## 🎉 Muito obrigado pela sua participação.")
            st.info("Concluiu todas as rondas previstas para este estudo.")
            pdf_final = generate_expert_report_pdf(expert_id, conn)
            st.download_button("📄 Baixar Relatório Final (Todas as Rondas)", data=pdf_final, file_name=f"relatorio_final_{expert_id}.pdf", mime="application/pdf")
        
        elif round_num > ronda_ativa:
            st.warning(f"⏳ Já concluiu as rondas disponíveis. A **Ronda {round_num}** ainda se encontra fechada pelo investigador.")
            pdf_anteriores = generate_expert_report_pdf(expert_id, conn)
            st.download_button("📄 Baixar Respostas Anteriores (PDF)", data=pdf_anteriores, file_name=f"respostas_anteriores_{expert_id}.pdf", mime="application/pdf")
            st.divider()
            if st.button("🔄 Verificar se a nova Ronda já abriu"):
                st.rerun()
                
        else:
            st.header(f"Ronda {round_num}")
            cursor = conn.cursor()
            cursor.execute("SELECT start_time FROM tempos_ronda WHERE expert_id=? AND round_num=?", (expert_id, round_num))
            row_tempo = cursor.fetchone()
            if not row_tempo:
                conn.execute("INSERT INTO tempos_ronda (expert_id, round_num, start_time, duration_seconds) VALUES (?, ?, ?, 0)", (expert_id, round_num, datetime.datetime.now().isoformat()))
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
                    df_af = pd.read_sql_query("SELECT * FROM afirmacoes", conn)
                    if df_af.empty:
                        st.warning("Ainda não existem afirmações inseridas no estudo pelo investigador.")
                    else:
                        for _, row in df_af.iterrows():
                            idx = row['id']
                            st.markdown(f"**{row['texto']}**")
                            s = st.radio(f"Nota (ID:{idx})", escala_lista, key=f"s_{idx}", horizontal=True)
                            j = st.text_area(f"Justificação (ID:{idx})", key=f"j_{idx}")
                            obr = verificar_obrigatoriedade(s, escala_max, regra_just)
                            respostas[idx] = {"score": s, "just": j, "obr": obr}
                            st.divider()
                        
                    if st.form_submit_button("Submeter Ronda 1"):
                        if df_af.empty:
                            st.error("Não há afirmações para submeter.")
                        elif any(d['obr'] and not d['just'].strip() for d in respostas.values()):
                            st.error("Atenção: Existem respostas que exigem justificação obrigatória.")
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
                df_all_r = pd.read_sql_query("SELECT * FROM respostas", conn)
                df_af = pd.read_sql_query("SELECT * FROM afirmacoes ORDER BY id", conn)
                consensualizadas = []
                divergencias = []
                
                for idx in df_af['id'].tolist():
                    alcancou_consenso = False
                    for prev_r in range(1, round_num):
                        scores_prev = df_all_r[(df_all_r['round_num'] == prev_r) & (df_all_r['statement_id'] == idx) & (df_all_r['score'] > 0)]['score'].dropna()
                        if not scores_prev.empty:
                            if calcular_consenso_percentual(scores_prev, escala_max) >= 80.0:
                                alcancou_consenso = True
                                break
                    if alcancou_consenso: consensualizadas.append(idx)
                    else: divergencias.append(idx)
                
                if not divergencias:
                    st.success("Parabéns! Todas as afirmações atingiram consenso nas rondas anteriores.")
                    pdf_completo = generate_expert_report_pdf(expert_id, conn)
                    st.download_button("📄 Baixar Relatório Completo", data=pdf_completo, file_name=f"relatorio_completo_{expert_id}.pdf", mime="application/pdf")
                else:
                    st.info(f"Nesta Ronda {round_num}, responda às afirmações pendentes. Regra de justificação: **{regra_just}**.")
                    
                    # SEM FORMULÁRIO (st.form) para permitir interatividade em tempo real e reações instantâneas
                    respostas_rn = {}
                    for _, row in df_af.iterrows():
                        idx = row['id']
                        texto_af = row['texto']
                        
                        if idx in consensualizadas:
                            st.markdown(f"### {texto_af}")
                            st.success("✅ Afirmação consensualizada")
                            st.divider()
                        else:
                            ronda_anterior = round_num - 1
                            df_ant = df_all_r[df_all_r['round_num'] == ronda_anterior]
                            
                            row_antigo = df_ant[(df_ant['expert_id'] == expert_id) & (df_ant['statement_id'] == idx)]
                            voto_antigo = row_antigo['score'].values[0] if not row_antigo.empty else 1
                            just_antiga = row_antigo['justification'].values[0] if not row_antigo.empty else ""
                            
                            if int(voto_antigo) == 0:
                                st.markdown(f"### {texto_af}")
                                st.warning("🚫 Não relevante para si.")
                                st.divider()
                                respostas_rn[idx] = {"score": 0, "just": just_antiga, "obr": False}
                                continue
                            
                            scores_item_ant = df_ant[(df_ant['statement_id'] == idx) & (df_ant['score'] > 0)]['score'].dropna()
                            media_grupo = scores_item_ant.mean() if not scores_item_ant.empty else 0.0
                            outros_votos = df_ant[(df_ant['statement_id'] == idx) & (df_ant['expert_id'] != expert_id) & (df_ant['score'] > 0)]['score'].tolist()
                            outros_str = ", ".join(map(str, outros_votos)) if outros_votos else "Sem registos"
                            
                            st.markdown(f"### {texto_af}")
                            st.markdown(f"👤 **O seu voto anterior:** `{voto_antigo}` | 👥 **Média do grupo:** `{media_grupo:.2f}`")
                            st.markdown(f"👥 **Respostas dos restantes peritos:** `{outros_str}`")
                            
                            is_voto_neutro = (int(voto_antigo) == ponto_neutro)
                            
                            if is_voto_neutro:
                                quer_manter = st.radio(
                                    f"Classificou esta afirmação como não relevante. Quer manter a sua resposta anterior? (ID:{idx})", 
                                    ["Sim", "Não"], 
                                    key=f"qm_{idx}", 
                                    horizontal=True, 
                                    index=None
                                )
                                
                                if quer_manter is None:
                                    st.warning("⚠️ Escolha 'Sim' ou 'Não' na pergunta acima para poder avançar.")
                                    respostas_rn[idx] = {"score": None, "just": "", "obr": False}
                                elif quer_manter == "Sim":
                                    st.info("🚫 Não relevante para si.")
                                    respostas_rn[idx] = {"score": 0, "just": just_antiga, "obr": False}
                                else: # Se selecionar "Não", abre a escala instantaneamente em tempo real
                                    index_voto = int(voto_antigo) - 1 if (voto_antigo > 0 and int(voto_antigo) in escala_lista) else (ponto_neutro - 1)
                                    s = st.radio(f"Novo voto (ID:{idx})", escala_lista, key=f"sr_{idx}", horizontal=True, index=index_voto)
                                    j = st.text_area(f"Nova justificação (ID:{idx})", value=just_antiga, key=f"jr_{idx}")
                                    obr = verificar_obrigatoriedade(s, escala_max, regra_just)
                                    respostas_rn[idx] = {"score": s, "just": j, "obr": obr}
                            else:
                                index_voto = int(voto_antigo) - 1 if (voto_antigo > 0 and int(voto_antigo) in escala_lista) else (ponto_neutro - 1)
                                s = st.radio(f"Novo voto (ID:{idx})", escala_lista, key=f"sr_{idx}", horizontal=True, index=index_voto)
                                j = st.text_area(f"Nova justificação (ID:{idx})", value=just_antiga, key=f"jr_{idx}")
                                obr = verificar_obrigatoriedade(s, escala_max, regra_just)
                                respostas_rn[idx] = {"score": s, "just": j, "obr": obr}
                            st.divider()
                            
                    if st.button(f"Submeter Ronda {round_num}"):
                        if any(d['score'] is None for d in respostas_rn.values()):
                            st.error("Atenção: Tem de escolher 'Sim' ou 'Não' nas afirmações assinaladas a amarelo.")
                        elif any(d['obr'] and not d['just'].strip() for d in respostas_rn.values()):
                            st.error("Atenção: Existem respostas que exigem justificação obrigatória.")
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
        
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📈 Módulo Estatístico", "📊 Respostas Brutas", "👥 Utilizadores", "📝 Afirmações", "⚙️ Configurações", "👁️ Visão de Perito"])
        conn = get_db_connection()
        escala_max = int(conn.execute("SELECT valor FROM configuracoes WHERE chave='escala_max'").fetchone()[0])
        max_rondas = int(conn.execute("SELECT valor FROM configuracoes WHERE chave='max_rondas'").fetchone()[0])
        ronda_ativa = int(conn.execute("SELECT valor FROM configuracoes WHERE chave='ronda_ativa'").fetchone()[0])
        regra_just = conn.execute("SELECT valor FROM configuracoes WHERE chave='regra_justificacao'").fetchone()[0]
        
        with tab1:
            st.subheader("Matriz Estatística por Ronda")
            df_all_rep = pd.read_sql_query("SELECT * FROM respostas", conn)
            df_users_rep = pd.read_sql_query("SELECT * FROM utilizadores", conn)
            df_af_rep = pd.read_sql_query("SELECT * FROM afirmacoes", conn)
            df_tempos_rep = pd.read_sql_query("SELECT * FROM tempos_ronda", conn)
            
            if not df_all_rep.empty and not df_af_rep.empty:
                df_r_atual = df_all_rep[df_all_rep['round_num'] == ronda_ativa]
                if not df_r_atual.empty:
                    todas_consensualizadas = True
                    for stmt_id in df_af_rep['id'].tolist():
                        notas_stmt = df_r_atual[(df_r_atual['statement_id'] == stmt_id) & (df_r_atual['score'] > 0)]['score'].dropna()
                        if len(notas_stmt) == 0 or calcular_consenso_percentual(notas_stmt, escala_max) < 80.0:
                            todas_consensualizadas = False
                            break
                    if todas_consensualizadas:
                        st.success("🌟 Todas as afirmações atingiram o limiar de consenso (≥80%) nesta ronda!")
                        if st.button("🏁 Concluir Estudo Antecipadamente (Atingido Consenso Total)"):
                            conn.execute("UPDATE configuracoes SET valor=? WHERE chave='max_rondas'", (str(ronda_ativa),))
                            conn.commit()
                            st.success("Estudo concluído antecipadamente com sucesso!")
                            st.rerun()

            col_b1, col_b2 = st.columns(2)
            with col_b1:
                pdf_global_bytes = generate_admin_report_pdf(df_all_rep, df_users_rep, df_af_rep, escala_max, df_tempos_rep)
                st.download_button("📄 Baixar Relatório Global do Estudo (PDF)", data=pdf_global_bytes, file_name="relatorio_global_estudo_delphi.pdf", mime="application/pdf")
            with col_b2:
                df_completo_export = pd.read_sql_query("""
                    SELECT r.expert_id as 'ID Perito', r.round_num as 'Ronda', r.statement_id as 'ID Afirmação', 
                           a.texto as 'Texto Afirmação', r.score as 'Nota', r.justification as 'Justificação' 
                    FROM respostas r 
                    JOIN afirmacoes a ON r.statement_id = a.id
                """, conn)
                if not df_completo_export.empty:
                    st.download_button(
                        "📥 Exportar Todas as Rondas e Justificações (Excel/CSV)",
                        data=df_completo_export.to_csv(index=False).encode('utf-8'),
                        file_name="estudo_delphi_todas_rondas_justificacoes.csv",
                        mime="text/csv"
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
                st.markdown("Copie o texto estruturado abaixo e cole-o no **ChatGPT** ou **Gemini** para obter uma interpretação crítica automática.")
                prompt_ia = generate_ai_analysis_prompt(conn, escala_max)
                st.text_area("Prompt Académico Pronto a Copiar:", value=prompt_ia, height=250)
            st.divider()

            if df_all_rep.empty:
                st.warning("Ainda não existem respostas no estudo para gerar gráficos ou matrizes.")
            else:
                for r in sorted(df_all_rep['round_num'].unique()):
                    st.markdown(f"#### Resultados da RONDA {r}")
                    df_r = df_all_rep[df_all_rep['round_num'] == r]
                    pivot = df_r.pivot(index='statement_id', columns='expert_id', values='score')
                    stats = pd.DataFrame(index=pivot.index)
                    stats['Média'] = pivot[pivot > 0].mean(axis=1).round(2)
                    stats['Desv. Padrão'] = pivot[pivot > 0].std(axis=1).round(2)
                    stats['Índice Consenso (%)'] = pivot.apply(lambda row: calcular_consenso_percentual(row.dropna(), escala_max), axis=1).round(1)
                    pivot.columns = [f"Perito {col}" for col in pivot.columns]
                    df_final = pd.concat([pivot, stats], axis=1)
                    df_final.index = [f"Afirmação {i}" for i in df_final.index]
                    st.dataframe(df_final, use_container_width=True)
                    st.download_button(f"Exportar Matriz Ronda {r} (Excel/CSV)", data=df_final.to_csv(index_label="Afirmação").encode('utf-8'), file_name=f'matriz_estatistica_ronda_{r}.csv', mime='text/csv')
                
                st.divider()
                st.subheader("📈 Evolução Gráfica do Estudo")
                dados_graficos = []
                for r in sorted(df_all_rep['round_num'].unique()):
                    df_r = df_all_rep[df_all_rep['round_num'] == r]
                    for stmt in df_r['statement_id'].unique():
                        notas = df_r[(df_r['statement_id'] == stmt) & (df_r['score'] > 0)]['score'].dropna()
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
            st.dataframe(pd.read_sql_query("SELECT * FROM respostas", conn), use_container_width=True)
            st.dataframe(pd.read_sql_query("SELECT * FROM tempos_ronda", conn), use_container_width=True)
                
        with tab3:
            st.subheader("Utilizadores Registados")
            df_users = pd.read_sql_query("SELECT expert_id as 'ID de Perito' FROM utilizadores", conn)
            st.dataframe(df_users, hide_index=True, use_container_width=True) 
            
            col1, col2 = st.columns(2)
            with col1:
                with st.form("form_add_user", clear_on_submit=True):
                    novo_id = st.text_input("Novo ID (ex: P01)")
                    nova_pass = st.text_input("Código de Acesso")
                    if st.form_submit_button("Adicionar Perito"):
                        if novo_id and nova_pass:
                            try:
                                conn.execute("INSERT INTO utilizadores VALUES (?, ?, 1)", (novo_id, hash_password(nova_pass)))
                                conn.commit()
                                st.rerun()
                            except sqlite3.IntegrityError: 
                                st.error("Erro: Esse ID já existe na base de dados.")
            with col2:
                with st.form("form_del_user"):
                    del_id = st.selectbox("Remover Perito", df_users['ID de Perito'].tolist() if not df_users.empty else [])
                    if st.form_submit_button("Apagar Perito"):
                        if del_id:
                            conn.execute("DELETE FROM utilizadores WHERE expert_id=?", (del_id,))
                            conn.commit()
                            st.rerun()
            
        with tab4:
            st.subheader("Gerir Afirmações")
            df_af = pd.read_sql_query("SELECT * FROM afirmacoes", conn)
            st.dataframe(df_af, hide_index=True, use_container_width=True)
            
            if not df_af.empty:
                if st.button("🗑️ Apagar TODAS as Afirmações"):
                    conn.execute("DELETE FROM afirmacoes")
                    conn.execute("DELETE FROM sqlite_sequence WHERE name='afirmacoes'")
                    conn.commit()
                    st.rerun()
            
            with st.form("form_add_af", clear_on_submit=True):
                nova_af = st.text_area("Texto da nova afirmação")
                if st.form_submit_button("Adicionar Afirmação"):
                    if nova_af.strip():
                        conn.execute("INSERT INTO afirmacoes (texto) VALUES (?)", (nova_af,))
                        conn.commit()
                        st.rerun()
            with st.form("form_del_af"):
                del_af_id = st.selectbox("Apagar Afirmação ID", df_af['id'].tolist() if not df_af.empty else [])
                if st.form_submit_button("Apagar Selecionada"):
                    conn.execute("DELETE FROM afirmacoes WHERE id=?", (del_af_id,))
                    count_af = conn.execute("SELECT COUNT(*) FROM afirmacoes").fetchone()[0]
                    if count_af == 0:
                        conn.execute("DELETE FROM sqlite_sequence WHERE name='afirmacoes'")
                    conn.commit()
                    st.rerun()

        with tab5:
            st.subheader("Configurações e Controlo de Rondas")
            
            if st.button("🚨 REINICIAR ESTUDO (Apagar TUDO e Resetar IDs de Afirmações)"):
                conn.execute("DELETE FROM respostas")
                conn.execute("DELETE FROM utilizadores")
                conn.execute("DELETE FROM afirmacoes")
                conn.execute("DELETE FROM tempos_ronda")
                conn.execute("DELETE FROM sqlite_sequence WHERE name='afirmacoes'")
                conn.commit()
                st.warning("Tudo apagado com sucesso. Os IDs recomeçam no 1. Recarregue a página.")
                st.rerun()
            st.divider()

            st.info(f"Ronda ativa atual: **{ronda_ativa}** (de {max_rondas})")
            
            col_cfg1, col_cfg2 = st.columns(2)
            with col_cfg1:
                if ronda_ativa < max_rondas:
                    if st.button("🚀 Dar ordem para avançar para a Ronda Seguinte"):
                        conn.execute("UPDATE configuracoes SET valor=? WHERE chave='ronda_ativa'", (str(ronda_ativa + 1),))
                        conn.commit()
                        st.success("Avançado com sucesso!")
                        st.rerun()
            with col_cfg2:
                if st.button("🏁 Concluir Estudo Antecipadamente (Definir Ronda Atual como Final)"):
                    conn.execute("UPDATE configuracoes SET valor=? WHERE chave='max_rondas'", (str(ronda_ativa),))
                    conn.commit()
                    st.success("Estudo concluído antecipadamente!")
                    st.rerun()
            st.divider()

            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("**Escala Máxima (Ímpares)**")
                escalas_impares = [3, 5, 7, 9]
                idx_escala = escalas_impares.index(escala_max) if escala_max in escalas_impares else 1
                nova_escala = st.selectbox("Valor máximo", escalas_impares, index=idx_escala)
                if st.button("Atualizar Escala"):
                    conn.execute("UPDATE configuracoes SET valor=? WHERE chave='escala_max'", (str(nova_escala),))
                    conn.commit()
                    st.success("Atualizado!")
                    st.rerun()
            with c2:
                st.markdown("**Total de Rondas**")
                novas_rondas = st.number_input("Nº de Rondas", min_value=1, max_value=10, value=max_rondas)
                if st.button("Atualizar Rondas"):
                    conn.execute("UPDATE configuracoes SET valor=? WHERE chave='max_rondas'", (str(novas_rondas),))
                    conn.commit()
                    st.success("Atualizadas!")
                    st.rerun()
            with c3:
                st.markdown("**Regra de Justificação**")
                opcoes_regra = ["Extremos (1 e Max)", "Sempre obrigatória", "Apenas notas baixas (1)", "Desativada (Opcional)"]
                idx_regra = opcoes_regra.index(regra_just) if regra_just in opcoes_regra else 0
                nova_regra = st.selectbox("Exigir em:", opcoes_regra, index=idx_regra)
                if st.button("Atualizar Regra"):
                    conn.execute("UPDATE configuracoes SET valor=? WHERE chave='regra_justificacao'", (nova_regra,))
                    conn.commit()
                    st.success("Atualizada!")
                    st.rerun()

        with tab6:
            st.subheader("👁️ Visão em Tempo Real do Ecrã dos Peritos")
            st.info("Aqui pode inspecionar exatamente o estado de consenso e as afirmações que cada perito visualiza.")
            
            lista_experts = [u[0] for u in conn.execute("SELECT expert_id FROM utilizadores").fetchall()]
            if not lista_experts:
                st.warning("Ainda não existem peritos registados.")
            else:
                sel_expert = st.selectbox("Selecione o perito para simular a visão:", lista_experts)
                if sel_expert:
                    st.markdown(f"### Perspetiva do Perito: **{sel_expert}**")
                    df_all_r = pd.read_sql_query("SELECT * FROM respostas", conn)
                    df_af = pd.read_sql_query("SELECT * FROM afirmacoes ORDER BY id", conn)
                    
                    rondas_feitas_exp = [r[0] for r in conn.execute("SELECT DISTINCT round_num FROM respostas WHERE expert_id = ?", (sel_expert,)).fetchall()]
                    r_exp = 1
                    while r_exp <= max_rondas:
                        if r_exp not in rondas_feitas_exp: break
                        r_exp += 1
                        
                    st.markdown(f"**Ronda atual em que este perito se encontra:** Ronda {min(r_exp, max_rondas)}")
                    
                    if not df_af.empty:
                        for _, row_a in df_af.iterrows():
                            aid = row_a['id']
                            atxt = row_a['texto']
                            
                            alc_cons = False
                            for pr in range(1, r_exp):
                                sprev = df_all_r[(df_all_r['round_num'] == pr) & (df_all_r['statement_id'] == aid) & (df_all_r['score'] > 0)]['score'].dropna()
                                if not sprev.empty and calcular_consenso_percentual(sprev, escala_max) >= 80.0:
                                    alc_cons = True
                                    break
                            
                            if alc_cons:
                                st.success(f"✅ **[ID {aid}]** {atxt} — *Afirmação consensualizada no grupo.*")
                            else:
                                r_ant_exp = r_exp - 1
                                if r_ant_exp >= 1:
                                    v_ant = df_all_r[(df_all_r['expert_id'] == sel_expert) & (df_all_r['round_num'] == r_ant_exp) & (df_all_r['statement_id'] == aid)]
                                    if not v_ant.empty and int(v_ant['score'].values[0]) == 0:
                                        st.warning(f"🚫 **[ID {aid}]** {atxt} — *Marcada pelo perito como 'Não relevante para si'.*")
                                        continue
                                st.info(f"📝 **[ID {aid}]** {atxt} — *Pendente / Ativa para votação.*")
                    else:
                        st.warning("Não existem afirmações inseridas.")
                    
        conn.close()
