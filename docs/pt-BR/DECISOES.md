# Decisões

Oito escolhas moldaram o Pulso+. Cada entrada declara a decisão, as alternativas consideradas e o que ela custa.

## 1. Streamlit em vez de frontend separado

A interface é uma página Streamlit, não uma aplicação React sobre um serviço FastAPI.

A alternativa era a separação convencional, e ela produziria um produto melhor para uma equipe e pior para esta fase. O estado que importa aqui é uma sessão única segurando um formulário, uma trilha e uma saída, e o Streamlit entrega esse estado de graça com renderização no servidor e sem build de cliente. O custo é real: o controle de layout é grosseiro, as três colunas são um compromisso em telas estreitas, e não há interatividade de cliente além dos widgets. Para uma ferramenta clínica que é lida, não operada, a troca era aceitável.

A decisão é reversível na direção que importa. O pacote de domínio não importa Streamlit, então uma superfície FastAPI sobre as mesmas ferramentas é um adaptador novo, não reescrita.

## 2. Um modelo com ferramentas em vez de um modelo que responde

A lógica clínica vive em seis funções, e o modelo as orquestra. A alternativa, um prompt longo com o protocolo embutido e um esquema de saída estruturada, seria mais rápida de construir e impossível de auditar.

Com ferramentas, a trilha mostra quais limiares foram aplicados e com quais entradas, e o revisor consegue recalcular qualquer valor. A contribuição do modelo fica reduzida a seleção e explicação, que é justamente o que um modelo de linguagem faz bem: ler um caso desorganizado, notar que falta um perfil lipídico e escolher a próxima checagem.

O custo é latência e uma nova superfície de falha. Cada chamada é uma ida e volta, e um modelo que chama a ferramenta errada na ordem errada produz uma trilha que parece completa e responde a outra pergunta. O orçamento de seis turnos e dezesseis chamadas limita o segundo problema sem resolvê-lo.

## 3. O portão de sinais de alarme fora do modelo

A checagem coronariana é uma função que roda antes do contato com o endpoint, não uma instrução no prompt.

A alternativa era dizer ao modelo, em termos fortes, que dor torácica com marcadores elevados exige encaminhamento de emergência. Modelos seguem esse tipo de instrução na maior parte do tempo, e "na maior parte do tempo" é a quantidade errada para uma decisão de triagem. Levar a checagem para o código torna o comportamento testável e transforma o modo de falha em recusa, não em parágrafo confiante.

O custo é escopo. Um portão em código cobre o que ele enumera, e a enumeração é curta. Um modelo com instrução ampla poderia capturar uma apresentação que o portão não captura, e é exatamente por isso que o portão é descrito como estreito na documentação, não como camada geral de segurança.

## 4. PREVENT portado, não chamado

O modelo de risco de dez anos é implementado em Python a partir de coeficientes publicados, não consumido de uma API.

Um port é determinístico, testável e offline, e a interface pode declarar a procedência e o limite de calibração junto ao número. Uma API seria menos código e mais dependências, e tornaria o escore indisponível sempre que a rede estivesse.

O custo é manutenção. Uma atualização de coeficiente na origem é mudança de código aqui, e não existe sinal automático de que aconteceu. O escore alternativo para a população brasileira não existe em forma portável, e é por isso que a saída carrega a ressalva de calibração em vez de um modelo melhor.

## 5. OCR local, revisão obrigatória

A extração roda no processo, com Tesseract e Poppler, e o resultado é sempre proposta que o profissional confirma.

A alternativa era enviar o documento ao modelo e deixar que ele lesse. Isso é mais capaz e pior em dois eixos: o documento sai da aplicação, e a extração se torna não verificável, porque a leitura do modelo sobre um laudo é uma frase, não um campo. Um parser que reconhece um conjunto pequeno de padrões e recusa o resto é mais sem graça e auditável.

O custo é cobertura. Manuscrito, digitalização torta e layout incomum produzem campos vazios. O formulário torna isso visível, e o profissional digita o valor, que é o mesmo trabalho de antes do recurso existir e nunca pior.

## 6. Aceite apenas no estado da sessão

Não existe banco, exportação ou integração com prontuário. O estado aceito vive na sessão.

Foi a única escolha defensável para uma demonstração que não autentica ninguém. Uma ferramenta que guarda dado de paciente sem identidade, política de retenção e controle de acesso é passivo, e adicionar armazenamento para a demonstração parecer completa seria a direção errada. A ausência está documentada como limite, não apresentada como recurso de privacidade.

O custo é que o produto não pode ser usado em fluxo real. Isso é exato: não pode.

## 7. O modo público não tem chave de fallback

A flag de publicação desativa o carregamento de `.env` e a chave global, então uma instância pública sem chave de sessão não consegue chamar o motor.

A alternativa, uma chave compartilhada com limite de taxa, é o atalho usual e o que vaza primeiro. Fazer o build público ficar inerte sem chave por sessão significa que a demonstração não pode virar proxy anônimo da cota de outra pessoa.

O custo é atrito: quem quer testar o fluxo completo precisa de uma chave. As capturas de tela existem por isso.

## 8. Publicar a taxa de divergência

O resultado do benchmark, 40 por cento de concordância em 50 casos sintéticos, está no README.

A alternativa é publicar só o que favorece o sistema: a contagem de testes, a ausência de erro crítico, o portão. A taxa de concordância é o número que um clínico pediria primeiro, e omiti-lo tornaria suspeita qualquer outra afirmação do repositório.

O custo é que o projeto lê como menos pronto do que poderia. É a impressão correta. Uma ferramenta de apoio que concorda com uma referência cuidadosa quatro vezes em dez é um segundo leitor, e o repositório deve dizer isso antes que alguém descubra em uso.
