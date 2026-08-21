import streamlit as st
import pandas as pd
import os
import datetime
import xml.etree.ElementTree as ET
import plotly.express as px
import plotly.graph_objects as go
from supabase import create_client, Client

favicon_path = "logo-sovereign.png" if os.path.exists("logo-sovereign.png") else ("logo_sovereign.png" if os.path.exists("logo_sovereign.png") else None)

st.set_page_config(
    page_title="Sovereign Client Engine",
    page_icon=favicon_path if favicon_path else "🛡️",
    layout="wide"
)

# Conexão Supabase
SUPABASE_URL = "https://kmsrmsskkvrcwwzcvmvo.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imttc3Jtc3Nra3ZyY3d3emN2bXZvIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4NzE1MTU0NCwiZXhwIjoyMTAyNzI3NTQ0fQ.76HeRp0Eh7SkKDdE5WT4wqZtA7ezF5F6-_Ryh3SOH7E"

@st.cache_resource
def init_connection():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_connection()

# ----------------- FUNÇÕES DE BANCO -----------------
def autenticar_usuario(email, senha):
    email_limpo = email.strip().lower()
    senha_limpa = senha.strip()
    
    user_res = supabase.table("users").select("*").eq("email", email_limpo).execute()
    if not user_res.data:
        st.warning(f"Usuário '{email_limpo}' não encontrado.")
        return None
        
    usuario = user_res.data[0]
    if usuario.get("senha_hash") == senha_limpa:
        org_res = supabase.table("organizations").select("*").eq("id", usuario["org_id"]).execute()
        org_data = org_res.data[0] if org_res.data else {}
        return {
            "user_id": usuario["id"],
            "nome": usuario["nome"],
            "org_id": usuario["org_id"],
            "nome_empresa": org_data.get("nome_empresa", "Organização"),
            "chave_api_acesso": org_data.get("chave_api_acesso", ""),
            "config_triagem": org_data.get("config_triagem") or {},
            "nivel": usuario.get("nivel_acesso", "admin")
        }
    else:
        st.warning("Senha incorreta informada.")
        return None

def carregar_clientes(org_id):
    leads_res = supabase.table("leads").select("*").eq("org_id", org_id).order("created_at", desc=True).execute()
    return leads_res.data

def carregar_config_organizacao(org_id):
    org_res = supabase.table("organizations").select("*").eq("id", org_id).execute()
    return org_res.data[0] if org_res.data else {}

def salvar_config_organizacao(org_id, nova_config):
    supabase.table("organizations").update({"config_triagem": nova_config}).eq("id", org_id).execute()
    st.toast("Configurações da IA atualizadas com sucesso!", icon="⚙️")

def atualizar_dados_cliente(lead_id, payload):
    supabase.table("leads").update(payload).eq("id", lead_id).execute()
    st.toast("Dados do cliente atualizados com sucesso!", icon="✅")

def upload_pdf_supabase(lead_id, arquivo):
    nome_arquivo = f"{lead_id}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{arquivo.name}"
    caminho_storage = f"orcamentos/{nome_arquivo}"
    bytes_arquivo = arquivo.read()
    supabase.storage.from_("documentos-clientes").upload(
        path=caminho_storage,
        file=bytes_arquivo,
        file_options={"content-type": "application/pdf"}
    )
    return supabase.storage.from_("documentos-clientes").get_public_url(caminho_storage)

def gerar_xml(df_filtrado):
    root = ET.Element("Clientes")
    for _, row in df_filtrado.iterrows():
        cliente_elem = ET.SubElement(root, "Cliente")
        ET.SubElement(cliente_elem, "Nome").text = str(row.get("nome", ""))
        ET.SubElement(cliente_elem, "Telefone").text = str(row.get("telefone", ""))
        ET.SubElement(cliente_elem, "Endereco").text = str(row.get("endereco_regiao", ""))
        ET.SubElement(cliente_elem, "TipoServico").text = str(row.get("tipo_servico", ""))
        ET.SubElement(cliente_elem, "Status").text = str(row.get("status_funil", ""))
        ET.SubElement(cliente_elem, "MotivoPerda").text = str(row.get("motivo_perda", ""))
        ET.SubElement(cliente_elem, "ValorProposta").text = str(row.get("valor_proposta", 0.0))
        ET.SubElement(cliente_elem, "DataCadastro").text = str(row.get("created_at", ""))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)

# ----------------- TELA DE LOGIN -----------------
if "usuario_logado" not in st.session_state:
    st.session_state["usuario_logado"] = None

if st.session_state["usuario_logado"] is None:
    _, col_login, _ = st.columns([1, 1.2, 1])
    with col_login:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.title("Sovereign Client Engine")
        st.caption("Acesso Restrito ao Painel de Atendimento")
        
        with st.form("form_login"):
            email = st.text_input("E-mail de Acesso")
            senha = st.text_input("Senha", type="password")
            btn_entrar = st.form_submit_button("Acessar Painel")
            
            if btn_entrar:
                sessao = autenticar_usuario(email, senha)
                if sessao:
                    st.session_state["usuario_logado"] = sessao
                    st.rerun()
    st.stop()

# ----------------- DASHBOARD PRINCIPAL -----------------
usuario = st.session_state["usuario_logado"]
org_id = usuario["org_id"]
nome_empresa = usuario["nome_empresa"]
nivel_acesso = usuario["nivel"]

st.title("Sovereign Client Engine")
st.caption(f"Central de Atendimento e Gestão de Propostas • **{nome_empresa}**")

st.sidebar.markdown(f"**Operador:** {usuario['nome']}")
st.sidebar.markdown(f"**Empresa:** {nome_empresa}")
st.sidebar.markdown(f"**Nível:** `{nivel_acesso.upper()}`")

if st.sidebar.button("Encerrar Sessão (Sair)"):
    st.session_state["usuario_logado"] = None
    st.rerun()

# Divisão em 3 Abas
tab_crm, tab_analytics, tab_config = st.tabs([
    "📊 Fila de Atendimento",
    "📈 Métricas & Inteligência Visual",
    "⚙️ Configuração da IA & WhatsApp"
])

clientes_raw = carregar_clientes(org_id)
df_completo = pd.DataFrame(clientes_raw) if clientes_raw else pd.DataFrame()

if not df_completo.empty:
    df_completo["created_at_dt"] = pd.to_datetime(df_completo["created_at"])
    df_completo["valor_proposta"] = pd.to_numeric(df_completo["valor_proposta"], errors="coerce").fillna(0.0)

# Filtros Globais da Sidebar
st.sidebar.markdown("---")
st.sidebar.header("Filtros Globais")

status_disponiveis = ["Todos", "Triado", "Em Triagem", "Em Atendimento", "Proposta Enviada", "Fechado", "Perdido"]
status_selecionado = st.sidebar.selectbox("Filtrar por Status", status_disponiveis)
termo_busca = st.sidebar.text_input("Buscar por Nome, Telefone ou Região", "")

st.sidebar.subheader("Período")
opcao_tempo = st.sidebar.selectbox(
    "Intervalo Rápido",
    ["Todo o Histórico", "Hoje", "Últimos 7 Dias", "Últimos 30 Dias", "Personalizado"]
)

data_hoje = datetime.datetime.now().date()
df_filtrado = df_completo.copy()

if not df_completo.empty:
    if opcao_tempo == "Hoje":
        df_filtrado = df_filtrado[df_filtrado["created_at_dt"].dt.date == data_hoje]
    elif opcao_tempo == "Últimos 7 Dias":
        data_limite = data_hoje - datetime.timedelta(days=7)
        df_filtrado = df_filtrado[df_filtrado["created_at_dt"].dt.date >= data_limite]
    elif opcao_tempo == "Últimos 30 Dias":
        data_limite = data_hoje - datetime.timedelta(days=30)
        df_filtrado = df_filtrado[df_filtrado["created_at_dt"].dt.date >= data_limite]
    elif opcao_tempo == "Personalizado":
        dt_inicio = st.sidebar.date_input("Início", data_hoje - datetime.timedelta(days=15))
        dt_fim = st.sidebar.date_input("Fim", data_hoje)
        df_filtrado = df_filtrado[
            (df_filtrado["created_at_dt"].dt.date >= dt_inicio) & 
            (df_filtrado["created_at_dt"].dt.date <= dt_fim)
        ]

    if status_selecionado != "Todos":
        df_filtrado = df_filtrado[df_filtrado["status_funil"] == status_selecionado]
        
    if termo_busca:
        df_filtrado = df_filtrado[
            df_filtrado["nome"].astype(str).str.contains(termo_busca, case=False, na=False) |
            df_filtrado["telefone"].astype(str).str.contains(termo_busca, case=False, na=False) |
            df_filtrado["endereco_regiao"].astype(str).str.contains(termo_busca, case=False, na=False)
        ]

# ==============================================================================
# ABA 1: CRM & FILA DE ATENDIMENTO
# ==============================================================================
with tab_crm:
    if df_filtrado.empty:
        st.info("Nenhum registro encontrado para os filtros aplicados.")
    else:
        st.markdown("### Resumo Operacional")
        m1, m2, m3, m4 = st.columns(4)
        
        total_filtrado = len(df_filtrado)
        total_fechados = len(df_filtrado[df_filtrado["status_funil"] == "Fechado"])
        faturamento_fechado = df_filtrado[df_filtrado["status_funil"] == "Fechado"]["valor_proposta"].sum()
        em_negociacao = df_filtrado[df_filtrado["status_funil"].isin(["Triado", "Em Triagem", "Em Atendimento", "Proposta Enviada"])]["valor_proposta"].sum()

        m1.metric("Total no Filtro", total_filtrado)
        m2.metric("Propostas Fechadas", total_fechados)
        m3.metric("Faturamento Fechado", f"R$ {faturamento_fechado:,.2f}")
        m4.metric("Em Negociação", f"R$ {em_negociacao:,.2f}")

        st.sidebar.markdown("---")
        st.sidebar.subheader("Exportação do Filtro Atual")
        st.sidebar.download_button(
            label="Baixar XML",
            data=gerar_xml(df_filtrado),
            file_name=f"leads_{nome_empresa.lower()}.xml",
            mime="application/xml"
        )
        st.sidebar.download_button(
            label="Baixar CSV",
            data=df_filtrado.to_csv(index=False).encode('utf-8'),
            file_name=f"leads_{nome_empresa.lower()}.csv",
            mime="text/csv"
        )

        st.markdown("---")
        st.subheader(f"Fila de Clientes ({total_filtrado} registros)")

        for _, cliente in df_filtrado.iterrows():
            dados_extras = cliente.get("dados_extras") or {}
            with st.expander(f"{cliente.get('nome', 'Sem Nome')} | 📞 {cliente.get('telefone')} | Status: {cliente.get('status_funil')}"):
                c1, c2 = st.columns([2, 1])

                with c1:
                    st.markdown(f"**Serviço Desejado:** {cliente.get('tipo_servico', 'N/A')}")
                    st.markdown(f"**Localização / Obra:** {cliente.get('endereco_regiao', 'N/A')}")
                    st.markdown(f"**Resumo da Demanda:** {cliente.get('resumo_necessidade', 'N/A')}")
                    st.caption(f"Data de Entrada: {cliente.get('created_at_dt').strftime('%d/%m/%Y às %H:%M')}")
                    
                    pdf_url = dados_extras.get("pdf_url")
                    if pdf_url:
                        st.markdown(f"📄 [**Abrir Orçamento / Nota Fiscal (PDF)**]({pdf_url})")

                with c2:
                    tel_clean = ''.join(filter(str.isdigit, str(cliente.get('telefone', ''))))
                    st.markdown(f"[**Iniciar Conversa no WhatsApp**](https://wa.me/{tel_clean})", unsafe_allow_html=True)

                    with st.form(key=f"form_lead_{cliente['id']}"):
                        status_opcoes = ["Triado", "Em Triagem", "Em Atendimento", "Proposta Enviada", "Fechado", "Perdido"]
                        status_atual = cliente.get("status_funil", "Triado")
                        idx = status_opcoes.index(status_atual) if status_atual in status_opcoes else 0

                        novo_status = st.selectbox("Status", status_opcoes, index=idx)
                        novo_valor = st.number_input("Valor da Proposta (R$)", value=float(cliente.get("valor_proposta") or 0.0), step=100.0)
                        
                        cpf_cnpj_atual = dados_extras.get("cpf_cnpj", "")
                        novo_cpf_cnpj = st.text_input("CPF / CNPJ (Opcional)", value=cpf_cnpj_atual)
                        
                        arquivo_pdf = st.file_uploader("Anexar Proposta / NF (PDF)", type=["pdf"])

                        motivo = cliente.get("motivo_perda") or ""
                        if novo_status == "Perdido":
                            motivo = st.text_input("Motivo da Perda", value=motivo)

                        btn_salvar = st.form_submit_button("Salvar Alterações")
                        if btn_salvar:
                            novos_extras = dict(dados_extras)
                            if novo_cpf_cnpj:
                                novos_extras["cpf_cnpj"] = novo_cpf_cnpj

                            if arquivo_pdf is not None:
                                url_gerada = upload_pdf_supabase(cliente["id"], arquivo_pdf)
                                novos_extras["pdf_url"] = url_gerada

                            payload = {
                                "status_funil": novo_status,
                                "valor_proposta": novo_valor,
                                "dados_extras": novos_extras,
                                "motivo_perda": motivo if novo_status == "Perdido" else None
                            }

                            atualizar_dados_cliente(cliente["id"], payload)
                            st.rerun()

# ==============================================================================
# ABA 2: MÉTRICAS & INTELIGÊNCIA VISUAL (ANALYTICS)
# ==============================================================================
with tab_analytics:
    st.markdown("### Inteligência Comercial & Métricas Avançadas")
    st.caption("Visão estratégica gerada em tempo real com base no histórico filtrado.")

    if df_filtrado.empty:
        st.info("Sem dados suficientes para gerar gráficos no período selecionado.")
    else:
        # Métricas de Alta Performance
        total_leads = len(df_filtrado)
        fechados_df = df_filtrado[df_filtrado["status_funil"] == "Fechado"]
        perdidos_df = df_filtrado[df_filtrado["status_funil"] == "Perdido"]
        
        taxa_conversao = (len(fechados_df) / total_leads * 100) if total_leads > 0 else 0.0
        ticket_medio = (fechados_df["valor_proposta"].sum() / len(fechados_df)) if len(fechados_df) > 0 else 0.0
        
        g1, g2, g3, g4 = st.columns(4)
        g1.metric("Taxa de Conversão", f"{taxa_conversao:.1f}%")
        g2.metric("Ticket Médio (Fechados)", f"R$ {ticket_medio:,.2f}")
        g3.metric("Oportunidades Perdidas", len(perdidos_df))
        g4.metric("Total de Oportunidades", total_leads)

        st.markdown("---")
        col_graf1, col_graf2 = st.columns(2)

        with col_graf1:
            # Gráfico de Funil / Distribuição por Status
            status_counts = df_filtrado["status_funil"].value_counts().reset_index()
            status_counts.columns = ["Status", "Quantidade"]
            fig_funil = px.bar(
                status_counts,
                x="Status",
                y="Quantidade",
                title="Distribuição do Funil de Atendimento",
                color="Status",
                color_discrete_sequence=["#8B5CF6", "#A78BFA", "#38BDF8", "#34D399", "#F87171", "#94A3B8"]
            )
            fig_funil.update_layout(template="plotly_dark", plot_bgcolor="#1E1E2E", paper_bgcolor="#1E1E2E", showlegend=False)
            st.plotly_chart(fig_funil, use_container_width=True)

        with col_graf2:
            # Gráfico de Demandas por Região
            regiao_df = df_filtrado[df_filtrado["endereco_regiao"].notnull() & (df_filtrado["endereco_regiao"] != "")]
            if not regiao_df.empty:
                top_regioes = regiao_df["endereco_regiao"].value_counts().head(6).reset_index()
                top_regioes.columns = ["Região", "Demandas"]
                fig_regioes = px.pie(
                    top_regioes,
                    names="Região",
                    values="Demandas",
                    title="Top Regiões Mais Demandadas",
                    hole=0.4,
                    color_discrete_sequence=px.colors.sequential.Purp
                )
                fig_regioes.update_layout(template="plotly_dark", plot_bgcolor="#1E1E2E", paper_bgcolor="#1E1E2E")
                st.plotly_chart(fig_regioes, use_container_width=True)
            else:
                st.info("Nenhuma localização capturada ainda para exibir o gráfico.")

        col_graf3, col_graf4 = st.columns(2)

        with col_graf3:
            # Serviços Mais Solicitados
            servicos_df = df_filtrado[df_filtrado["tipo_servico"].notnull() & (df_filtrado["tipo_servico"] != "")]
            if not servicos_df.empty:
                top_servicos = servicos_df["tipo_servico"].value_counts().head(6).reset_index()
                top_servicos.columns = ["Serviço", "Total"]
                fig_serv = px.bar(
                    top_servicos,
                    y="Serviço",
                    x="Total",
                    orientation="h",
                    title="Tipos de Serviços Mais Solicitados",
                    color_discrete_sequence=["#8B5CF6"]
                )
                fig_serv.update_layout(template="plotly_dark", plot_bgcolor="#1E1E2E", paper_bgcolor="#1E1E2E")
                st.plotly_chart(fig_serv, use_container_width=True)
            else:
                st.info("Nenhum serviço registrado para o gráfico.")

        with col_graf4:
            # Diagnóstico de Motivos de Perda
            motivos_df = df_filtrado[df_filtrado["motivo_perda"].notnull() & (df_filtrado["motivo_perda"] != "")]
            if not motivos_df.empty:
                top_motivos = motivos_df["motivo_perda"].value_counts().reset_index()
                top_motivos.columns = ["Motivo", "Total"]
                fig_motivos = px.bar(
                    top_motivos,
                    x="Motivo",
                    y="Total",
                    title="Diagnóstico: Principais Motivos de Perda",
                    color_discrete_sequence=["#EF4444"]
                )
                fig_motivos.update_layout(template="plotly_dark", plot_bgcolor="#1E1E2E", paper_bgcolor="#1E1E2E")
                st.plotly_chart(fig_motivos, use_container_width=True)
            else:
                st.info("Nenhum lead com motivo de perda registrado no período.")

# ==============================================================================
# ABA 3: CONFIGURAÇÃO DA IA & WHATSAPP
# ==============================================================================
with tab_config:
    st.markdown("### Configurações de Atendimento Inteligente")
    st.caption("Personalize o comportamento, o nicho de mercado e os prompts da IA para esta organização.")

    org_atual = carregar_config_organizacao(org_id)
    config_atual = org_atual.get("config_triagem") or {}
    api_key_org = org_atual.get("chave_api_acesso", "")

    st.info(f"**Endpoint Webhook da sua Empresa:**\n`/webhook/whatsapp/{api_key_org}`")

    with st.form("form_config_ia"):
        st.subheader("1. Nicho & Identidade da Organização")
        nicho = st.text_input(
            "Nicho de Atuação da Empresa",
            value=config_atual.get("nicho", "Calhas e Estruturas Metálicas")
        )

        st.subheader("2. Prompt de Instrução do Sistema (Personalidade da IA)")
        st.caption("Instrua a IA sobre como ela deve acolher os clientes, quais informações deve coletar e as regras que nunca deve violar.")
        
        prompt_padrao = (
            "Você é a atendente virtual especialista da ACOTEk Calhas.\n"
            "Sua missão é fazer uma triagem educada, acolhedora e rápida em 2 a 3 trocas de mensagens.\n\n"
            "REGRAS:\n"
            "1. Colete apenas: Nome/Empresa, Tipo de Peça/Serviço e Bairro/Região da obra.\n"
            "2. NUNCA informe preços tabelados nem feche prazos; avise que o consultor técnico assumirá.\n"
            "3. Seja concisa e profissional."
        )
        
        prompt_customizado = st.text_area(
            "Prompt do Sistema (System Instruction)",
            value=config_atual.get("prompt_customizado", prompt_padrao),
            height=200
        )

        st.subheader("3. Conexão do Gateway WhatsApp (Opcional / Produção)")
        c_inst1, c_inst2 = st.columns(2)
        with c_inst1:
            instancia_url = st.text_input("URL da Instância (Evolution API / Z-API)", value=config_atual.get("instancia_url", ""))
        with c_inst2:
            instancia_apikey = st.text_input("API Key da Instância WhatsApp", value=config_atual.get("instancia_apikey", ""), type="password")

        btn_salvar_config = st.form_submit_button("Salvar Parâmetros da IA")
        if btn_salvar_config:
            nova_configuracao = {
                "nicho": nicho,
                "prompt_customizado": prompt_customizado,
                "instancia_url": instancia_url,
                "instancia_apikey": instancia_apikey
            }
            salvar_config_organizacao(org_id, nova_configuracao)
            st.rerun()