import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { HugeiconsIcon } from '@hugeicons/react';
import {
  ArrowDown01Icon,
  ArrowUp02Icon,
  Cancel01Icon,
  File01Icon,
  Mic01Icon,
  PlusSignIcon,
  StopIcon,
  Tick02Icon,
} from '@hugeicons/core-free-icons';
import './PromptBar.css';

/**
 * Barra de mensagem com menus de fontes, comandos "/" e modelos.
 *
 * onSend(text, { attachments, model, effort, sources }) é chamado ao enviar.
 * Fontes com `attach: true` abrem o seletor de arquivos; as demais funcionam
 * como liga/desliga e chegam em `sources`. Comandos são inseridos no texto
 * (ex.: "/nova") e interpretados por quem usa o componente.
 */
export default function PromptBar({
  placeholder = 'Ask anything',
  sources = [],
  commands = [],
  models = [],
  efforts = [],
  busy = false,
  onSend,
  onStop,
  onAttach,
  onDictate,
  background = '#27272a',
  color = '#f5f5f5',
  menuBackground = '#323236',
  sparkColor = '#b39dff',
  sparkBoost = 1,
  width = 400,
  radius = 16,
  maxRows = 5,
  morphDuration = 240,
  squash = 0.12,
  tilt = 8,
  pressScale = 0.96,
  disabled = false,
}) {
  const [text, setText] = useState('');
  const [files, setFiles] = useState([]);
  const [activeSources, setActiveSources] = useState([]);
  const [model, setModel] = useState(models[0] ?? null);
  const [effort, setEffort] = useState(efforts[1] ?? efforts[0] ?? null);
  const [menu, setMenu] = useState(null); // 'sources' | 'models' | null
  const [cmdIndex, setCmdIndex] = useState(0);
  const [focused, setFocused] = useState(false);
  const [squashing, setSquashing] = useState(false);
  const [pose, setPose] = useState({ x: 0, y: 0 });

  const rootRef = useRef(null);
  const inputRef = useRef(null);
  const fileRef = useRef(null);
  const acceptRef = useRef('');
  const composing = useRef(false);
  const menuId = useId();

  // Mantém o modelo selecionado válido quando a lista muda
  useEffect(() => {
    if (!models.length) return setModel(null);
    setModel((atual) => models.find((m) => m.key === atual?.key) ?? models[0]);
  }, [models]);

  // Menu de comandos: aparece quando o texto começa com "/" e ainda não tem espaço
  const commandQuery = /^\/\S*$/.test(text) ? text.slice(1).toLowerCase() : null;
  const commandMatches = useMemo(
    () => (commandQuery === null ? [] : commands.filter((c) => c.name.toLowerCase().includes(commandQuery))),
    [commandQuery, commands],
  );
  const showCommands = commandMatches.length > 0 && menu === null;
  useEffect(() => setCmdIndex(0), [commandQuery]);

  // Altura automática do campo, até maxRows linhas
  useLayoutEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = 'auto';
    const linha = parseFloat(getComputedStyle(el).lineHeight) || 22;
    el.style.height = `${Math.min(el.scrollHeight, linha * maxRows)}px`;
    el.style.overflowY = el.scrollHeight > linha * maxRows ? 'auto' : 'hidden';
  }, [text, maxRows]);

  // Fecha menus ao clicar fora
  useEffect(() => {
    if (!menu) return;
    const fechar = (e) => rootRef.current && !rootRef.current.contains(e.target) && setMenu(null);
    document.addEventListener('pointerdown', fechar);
    return () => document.removeEventListener('pointerdown', fechar);
  }, [menu]);

  const canSend = !disabled && !busy && (text.trim().length > 0 || files.length > 0);

  function send() {
    if (!canSend) return;
    setSquashing(true);
    setTimeout(() => setSquashing(false), morphDuration);
    onSend?.(text.trim(), {
      attachments: files,
      model,
      effort,
      sources: activeSources,
    });
    setText('');
    setFiles([]);
    setMenu(null);
  }

  function chooseCommand(cmd) {
    setText(`${cmd.name} `);
    inputRef.current?.focus();
  }

  function pickSource(source) {
    if (source.attach) {
      acceptRef.current = source.accept ?? '';
      if (fileRef.current) fileRef.current.accept = acceptRef.current;
      fileRef.current?.click();
    } else {
      setActiveSources((atual) =>
        atual.includes(source.key) ? atual.filter((k) => k !== source.key) : [...atual, source.key],
      );
    }
    setMenu(null);
  }

  function onFiles(e) {
    const novos = Array.from(e.target.files ?? []);
    e.target.value = '';
    if (!novos.length) return;
    setFiles((atual) => [...atual, ...novos]);
    onAttach?.(novos);
    inputRef.current?.focus();
  }

  function onKeyDown(e) {
    if (composing.current) return;
    if (showCommands) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        return setCmdIndex((i) => (i + 1) % commandMatches.length);
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        return setCmdIndex((i) => (i - 1 + commandMatches.length) % commandMatches.length);
      }
      if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey && text.slice(1) !== commandMatches[cmdIndex].name.slice(1))) {
        e.preventDefault();
        return chooseCommand(commandMatches[cmdIndex]);
      }
    }
    if (e.key === 'Escape') {
      setMenu(null);
      if (commandQuery !== null) setText('');
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  // Inclinação 3D seguindo o ponteiro (desligada enquanto se digita, para o texto ficar nítido)
  useEffect(() => {
    if (focused) setPose({ x: 0, y: 0 });
  }, [focused]);

  function onPointerMove(e) {
    if (!tilt || focused || e.pointerType !== 'mouse') return;
    const r = rootRef.current.getBoundingClientRect();
    setPose({
      x: ((e.clientY - r.top) / r.height - 0.5) * -tilt,
      y: ((e.clientX - r.left) / r.width - 0.5) * tilt,
    });
  }

  const style = {
    '--pb-bg': background,
    '--pb-fg': color,
    '--pb-menu-bg': menuBackground,
    '--pb-spark': sparkColor,
    '--pb-boost': sparkBoost,
    '--pb-radius': `${radius}px`,
    '--pb-morph': `${morphDuration}ms`,
    '--pb-press': pressScale,
    '--pb-squash-x': 1 + squash / 2,
    '--pb-squash-y': 1 - squash,
    '--pb-rx': `${pose.x}deg`,
    '--pb-ry': `${pose.y}deg`,
    maxWidth: typeof width === 'number' ? `${width}px` : width,
  };

  const sourceObjs = sources.filter((s) => activeSources.includes(s.key));

  return (
    <div
      ref={rootRef}
      className={`pb${focused ? ' pb--focus' : ''}${busy ? ' pb--busy' : ''}${squashing ? ' pb--squash' : ''}`}
      style={style}
      onPointerMove={onPointerMove}
      onPointerLeave={() => setPose({ x: 0, y: 0 })}
    >
      <div className="pb__spark" aria-hidden="true" />

      <div className="pb__body">
        {(files.length > 0 || sourceObjs.length > 0) && (
          <div className="pb__chips">
            {files.map((f, i) => (
              <span className="pb__chip" key={`${f.name}-${i}`}>
                <HugeiconsIcon icon={File01Icon} size={14} />
                <span className="pb__chip-label" title={f.name}>{f.name}</span>
                <button
                  type="button"
                  className="pb__chip-x"
                  aria-label={`Remover ${f.name}`}
                  onClick={() => setFiles((atual) => atual.filter((_, j) => j !== i))}
                >
                  <HugeiconsIcon icon={Cancel01Icon} size={12} />
                </button>
              </span>
            ))}
            {sourceObjs.map((s) => (
              <span className="pb__chip pb__chip--source" key={s.key}>
                {s.icon && <HugeiconsIcon icon={s.icon} size={14} />}
                <span className="pb__chip-label">{s.name}</span>
                <button type="button" className="pb__chip-x" aria-label={`Desativar ${s.name}`} onClick={() => pickSource(s)}>
                  <HugeiconsIcon icon={Cancel01Icon} size={12} />
                </button>
              </span>
            ))}
          </div>
        )}

        <textarea
          ref={inputRef}
          className="pb__input"
          rows={1}
          value={text}
          placeholder={placeholder}
          disabled={disabled}
          aria-label={placeholder}
          aria-controls={showCommands ? `${menuId}-cmd` : undefined}
          aria-expanded={showCommands}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          onCompositionStart={() => (composing.current = true)}
          onCompositionEnd={() => (composing.current = false)}
        />

        <div className="pb__row">
          <div className="pb__left">
            {sources.length > 0 && (
              <button
                type="button"
                className={`pb__icon-btn${menu === 'sources' ? ' is-open' : ''}`}
                aria-label="Adicionar"
                aria-haspopup="menu"
                aria-expanded={menu === 'sources'}
                onClick={() => setMenu(menu === 'sources' ? null : 'sources')}
              >
                <HugeiconsIcon icon={PlusSignIcon} size={18} />
              </button>
            )}

            {models.length > 0 && model && (
              <button
                type="button"
                className={`pb__pill${menu === 'models' ? ' is-open' : ''}`}
                aria-haspopup="listbox"
                aria-expanded={menu === 'models'}
                onClick={() => setMenu(menu === 'models' ? null : 'models')}
              >
                <span>{model.name}</span>
                {effort && efforts.length > 0 && <span className="pb__pill-sub">· {effort}</span>}
                <HugeiconsIcon icon={ArrowDown01Icon} size={14} className="pb__caret" />
              </button>
            )}
          </div>

          <div className="pb__right">
            {onDictate && (
              <button type="button" className="pb__icon-btn" aria-label="Ditar" onClick={onDictate} disabled={busy}>
                <HugeiconsIcon icon={Mic01Icon} size={18} />
              </button>
            )}
            <button
              type="button"
              className={`pb__send${busy ? ' is-stop' : ''}`}
              aria-label={busy ? 'Parar' : 'Enviar'}
              disabled={!busy && !canSend}
              onClick={busy ? onStop : send}
            >
              <span className="pb__send-icon pb__send-icon--up">
                <HugeiconsIcon icon={ArrowUp02Icon} size={18} strokeWidth={2} />
              </span>
              <span className="pb__send-icon pb__send-icon--stop">
                <HugeiconsIcon icon={StopIcon} size={16} strokeWidth={2} />
              </span>
            </button>
          </div>
        </div>
      </div>

      {menu === 'sources' && (
        <div className="pb__menu" role="menu">
          {sources.map((s) => (
            <button type="button" role="menuitem" className="pb__item" key={s.key} onClick={() => pickSource(s)}>
              {s.icon && <span className="pb__item-icon"><HugeiconsIcon icon={s.icon} size={18} /></span>}
              <span className="pb__item-text">
                <span className="pb__item-name">{s.name}</span>
                {s.description && <span className="pb__item-desc">{s.description}</span>}
              </span>
              {!s.attach && activeSources.includes(s.key) && <HugeiconsIcon icon={Tick02Icon} size={16} />}
            </button>
          ))}
        </div>
      )}

      {menu === 'models' && (
        <div className="pb__menu" role="listbox" aria-label="Modelo">
          {models.map((m) => (
            <button
              type="button"
              role="option"
              aria-selected={m.key === model?.key}
              className="pb__item"
              key={m.key}
              onClick={() => {
                setModel(m);
                if (!efforts.length) setMenu(null);
              }}
            >
              <span className="pb__item-text">
                <span className="pb__item-name">{m.name}</span>
              </span>
              {m.tag && <span className="pb__tag">{m.tag}</span>}
              {m.key === model?.key && <HugeiconsIcon icon={Tick02Icon} size={16} />}
            </button>
          ))}
          {efforts.length > 0 && (
            <div className="pb__efforts" role="radiogroup" aria-label="Esforço">
              {efforts.map((ef) => (
                <button
                  type="button"
                  role="radio"
                  aria-checked={ef === effort}
                  className={`pb__effort${ef === effort ? ' is-on' : ''}`}
                  key={ef}
                  onClick={() => setEffort(ef)}
                >
                  {ef}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {showCommands && (
        <div className="pb__menu" role="listbox" id={`${menuId}-cmd`} aria-label="Comandos">
          {commandMatches.map((c, i) => (
            <button
              type="button"
              role="option"
              aria-selected={i === cmdIndex}
              className={`pb__item${i === cmdIndex ? ' is-active' : ''}`}
              key={c.key}
              onPointerDown={(e) => e.preventDefault()}
              onPointerEnter={() => setCmdIndex(i)}
              onClick={() => chooseCommand(c)}
            >
              <span className="pb__item-text">
                <span className="pb__item-name pb__mono">{c.name}</span>
                {c.description && <span className="pb__item-desc">{c.description}</span>}
              </span>
            </button>
          ))}
        </div>
      )}

      <input ref={fileRef} type="file" multiple hidden onChange={onFiles} />
    </div>
  );
}
