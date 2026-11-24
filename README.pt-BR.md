# Pulso+

Código-fonte do Pulso+, uma aplicação de apoio à decisão clínica em hipertensão na atenção primária brasileira. O profissional preenche um formulário estruturado, um agente com LLM raciocina sobre ele usando seis ferramentas determinísticas, e o resultado chega como sugestão para revisão, nunca como prescrição.

A prestação de contas de engenharia do produto, com as decisões, o desenho de segurança e a avaliação, está em [case-study](case-study/README.pt-BR.md).

**English:** [README.md](README.md)

## Escopo

Este repositório é publicado para leitura, estudo e revisão. O Pulso+ é uma demonstração, não um dispositivo médico: não tem registro em órgão regulador, não foi validado contra prontuários reais, e o modo de publicação pública não autentica identidade institucional. Não deve receber dados de pacientes reais.

O snapshot é a aplicação como foi desenvolvida e validada, incluindo o prompt operacional e a suíte de testes. Não é uma release empacotada: ele espera o ambiente para o qual foi construído, descrito abaixo, e a camada de autenticação de sessão é específica de cada implantação, então você fornece a sua.

## Como funciona

O `app.py` renderiza uma página em três colunas e é dono da sessão. O domínio vive em `src/has_cdss/`, sem importação de Streamlit dentro dele. O laço do agente chama um endpoint de chat compatível com OpenAI com definições de ferramenta, executa as ferramentas localmente e termina na mensagem final, em seis turnos ou em dezesseis chamadas. Antes de qualquer chamada de rede, um portão de pré-voo inspeciona os exames: troponina ou CK-MB elevadas encerram a passagem com declaração de emergência e marcação para revisão humana.

As seis ferramentas são `verificar_red_flags_infarto`, `classificar_pa`, `verificar_confirmacao_pa`, `estratificar_risco_cardio`, `verificar_medicamento_sus` e `checar_contraindicacao`. Cada uma recebe um modelo Pydantic e devolve outro, então a trilha de raciocínio pode ser renderizada como dado e os guardrails conseguem comparar o texto do modelo com o que as ferramentas realmente produziram.

O risco cardiovascular é um port determinístico do PREVENT-CVD de dez anos (modelo-base), com os coeficientes da implementação pública PyPREVENT. A saída declara a procedência do modelo e o fato de não ser calibrado para a população brasileira.

O botão de aceite só fica disponível quando a saída é elegível e a trilha está completa, e o aceite é registrado no estado da sessão. Não há banco de dados, exportação para prontuário nem persistência além da sessão.

## Estrutura

| Caminho | Conteúdo |
| --- | --- |
| `app.py` | Página, formulário, três colunas, estado da sessão, fluxo de aceite |
| `src/has_cdss/agent.py` | Laço do agente, despacho de ferramentas, orçamento, resolução do prompt, parse da saída |
| `src/has_cdss/tools.py` | As seis ferramentas clínicas |
| `src/has_cdss/prevent.py` | Modelo PREVENT-CVD de dez anos |
| `src/has_cdss/schemas.py` | Modelos Pydantic do caso, dos resultados e da saída final |
| `src/has_cdss/clinical_parser.py` | Extração conservadora de texto e de saída de OCR |
| `src/has_cdss/public_network.py` | Guarda de saída: HTTPS, porta 443, endereço público, IP fixado, sem proxy ambiente |
| `src/has_cdss/ui_review.py` | Estado de revisão e elegibilidade do aceite |
| `src/has_cdss/config.py` | Resolução de configuração e a flag de publicação pública |
| `prompts/system_prompt.md` | Instrução operacional do agente |
| `tests/` | Testes unitários e de regressão, mais a fixture sintética |
| `deploy/` | Entrada do contêiner, template do proxy reverso, verificação do artefato |
| `docs/` | Relatório de validação do caso sintético, com capturas |

## Requisitos

Python 3.12. Tesseract com dados de português e Poppler para extração local de PDFs e imagens. Nginx para a entrada de implantação em `deploy/`, ou qualquer proxy reverso na frente do Streamlit. Um endpoint de chat compatível com OpenAI que suporte tool calling.

```
pip install -r requirements.txt
```

## Configuração

| Variável | Função |
| --- | --- |
| `LLM_API_KEY` | Credencial do endpoint de chat |
| `LLM_BASE_URL` | URL base do endpoint compatível com OpenAI |
| `LLM_MODEL_NAME` | Nome do modelo, que precisa suportar tool calling |
| `PULSO_PUBLIC_DEPLOY` | `1` desativa o carregamento de `.env` e a chave de fallback, então a sessão precisa fornecer a própria configuração |
| `PORT` | Porta pública usada pelo proxy reverso, 3000 por padrão |
| `PULSO_INTERNAL_PORT` | Porta interna do Streamlit, 8502 por padrão |

Segredos pertencem à sessão ou ao ambiente da implantação. Nada é lido de arquivo versionado aqui.

## Execução

```
python -m streamlit run app.py
```

Para a entrada em contêiner, o `deploy/start.sh` verifica o artefato, renderiza a configuração do proxy, sobe o Streamlit na porta interna e coloca o nginx à frente.

## Testes

```
python -m unittest discover -s tests
```

A suíte cobre os estágios de pressão nas fronteiras, a regra de confirmação, o modelo de risco contra valores de referência, a matriz de contraindicação, o portão de sinais de alarme, os esquemas, a guarda de saída e as regras de aceite. Roda offline, com o endpoint em mock.

## Desenho de segurança

O portão de sinais de alarme roda antes do modelo, então um caso cardíaco não pode ser respondido como caso de hipertensão. Limiares, aritmética de risco e contraindicações são código, não texto de prompt. Invariantes aplicados à saída do modelo removem qualquer nome de fármaco ou dose que uma ferramenta não tenha devolvido. O aceite exige saída elegível, trilha completa e confirmação humana explícita.

O caso de validação sintético, com os valores, a trilha e as capturas, está em [docs/validacao_cenario_a_sintetico.md](docs/validacao_cenario_a_sintetico.md). O benchmark de cinquenta casos sintéticos e os limites da avaliação estão descritos no repositório do estudo de caso.

## Licença

MIT. Ver [LICENSE](LICENSE).

---

Hay Beaumont, Arquiteto de Software e Engenheiro. [github.com/yahbeaumont](https://github.com/yahbeaumont)
