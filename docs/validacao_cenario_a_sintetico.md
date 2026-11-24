# Pulso+ — validação do Cenário A sintético

Data: 3 de novembro de 2026. Este documento relata um caso integralmente fictício de QA, não um paciente nem validação clínica populacional.

## Entrada e premissas

Os valores aprovados foram preservados: homem de 55 anos, não fumante, IMC 26, eGFR 90, colesterol total 190, HDL 50, sem diabetes e sem estatina; PA 145/95 e 148/96. Para completar a fixture, foram declaradas premissas sintéticas adicionais: aferições em 20/10/2026 e 03/11/2026; sem DCV prévia, gestação ou suspeita de hipertensão secundária; assintomático; esquema fictício **em uso** de losartana 50 mg uma vez ao dia; creatinina 1,0 e potássio 4,3. Não se trata de nova prescrição. Troponina e CK-MB não foram inventados nem classificados como negativos.

A fixture única está em `tests/fixtures/cenario_rotina_sintetico.json`. Os 50 casos do benchmark original e seus gabaritos não foram alterados.

## Resultado real

| Item | Resultado observado |
|---|---|
| Classificação da PA | HAS estágio 1 |
| Confirmação operacional do app | Duas aferições válidas em datas distintas |
| PREVENT-CVD de 10 anos | 7,79%, risco intermediário |
| Red Flag | Nenhum gatilho detectado com os dados fornecidos; exames ausentes não são negativos |
| Conduta do motor após validação | `ajustar_dose` — avaliar possível ajuste com o profissional |
| Confiança | Média |
| Pendência impeditiva para revisão adicional | Não, neste teste |
| Revisão profissional de rotina | Sempre obrigatória |
| Botão Aceitar Sugestão | Ativo para a saída vigente, com confirmação de revisão |
| Efeito do clique | Somente registro em session state; sem prescrição, dose nova ou prontuário |

Foi executado o motor real pela UI de teste Streamlit e pelo navegador Chromium. Não houve mock de decisão clínica, replay fabricado, nova dose proposta, remoção de guardrail ou override de `necessita_revisao_humana`. Os mocks existentes na suíte são apenas testes unitários de UI e não embasaram a evidência clínica acima.

## Falhas detectadas e correções

O primeiro resultado foi âmbar apesar de PREVENT completo: uma menção farmacológica livre foi suprimida pelo guardrail. O prompt restringia nomes/doses apenas no detalhe, enquanto o código restringia também situação e justificativa. O prompt foi alinhado aos três campos; o bloqueio Python permaneceu intacto.

Na execução seguinte pela UI, o modelo ainda marcou revisão por confundir a avaliação profissional sempre obrigatória com o flag de pendência impeditiva. O contrato passou a distinguir esses conceitos explicitamente, sem exigir conduta, confiança ou cor específica. O modelo então retornou `ajustar_dose`, com confiança média, sem pendências; o backend validou a resposta. Acrescentou-se também instrução de não descrever biomarcadores ausentes como normais.

As execuções anteriores foram preservadas como evidência de diagnóstico. O resultado verde é de um teste pós-correção de contrato, não uma garantia de repetição ou evidência de acurácia sobre 50 casos. Qualquer novo alerta ou incerteza pode legitimamente produzir âmbar/vermelho.

## Segurança do aceite e testes

O botão exige saída elegível, trilha determinística executada, confirmação de aferições, medicamentos/contraindicações auditados e revisão profissional. Alterar um campo ou retirar a confirmação invalida análise e aceite. Limpar, sair, reanalisar ou trocar/remover configuração também invalidam a revisão anterior. Alertas e pendências desativam aceite.

Passaram 46 testes automatizados da cópia de publicação, incluindo bloqueio vermelho/âmbar, trilha incompleta, dados faltantes, retirada de confirmação, logout e troca de configuração. No navegador foram verificados isolamento entre sessões, Red Flag pré-motor, aceite local e edição posterior. Não houve erros de página; desktop 1440, notebook 1024, tablet 820 e mobile 390 não apresentaram overflow horizontal.

A compilação de produção e o manifesto de hashes foram regenerados e verificados. Backend `agent.py`, `tools.py`, `prevent.py` e `schemas.py` são idênticos ao checkpoint clínico anterior; as alterações são de UI/revisão e explicitação do contrato do prompt. Não foram copiados segredos para runtime, fixture, docs ou imagem de publicação.

## Estado da entrega
O botão de aceite está implementado e verificado neste snapshot, com o comportamento descrito acima.

A demonstração usa somente dados sintéticos. Não constitui produto aprovado para uso assistencial, certificação LGPD, validação clínica, prescrição ou garantia de disponibilidade 24/7. O benchmark de 50 casos não foi reexecutado nem alterado; suas métricas anteriores continuam separadas desta prova funcional.
