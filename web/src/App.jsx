import { useEffect, useMemo, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { HugeiconsIcon } from '@hugeicons/react';
import {
  Alert02Icon,
  ArrowDown01Icon,
  CheckmarkCircle02Icon,
  Delete02Icon,
  JusticeScale01Icon,
  Key01Icon,
  Loading03Icon,
  MessageAdd01Icon,
  Pdf01Icon,
} from '@hugeicons/core-free-icons';
import PromptBar from './PromptBar';
import { carregarConfig, conversar, lerAnexo } from './api';

const NOMES_MODELOS = {
  'deepseek-flash': { name: 'DeepSeek Flash', tag: 'Rápido' },
  'deepseek-v4-pro': { name: 'DeepSeek V4 Pro', tag: 'Preciso' },
};

const COMANDOS = [
  { key: 'nova', name: '/nova', description: 'Começar uma conversa nova' },
  { key: 'resumo', name: '/resumo', description: 'Resumir a conversa até aqui' },
];

const FONTES = [
  { key: 'pdf', name: 'Anexar PDF', description: 'Intimação, petição ou decisão', icon: Pdf01Icon, attach: true, accept: 'application/pdf,.pdf' },
];

// A chave do visitante fica só no navegador dele. O armazenamento pode falhar
// (navegação privada, iframe bloqueado), então tudo vai dentro de try/catch.
const CHAVE_LOCAL = 'acp:chave-llm';
function lerChaveSalva() {
  try { return localStorage.getItem(CHAVE_LOCAL) || ''; } catch { return ''; }
}
function salvarChave(valor) {
  try {
    if (valor) localStorage.setItem(CHAVE_LOCAL, valor);
    else localStorage.removeItem(CHAVE_LOCAL);
  } catch { /* sem armazenamento: a chave vale só enquanto a página estiver aberta */ }
}

let proximoId = 1;
const novoId = () => proximoId++;

export default function App() {
  const [mensagens, setMensagens] = useState([]);
  const [busy, setBusy] = useState(false);
  const [modelos, setModelos] = useState([]);
  const [aviso, setAviso] = useState('');
  const [chave, setChave] = useState(lerChaveSalva);
  const [chaveServidor, setChaveServidor] = useState(true);
  const [painelChave, setPainelChave] = useState(false);
  const controller = useRef(null);
  const fimRef = useRef(null);
  const listaRef = useRef(null);
  const colado = useRef(true); // o usuário está no fim da conversa?

  useEffect(() => {
    carregarConfig()
      .then(({ modelos, chave_servidor }) => {
        setModelos(modelos.map((key) => ({ key, ...(NOMES_MODELOS[key] ?? { name: key }) })));
        setChaveServidor(chave_servidor !== false);
      })
      .catch(() => setAviso('Servidor indisponível. Verifique se a API está rodando.'));
  }, []);

  // Rola até o fim enquanto a resposta chega, a menos que o usuário tenha subido a tela
  useEffect(() => {
    if (colado.current) fimRef.current?.scrollIntoView({ block: 'end' });
  }, [mensagens]);

  const modelosBarra = useMemo(() => modelos, [modelos]);

  function atualizarUltima(alterar) {
    setMensagens((atual) => {
      const copia = [...atual];
      copia[copia.length - 1] = alterar({ ...copia[copia.length - 1] });
      return copia;
    });
  }

  function novaConversa() {
    controller.current?.abort();
    setMensagens([]);
    setAviso('');
  }

  const send = async (text, { attachments = [], model }) => {
    setAviso('');

    // Comandos
    if (text === '/nova' || text.startsWith('/nova ')) return novaConversa();
    if (text === '/resumo' || text.startsWith('/resumo ')) {
      if (!mensagens.length) return setAviso('Ainda não há conversa para resumir.');
      text = 'Resuma a nossa conversa até aqui em tópicos curtos, destacando os processos consultados.';
    }

    if (!chaveServidor && !chave) {
      setPainelChave(true);
      return setAviso('Para conversar, informe a sua chave de API do DeepSeek.');
    }

    setBusy(true);
    controller.current = new AbortController();
    colado.current = true;

    // Lê os PDFs anexados
    let anexos = [];
    try {
      anexos = await Promise.all(attachments.map(lerAnexo));
    } catch (e) {
      setAviso(e.message);
      setBusy(false);
      return;
    }

    const pergunta = { id: novoId(), papel: 'user', texto: text, anexos };
    const historico = [...mensagens, pergunta];
    setMensagens([...historico, { id: novoId(), papel: 'assistant', texto: '', consultas: [], pendente: true }]);

    try {
      await conversar({
        mensagens: historico.filter((m) => !m.erro).map(({ papel, texto, anexos }) => ({ papel, texto, anexos: anexos ?? [] })),
        modelo: model?.key,
        chave,
        signal: controller.current.signal,
        aoReceber: (ev) =>
          atualizarUltima((m) => {
            if (ev.tipo === 'texto') m.texto += ev.delta;
            if (ev.tipo === 'consulta_inicio') m.consultas = [...m.consultas, { id: ev.id, numero: ev.numero }];
            if (ev.tipo === 'consulta') m.consultas = m.consultas.map((c) => (c.id === ev.id ? { ...c, ok: ev.ok, resultado: ev.resultado } : c));
            if (ev.tipo === 'erro') m.erro = ev.mensagem;
            if (ev.tipo === 'fim') m.pendente = false;
            return m;
          }),
      });
    } catch (e) {
      let mensagem = e.message;
      if (e.status === 401) setPainelChave(true);
      if (e.status === 429 && !chave) mensagem += ' Se preferir, use a sua própria chave do DeepSeek em "Sua chave", sem limite.';
      atualizarUltima((m) => (e.name === 'AbortError' ? { ...m, interrompida: true } : { ...m, erro: mensagem }));
    } finally {
      atualizarUltima((m) => ({ ...m, pendente: false }));
      setBusy(false);
    }
  };

  const vazio = mensagens.length === 0;

  return (
    <div className="app">
      <header className="topo">
        <div className="marca">
          <span className="marca__icone"><HugeiconsIcon icon={JusticeScale01Icon} size={20} /></span>
          <div>
            <h1>Agente de Consulta Processual</h1>
            <p>Dados públicos do DataJud · CNJ</p>
          </div>
        </div>
        <div className="topo__acoes">
          <button
            type="button"
            className={`botao-fantasma${chave ? ' is-ativo' : ''}`}
            onClick={() => setPainelChave(true)}
            aria-haspopup="dialog"
          >
            <HugeiconsIcon icon={Key01Icon} size={16} /> {chave ? 'Usando sua chave' : 'Sua chave'}
          </button>
          {!vazio && (
            <button type="button" className="botao-fantasma" onClick={novaConversa}>
              <HugeiconsIcon icon={MessageAdd01Icon} size={16} /> Nova conversa
            </button>
          )}
        </div>
      </header>

      {painelChave && (
        <PainelChave
          atual={chave}
          obrigatoria={!chaveServidor}
          aoSalvar={(valor) => {
            setChave(valor);
            salvarChave(valor);
            setPainelChave(false);
            setAviso('');
          }}
          aoFechar={() => setPainelChave(false)}
        />
      )}

      <main
        className="conversa"
        ref={listaRef}
        onScroll={(e) => {
          const el = e.currentTarget;
          colado.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        }}
      >
        {vazio ? (
          <div className="inicio">
            <h2>Pergunte sobre qualquer processo público</h2>
            <p>
              Informe o número no formato <code>NNNNNNN-DD.AAAA.J.TR.OOOO</code> ou anexe um PDF. O agente consulta o DataJud e
              explica a situação do processo.
            </p>
          </div>
        ) : (
          <div className="mensagens">
            {mensagens.map((m) => (m.papel === 'user' ? <MensagemUsuario key={m.id} m={m} /> : <MensagemAgente key={m.id} m={m} />))}
            <div ref={fimRef} />
          </div>
        )}
      </main>

      <footer className="rodape">
        {aviso && <div className="aviso" role="alert"><HugeiconsIcon icon={Alert02Icon} size={16} /> {aviso}</div>}
        <PromptBar
          placeholder="Pergunte sobre um processo…"
          sources={FONTES}
          commands={COMANDOS}
          models={modelosBarra}
          busy={busy}
          onSend={send}
          onStop={() => controller.current?.abort()}
          background="#27272a"
          color="#f5f5f5"
          menuBackground="#323236"
          sparkColor="#b39dff"
          sparkBoost={1}
          width={760}
          radius={16}
          maxRows={5}
          morphDuration={240}
          squash={0.12}
          tilt={8}
          pressScale={0.96}
        />
        <p className="nota">
          Metadados públicos do DataJud: sem nomes das partes nem teor das decisões. O texto de PDFs anexados é enviado ao modelo de linguagem.
        </p>
      </footer>
    </div>
  );
}

function MensagemUsuario({ m }) {
  return (
    <div className="msg msg--usuario">
      <div className="balao">
        {m.anexos?.map((a) => (
          <div className="anexo" key={a.nome}>
            <HugeiconsIcon icon={Pdf01Icon} size={16} />
            <span className="anexo__nome">{a.nome}</span>
            <span className="anexo__info">
              {a.numeros.length ? `${a.numeros.length} processo${a.numeros.length > 1 ? 's' : ''} encontrado${a.numeros.length > 1 ? 's' : ''}` : a.tem_texto === false ? 'sem texto (imagem)' : 'nenhum nº de processo'}
            </span>
          </div>
        ))}
        {m.texto && <p>{m.texto}</p>}
      </div>
    </div>
  );
}

function MensagemAgente({ m }) {
  const esperando = m.pendente && !m.texto && !m.erro;
  const consultando = m.consultas.some((c) => c.ok === undefined);
  return (
    <div className="msg msg--agente">
      <span className="avatar"><HugeiconsIcon icon={JusticeScale01Icon} size={16} /></span>
      <div className="corpo">
        {m.consultas.map((c) => <Consulta key={c.id} c={c} />)}
        {esperando && !consultando && (
          <div className="pensando" aria-live="polite"><span /><span /><span /></div>
        )}
        {m.texto && (
          <div className="markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: (p) => <a {...p} target="_blank" rel="noreferrer" /> }}>
              {m.texto}
            </ReactMarkdown>
            {m.pendente && <span className="cursor" aria-hidden="true" />}
          </div>
        )}
        {m.interrompida && <p className="meta">Resposta interrompida.</p>}
        {m.erro && <p className="erro"><HugeiconsIcon icon={Alert02Icon} size={16} /> {m.erro}</p>}
      </div>
    </div>
  );
}

function Consulta({ c }) {
  const [aberta, setAberta] = useState(false);
  const carregando = c.ok === undefined;
  let dados = null;
  if (c.ok) {
    try { dados = JSON.parse(c.resultado); } catch { /* resultado não é JSON */ }
  }
  const inst = dados?.instancias?.[0];

  return (
    <div className={`consulta${carregando ? ' is-carregando' : c.ok ? ' is-ok' : ' is-erro'}`}>
      <button type="button" className="consulta__topo" onClick={() => !carregando && setAberta(!aberta)} disabled={carregando} aria-expanded={aberta}>
        <span className="consulta__icone">
          <HugeiconsIcon icon={carregando ? Loading03Icon : c.ok ? CheckmarkCircle02Icon : Alert02Icon} size={16} />
        </span>
        <span className="consulta__titulo">
          {carregando ? 'Consultando o DataJud' : c.ok ? 'Consulta ao DataJud' : 'Consulta não concluída'}
          <span className="consulta__numero">{c.numero}</span>
        </span>
        {carregando ? <span className="consulta__dica">pode levar até 1 min</span> : <HugeiconsIcon icon={ArrowDown01Icon} size={16} className={`consulta__seta${aberta ? ' is-aberta' : ''}`} />}
      </button>
      {aberta && (
        <div className="consulta__detalhe">
          {inst ? (
            <dl>
              <dt>Tribunal</dt><dd>{dados.tribunal} · {inst.grau}</dd>
              <dt>Classe</dt><dd>{inst.classe}</dd>
              <dt>Órgão julgador</dt><dd>{inst.orgao_julgador}</dd>
              <dt>Movimentos</dt><dd>{inst.total_movimentos}</dd>
            </dl>
          ) : null}
          <pre>{dados ? JSON.stringify(dados, null, 2) : c.resultado}</pre>
        </div>
      )}
    </div>
  );
}

function PainelChave({ atual, obrigatoria, aoSalvar, aoFechar }) {
  const [valor, setValor] = useState(atual);
  const campo = useRef(null);

  useEffect(() => {
    campo.current?.focus();
    const fechar = (e) => e.key === 'Escape' && aoFechar();
    window.addEventListener('keydown', fechar);
    return () => window.removeEventListener('keydown', fechar);
  }, [aoFechar]);

  const salvar = (e) => {
    e.preventDefault();
    aoSalvar(valor.trim());
  };

  return (
    <div className="painel-fundo" onMouseDown={(e) => e.target === e.currentTarget && aoFechar()}>
      <form className="painel" role="dialog" aria-modal="true" aria-labelledby="painel-titulo" onSubmit={salvar}>
        <h2 id="painel-titulo"><HugeiconsIcon icon={Key01Icon} size={18} /> Sua chave do DeepSeek</h2>
        <p>
          {obrigatoria
            ? 'Esta demonstração usa a sua própria chave: as perguntas são cobradas na sua conta do DeepSeek, a poucos centavos cada.'
            : 'Opcional. Com a sua chave, as perguntas são cobradas na sua conta do DeepSeek e não contam no limite da demonstração.'}
        </p>
        <label htmlFor="campo-chave">Chave de API</label>
        <input
          id="campo-chave"
          ref={campo}
          type="password"
          autoComplete="off"
          spellCheck={false}
          placeholder="sk-..."
          value={valor}
          onChange={(e) => setValor(e.target.value)}
        />
        <p className="painel__nota">
          A chave fica salva só neste navegador. Ela vai junto de cada pergunta e é repassada ao DeepSeek, sem ser guardada no servidor.{' '}
          <a href="https://platform.deepseek.com/api_keys" target="_blank" rel="noreferrer">Criar uma chave</a>
        </p>
        <div className="painel__botoes">
          {atual && (
            <button type="button" className="botao-fantasma botao-perigo" onClick={() => aoSalvar('')}>
              <HugeiconsIcon icon={Delete02Icon} size={16} /> Remover
            </button>
          )}
          <span className="painel__espaco" />
          <button type="button" className="botao-fantasma" onClick={aoFechar}>Cancelar</button>
          <button type="submit" className="botao-primario" disabled={!valor.trim() || valor.trim() === atual}>Salvar</button>
        </div>
      </form>
    </div>
  );
}
