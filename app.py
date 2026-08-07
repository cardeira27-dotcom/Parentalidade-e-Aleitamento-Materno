import streamlit as st
import sqlite3
import pandas as pd

# Configuração da Página
st.set_page_config(page_title="Painel Delphi - Enfermagem", layout="centered")

# --- BANCO DE DADOS SQLite ---
def init_db():
    conn = sqlite3.connect("delphi_data.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS respostas (
            expert_id TEXT,
            round_num INTEGER,
            statement_id INTEGER,
            score INTEGER,
            justification TEXT,
            PRIMARY KEY (expert_id, round_num, statement_id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Lista das 24 Afirmações (Pode substituir pelos seus textos reais)
AFIRMACOES = [
    f"Afirmação {i}: [Insira aqui o texto da afirmação]" for i in range(1, 25)
]

# --- MENU LATERAL (NAVEGAÇÃO) ---
st.sidebar.title("Navegação")
modo = st.sidebar.radio("Escolha o perfil:", ["Participante (Perito)", "Administrador (Investigador)"])

if modo == "Participante (Perito)":
    st.title("Painel Delphi - Consulta de Peritos")
    st.markdown("Bem-vindo ao estudo de consenso. Por favor, insira o seu ID e selecione a ronda.")
    
    expert_id = st.sidebar.selectbox("O seu ID de Perito:", ["P01", "P02", "P03", "P04", "P05", "P06"])
    round_num = st.sidebar.selectbox("Ronda:", [1, 2])
    
    conn = sqlite3.connect("delphi_data.db")
    c = conn.cursor()
    
    if round_num == 1:
        st.subheader("Ronda 1 - Avaliação Inicial")
        st.info("Classifique cada afirmação de 1 (Discordo Totalmente) a 5 (Concordo Totalmente). A justificação é obrigatória se votar 1 ou 5.")
        
        with st.form("form_ronda1"):
            respostas_temp = {}
            for i, afirmacao in enumerate(AFIRMACOES):
                st.markdown(f"**{afirmacao}**")
                score = st.radio(f"Concordância (Afirmação {i+1})", [1, 2, 3, 4, 5], horizontal=True, key=f"s_{i}")
                
                obrigatorio = (score == 1 or score == 5)
                label_just = "Justificação (Obrigatória por ter votado nos extremos):" if obrigatorio else "Justificação (Opcional):"
                just = st.text_area(label_just, key=f"j_{i}")
                
                respostas_temp[i+1] = {"score": score, "just": just, "obrigatorio": obrigatorio}
                st.divider()
                
            submitted = st.form_submit_button("Submeter Respostas da Ronda 1")
            
            if submitted:
                erros = 0
                for idx, dados in respostas_temp.items():
                    if dados["obrigatorio"] and not dados["just"].strip():
                        st.error(f"A afirmação {idx} exige justificação obrigatória (votou 1 ou 5).")
                        erros += 1
                
                if erros == 0:
                    for idx, dados in respostas_temp.items():
                        c.execute('''
                            INSERT OR REPLACE INTO respostas (expert_id, round_num, statement_id, score, justification)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (expert_id, 1, idx, dados["score"], dados["just"]))
                    conn.commit()
                    st.success("Respostas guardadas com sucesso! Obrigado pela sua participação na Ronda 1.")
                
    elif round_num == 2:
        st.subheader("Ronda 2 - Reavaliação por Consenso")
        st.markdown("Nesta ronda, reveja as afirmações que ainda não obtiveram consenso global na Ronda 1, tendo em conta a média do grupo.")
        
        df_r1 = pd.read_sql_query("SELECT * FROM respostas WHERE round_num = 1", conn)
        
        if df_r1.empty:
            st.warning("Ainda não existem dados suficientes da Ronda 1 para gerar a Ronda 2.")
        else:
            itens_r2 = []
            medias_grupo = {}
            comentarios_grupo = {}
            
            for idx in range(1, 25):
                df_item = df_r1[df_r1['statement_id'] == idx]
                if not df_item.empty:
                    total_votos = len(df_item)
                    votos_altos = len(df_item[df_item['score'] >= 4])
                    concordancia = (votos_altos / total_votos) if total_votos > 0 else 0
                    
                    media = df_item['score'].mean()
                    medias_grupo[idx] = media
                    
                    justs = df_item[df_item['justification'].str.strip() != '']['justification'].tolist()
                    comentarios_grupo[idx] = justs
                    
                    if concordancia < 0.8:
                        itens_r2.append(idx)
            
            if not itens_r2:
                st.success("Parabéns! Todas as afirmações atingiram consenso na Ronda 1. Não é necessária Ronda 2.")
            else:
                st.info(f"Existem {len(itens_r2)} afirmações em discussão para a Ronda 2.")
                
                df_perito = df_r1[df_r1['expert_id'] == expert_id]
                
                with st.form("form_ronda2"):
                    respostas_r2 = {}
                    for idx in itens_r2:
                        voto_antigo_row = df_perito[df_perito['statement_id'] == idx]
                        voto_antigo = voto_antigo_row['score'].values[0] if not voto_antigo_row.empty else "N/A"
                        
                        st.markdown(f"### Afirmação {idx}: {AFIRMACOES[idx-1]}")
                        st.write(f"📊 **Média do grupo na Ronda 1:** {round(medias_grupo.get(idx, 0), 1)} / 5.0")
                        st.write(f"👤 **O seu voto anterior (Ronda 1):** {voto_antigo}")
                        
                        if comentarios_grupo.get(idx):
                            st.markdown("💬 *Comentários anónimos dos peritos na Ronda 1:*")
                            for comm in comentarios_grupo[idx]:
                                st.markdown(f"> *\"{comm}\"*")
                        
                        score_r2 = st.radio(f"Novo voto (Afirmação {idx})", [1, 2, 3, 4, 5], horizontal=True, key=f"s2_{idx}")
                        obrigatorio_r2 = (score_r2 == 1 or score_r2 == 5)
                        label_just_r2 = "Nova justificação (Obrigatória por ter votado nos extremos):" if obrigatorio_r2 else "Nova justificação (Opcional):"
                        just_r2 = st.text_area(label_just_r2, key=f"j2_{idx}")
                        
                        respostas_r2[idx] = {"score": score_r2, "just": just_r2, "obrigatorio": obrigatorio_r2}
                        st.divider()
                        
                    submitted_r2 = st.form_submit_button("Submeter Respostas da Ronda 2")
                    
                    if submitted_r2:
                        erros_r2 = 0
                        for idx, dados in respostas_r2.items():
                            if dados["obrigatorio"] and not dados["just"].strip():
                                st.error(f"A afirmação {idx} exige justificação obrigatória.")
                                erros_r2 += 1
                                
                        if erros_r2 == 0:
                            for idx, dados in respostas_r2.items():
                                c.execute('''
                                    INSERT OR REPLACE INTO respostas (expert_id, round_num, statement_id, score, justification)
                                    VALUES (?, ?, ?, ?, ?)
                                ''', (expert_id, 2, idx, dados["score"], dados["just"]))
                            conn.commit()
                            st.success("Respostas da Ronda 2 submetidas com sucesso!")

    conn.close()

elif modo == "Administrador (Investigador)":
    st.title("Área do Investigador (Painel de Controlo)")
    st.markdown("Aqui pode ver o ponto de situação das respostas dos 6 peritos e exportar os dados.")
    
    conn = sqlite3.connect("delphi_data.db")
    df_all = pd.read_sql_query("SELECT * FROM respostas", conn)
    conn.close()
    
    if df_all.empty:
        st.warning("Ainda não existem registos na base de dados.")
    else:
        st.subheader("Tabela Geral de Respostas")
        st.dataframe(df_all)
        
        csv = df_all.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Descarregar dados em CSV (para o Excel)",
            data=csv,
            file_name='delphi_resultados.csv',
            mime='text/csv',
        )
