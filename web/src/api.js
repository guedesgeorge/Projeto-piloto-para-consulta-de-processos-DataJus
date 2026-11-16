// Chamadas ao backend (FastAPI). Em desenvolvimento, o Vite repassa /api para a porta 8000.

export async function carregarConfig() {
  const r = await fetch('/api/config');
  if (!r.ok) throw new Error('Não foi possível carregar a configuração.');
  return r.json();
}

export async function lerAnexo(arquivo) {
  const dados = new FormData();
  dados.append('arquivo', arquivo);
  const r = await fetch('/api/anexos', { method: 'POST', body: dados });
  const corpo = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(corpo.detail || `Falha ao ler ${arquivo.name}.`);
  return corpo;
}

/**
 * Envia a conversa ao agente e chama `aoReceber(evento)` para cada evento do streaming
 * (consulta_inicio, consulta, texto, erro, fim).
 */
export async function conversar({ mensagens, modelo, signal, aoReceber }) {
  const r = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mensagens, modelo }),
    signal,
  });
  if (!r.ok) {
    const corpo = await r.json().catch(() => ({}));
    const detalhe = Array.isArray(corpo.detail) ? corpo.detail.map((d) => d.msg).join('; ') : corpo.detail;
    throw new Error(detalhe || `Erro ${r.status} no servidor.`);
  }

  const leitor = r.body.getReader();
  const decodificador = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { value, done } = await leitor.read();
    if (done) break;
    buffer += decodificador.decode(value, { stream: true });
    const blocos = buffer.split('\n\n');
    buffer = blocos.pop();
    for (const bloco of blocos) {
      const linha = bloco.split('\n').find((l) => l.startsWith('data: '));
      if (linha) aoReceber(JSON.parse(linha.slice(6)));
    }
  }
}
