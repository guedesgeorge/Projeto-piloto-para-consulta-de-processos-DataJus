---
title: Agente de Consulta Processual
emoji: ⚖️
colorFrom: purple
colorTo: gray
sdk: docker
app_port: 8000
pinned: false
short_description: Consulta processos públicos no DataJud com um agente de IA
---

# ⚖️ Agente de Consulta Processual

Cole o número de um processo judicial público, ou anexe a intimação em PDF, e pergunte do jeito que perguntaria a um colega. O agente consulta a **API pública do DataJud**, do CNJ, e explica a situação em português claro: tribunal, classe, assunto, vara, data de ajuizamento e os últimos andamentos.

Para testar, experimente: *Em que pé está o processo 0000832-35.2018.4.01.3202?*

**Stack:** Python · FastAPI · LangChain · DeepSeek · React · Vite · Docker

## Sobre esta demonstração

- Ela tem um **limite de mensagens por visitante** e um teto diário geral, porque roda com a minha chave do modelo de linguagem. Se o limite estourar, dá pra rodar o projeto na sua máquina com a sua chave.
- O DataJud traz só **metadados de processos públicos**: não vêm os nomes das partes nem o conteúdo das decisões.
- O **texto dos PDFs anexados vai para o modelo de linguagem**. Não anexe nada sigiloso.
- O DataJud às vezes demora ou recusa requisições por excesso de uso. Se a consulta falhar, tente de novo em alguns instantes.

O código, os testes e as instruções para rodar localmente estão no GitHub:
**[guedesgeorge/Projeto-piloto-para-consulta-de-processos-DataJus](https://github.com/guedesgeorge/Projeto-piloto-para-consulta-de-processos-DataJus)**

---

Feito por **George Emannuel Guedes de Carvalho** · [GitHub](https://github.com/guedesgeorge) · [LinkedIn](https://www.linkedin.com/in/george-guedes)
