import os
import requests
import uvicorn
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from supabase import create_client, Client

app = FastAPI(title="Sovereign Webhook Router & Dispatcher")

# 1. Configurações de Banco, IA e WhatsApp Gateway
SUPABASE_URL = "https://kmsrmsskkvrcwwzcvmvo.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imttc3Jtc3Nra3ZyY3d3emN2bXZvIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4NzE1MTU0NCwiZXhwIjoyMTAyNzI3NTQ0fQ.76HeRp0Eh7SkKDdE5WT4wqZtA7ezF5F6-_Ryh3SOH7E"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyD5qfUcNeDNWZ9LA2LetmJG53Uw1RDR488")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# 2. Schema de Extração da IA
class DadosTriagemDinamica(BaseModel):
    resposta_para_cliente: str = Field(description="Mensagem direta, empática e curta para o WhatsApp.")
    nome_identificado: str | None = Field(default=None)
    tipo_servico: str | None = Field(default=None)
    localizacao_regiao: str | None = Field(default=None)
    resumo_necessidade: str | None = Field(default=None)
    triagem_concluida: bool = Field(description="True se coletou nome/empresa, serviço e localização.")

# 3. Motor de Disparo de Mensagem (WhatsApp Dispatcher)
def enviar_mensagem_whatsapp(instancia_url: str, apikey_instancia: str, telefone: str, texto_resposta: str):
    """
    Envia a mensagem de volta para o cliente via Evolution API / Gateway WhatsApp.
    Se estiver em ambiente de teste simulado sem instância ativa, registra o log com segurança.
    """
    if not instancia_url or not apikey_instancia:
        print(f"📡 [DISPATCHER SIMULADO] Resposta pronta para {telefone}: \"{texto_resposta}\"")
        return

    endpoint = f"{instancia_url.rstrip('/')}/message/sendText/{telefone}"
    headers = {
        "apikey": apikey_instancia,
        "Content-Type": "application/json"
    }
    payload = {
        "number": telefone,
        "options": {"delay": 1200, "presence": "composing"},
        "textMessage": {"text": texto_resposta}
    }
    try:
        req = requests.post(endpoint, json=payload, headers=headers, timeout=10)
        print(f"✅ Mensagem enviada para o WhatsApp de {telefone} | Status: {req.status_code}")
    except Exception as e:
        print(f"⚠️ Falha ao disparar mensagem para WhatsApp: {e}")

# 4. Processamento Cognitivo Dinâmico
def processar_ia_com_contexto(prompt_sistema: str, historico: list[dict]) -> DadosTriagemDinamica:
    contents = []
    for msg in historico:
        contents.append(
            types.Content(
                role=msg["role"],
                parts=[types.Part.from_text(text=msg["text"])]
            )
        )

    response = ai_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=prompt_sistema,
            response_mime_type="application/json",
            response_schema=DadosTriagemDinamica,
            temperature=0.2,
        ),
    )
    return DadosTriagemDinamica.model_validate_json(response.text)

# 5. Endpoint Universal de Recebimento de Webhook
@app.post("/webhook/whatsapp/{api_key}")
async def receber_mensagem_whatsapp(api_key: str, request: Request, background_tasks: BackgroundTasks):
    payload = await request.json()
    
    # 1. Autenticação da Organização
    org_res = supabase.table("organizations").select("*").eq("chave_api_acesso", api_key).execute()
    if not org_res.data:
        raise HTTPException(status_code=403, detail="Chave de API da Organização inválida.")
    
    org = org_res.data[0]
    org_id = org["id"]
    config = org.get("config_triagem") or {}
    prompt_custom = config.get("prompt_customizado", "Você é um atendente virtual educado e objetivo.")

    # 2. Extração flexível dos dados recebidos (Compatível com Evolution API e simuladores)
    telefone = payload.get("telefone")
    mensagem_texto = payload.get("mensagem")

    # Formato padrão Evolution API (caso venha direto da instância)
    if not telefone and "data" in payload:
        data_ev = payload.get("data", {})
        telefone = data_ev.get("key", {}).get("remoteJid", "").split("@")[0]
        mensagem_texto = data_ev.get("message", {}).get("conversation") or data_ev.get("message", {}).get("extendedTextMessage", {}).get("text", "")

    if not telefone or not mensagem_texto:
        return {"status": "ignorado", "motivo": "Payload sem telefone ou texto legível"}

    # 3. Regra de Handoff (Atendente Humano)
    lead_res = supabase.table("leads").select("*").eq("org_id", org_id).eq("telefone", telefone).execute()
    lead_existente = lead_res.data[0] if lead_res.data else None

    if lead_existente and lead_existente.get("status_funil") in ["Em Atendimento", "Proposta Enviada", "Fechado"]:
        return {"status": "ignorado", "motivo": "Lead em atendimento com operador humano"}

    # 4. Histórico recente de mensagens para manter o contexto
    logs_res = supabase.table("interaction_logs").select("*").eq("org_id", org_id).order("created_at", desc=False).limit(6).execute()
    historico = []
    for log in logs_res.data:
        role = "user" if log["origem"] == "cliente" else "model"
        historico.append({"role": role, "text": log["mensagem"]})

    historico.append({"role": "user", "text": mensagem_texto})

    # 5. Execução da IA
    resultado_ia = processar_ia_com_contexto(prompt_custom, historico)

    # 6. Gravação no Supabase
    novo_status = "Triado" if resultado_ia.triagem_concluida else "Em Triagem"
    dados_lead = {
        "org_id": org_id,
        "telefone": telefone,
        "status_funil": novo_status
    }
    if resultado_ia.nome_identificado:
        dados_lead["nome"] = resultado_ia.nome_identificado
    if resultado_ia.tipo_servico:
        dados_lead["tipo_servico"] = resultado_ia.tipo_servico
    if resultado_ia.localizacao_regiao:
        dados_lead["endereco_regiao"] = resultado_ia.localizacao_regiao
    if resultado_ia.resumo_necessidade:
        dados_lead["resumo_necessidade"] = resultado_ia.resumo_necessidade

    res_upsert = supabase.table("leads").upsert(dados_lead, on_conflict="org_id,telefone").execute()
    lead_id = res_upsert.data[0]["id"] if res_upsert.data else (lead_existente["id"] if lead_existente else None)

    if lead_id:
        supabase.table("interaction_logs").insert([
            {"lead_id": lead_id, "org_id": org_id, "origem": "cliente", "mensagem": mensagem_texto},
            {"lead_id": lead_id, "org_id": org_id, "origem": "bot_triagem", "mensagem": resultado_ia.resposta_para_cliente}
        ]).execute()

    # 7. Disparo em segundo plano da resposta ao WhatsApp
    instancia_url = config.get("instancia_url")
    apikey_instancia = config.get("instancia_apikey")
    background_tasks.add_task(enviar_mensagem_whatsapp, instancia_url, apikey_instancia, telefone, resultado_ia.resposta_para_cliente)

    return {
        "status": "sucesso",
        "resposta_gerada": resultado_ia.resposta_para_cliente,
        "triagem_concluida": resultado_ia.triagem_concluida,
        "status_lead": novo_status
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)