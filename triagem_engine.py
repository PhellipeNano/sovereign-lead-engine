import os
import json
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

# 1. Definição do Schema de Dados Estruturados com Pydantic
class DadosTriagemCliente(BaseModel):
    resposta_para_cliente: str = Field(
        description="Mensagem educada, natural, cordial, humanizada e direta que será enviada para o WhatsApp do cliente."
    )
    nome_identificado: str | None = Field(
        default=None, 
        description="Nome ou razão social informado pelo cliente. Manter None se não informado."
    )
    tipo_servico: str | None = Field(
        default=None, 
        description="Tipo de serviço ou produto procurado (ex: Calhas, Rufos, Pingadeiras, Coifas, Estrutura)."
    )
    localizacao_regiao: str | None = Field(
        default=None, 
        description="Bairro, cidade ou endereço da obra/instalação."
    )
    resumo_necessidade: str | None = Field(
        default=None, 
        description="Breve resumo técnico da necessidade do cliente."
    )
    triagem_concluida: bool = Field(
        description="True se coletou ao menos o nome/empresa, o tipo de serviço e a localização/bairro aproximado. False se ainda falta alguma informação essencial."
    )

# 2. Configuração do Cliente da API
# Defina sua variável de ambiente GEMINI_API_KEY ou insira a chave aqui para testes
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyD5qfUcNeDNWZ9LA2LetmJG53Uw1RDR488")
client = genai.Client(api_key=GEMINI_API_KEY)

# 3. Prompt de Sistema Especializado para a ACOTEk
SYSTEM_INSTRUCTION = """
Você é a atendente virtual especialista da ACOTEk Calhas e Estruturas Metálicas.
Sua única missão é realizar uma triagem rápida, profissional e acolhedora em no máximo 2 a 3 trocas de mensagens.

REGRAS RÍGIDAS:
1. Colete apenas 3 informações essenciais:
   - Nome de quem está falando (ou nome da empresa/obra);
   - Qual serviço ou produto precisa (ex: calhas, rufos, condutores, coifas industriais);
   - Bairro, cidade ou região onde será a entrega/instalação.
2. NUNCA passe valores fixos, tabelas de preço ou prometa prazos. Explique gentilmente que o consultor técnico especialista receberá os dados para gerar o orçamento personalizado.
3. Quando tiver as 3 informações, encerre com uma mensagem cordial avisando que a equipe técnica já recebeu a solicitação e assumirá o atendimento a seguir. Marque `triagem_concluida = true`.
4. Responda em tom profissional, caloroso e conciso. Evite textos longos.
"""

def processar_mensagem_triagem(historico_mensagens: list[dict]) -> DadosTriagemCliente:
    """
    Recebe a lista de histórico no formato:
    [{"role": "user"|"model", "parts": [{"text": "..."}]}]
    Retorna o objeto estruturado com a resposta e os dados extraídos.
    """
    # Converte o histórico para o formato do SDK oficial
    contents = []
    for msg in historico_mensagens:
        contents.append(
            types.Content(
                role=msg["role"],
                parts=[types.Part.from_text(text=msg["text"])]
            )
        )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=DadosTriagemCliente,
            temperature=0.2, # Baixa temperatura para precisão analítica e factual
        ),
    )

    # Converte a saída JSON estrita no modelo Pydantic
    dados = DadosTriagemCliente.model_validate_json(response.text)
    return dados

# ----------------- SIMULADOR INTERATIVO NO TERMINAL -----------------
if __name__ == "__main__":
    print("==========================================================")
    print("  SIMULADOR DE TRIAGEM WHATSAPP — SOVEREIGN ENGINE       ")
    print("  (Digite 'sair' para encerrar a conversa)               ")
    print("==========================================================\n")

    historico = []

    while True:
        mensagem_usuario = input("Cliente (WhatsApp): ")
        if mensagem_usuario.strip().lower() in ["sair", "exit"]:
            break

        historico.append({"role": "user", "text": mensagem_usuario})

        resultado = processar_mensagem_triagem(historico)
        
        # Registra a resposta da IA no histórico para contextualizar a conversa
        historico.append({"role": "model", "text": resultado.resposta_para_cliente})

        print(f"\nACOTEk Bot: {resultado.resposta_para_cliente}\n")
        print("--- [DADOS EXTRAÍDOS EM TEMPO REAL] ---")
        print(f"• Nome: {resultado.nome_identificado}")
        print(f"• Serviço: {resultado.tipo_servico}")
        print(f"• Localização: {resultado.localizacao_regiao}")
        print(f"• Resumo: {resultado.resumo_necessidade}")
        print(f"• Status da Triagem Concluída?: {resultado.triagem_concluida}")
        print("-----------------------------------------\n")

        if resultado.triagem_concluida:
            print("🚀 [SISTEMA]: Triagem finalizada! Pronto para envio ao Supabase e notificação da equipe técnica.\n")
            break