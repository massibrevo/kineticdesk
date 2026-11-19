import { useEffect, useRef, useState, type CSSProperties, type FormEvent } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'

type Profile = {
  x_min: number; x_max: number; y_min: number; y_max: number;
  pinch_in: number; pinch_out: number; drag_ms: number;
  smoothing: number; scroll_gain: number; mirrored: boolean; camera: number;
}
type Motion = {
  id: number; kind: string; x: number | null; y: number | null;
  amount: number | null; injected: boolean; interrupted: boolean;
}
type Frame = {
  canOpenAccessibility: boolean; awaitingAccessibility: boolean; trackingInterrupted: boolean;
  source: 'off' | 'camera' | 'replay'; mode: string; reason: string; desktop: boolean;
  position: [number, number]; scanning: boolean; pose: string; armProgress: number; points: number[][] | null;
  aspect: number; preview: string | null; previewEnabled: boolean; events: Motion[];
  device: {platform: string; accessibility: boolean; camera: string}; error: string | null;
  profile: Profile; defaults: Profile; fps: number | null; frameAge: number | null;
  tracking: number | null; latency: [number, number] | null;
}
type Command = (name: string, payload?: Record<string, unknown>) => void
const links = [[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],
  [9,13],[13,14],[14,15],[15,16],[13,17],[17,18],[18,19],[19,20],[0,17]]
const modes: Record<string, string> = {
  ready: 'In attesa del pugno', armed: 'Pronto', pinching: 'Pinza in corso',
  dragging: 'Trascinamento', paused: 'In pausa', stopped: 'Fermo',
}
const reasons: Record<string, string> = {
  palm: 'Palmo rilevato', 'tracking-lost': 'Mano persa', idle: 'Inattività',
  'ui-pause': 'Pausa manuale', 'tab-hidden': 'Scheda nascosta', 'input-error': 'Errore di input',
  'camera-error': 'Errore della fotocamera', 'camera-stalled': 'Fotocamera interrotta',
  'ui-timeout': 'Connessione allo Studio scaduta',
}
const actions: Record<string, string> = {
  move: 'Movimento', click: 'Clic sinistro', down: 'Pulsante premuto',
  up: 'Pulsante rilasciato', scroll: 'Scorrimento',
}
const permissions: Record<string, string> = {
  authorized: 'Concessa', denied: 'Negata', restricted: 'Limitata',
  'not-requested': 'Da richiedere', unknown: 'Sconosciuta',
}
const gestures = [
  ['Scansiona', 'Per controllare il Mac, tieni fermo l’indice durante la scansione. In simulazione chiudi il pugno.'],
  ['Muovi', 'Distendi l’indice verso l’alto e lascia le altre dita rilassate.'],
  ['Clic', 'Dalla posizione di puntamento, unisci pollice e indice, poi rilasciali.'],
  ['Trascina', 'Tieni la pinza finché compare Trascinamento, poi muovi la mano e riapri le dita.'],
  ['Scorri', 'Estendi indice e medio, poi muovili in verticale.'],
  ['Pausa', 'Mostra il palmo aperto. Puoi anche premere Esc.'],
]

function useStudio() {
  const [frame, setFrame] = useState<Frame | null>(null)
  const [status, setStatus] = useState('Connessione…')
  const ws = useRef<WebSocket | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    let heartbeat: number | undefined
    fetch('/api/session', { signal: controller.signal })
      .then(response => {
        if (!response.ok) throw Error()
        return response.json() as Promise<{token: string}>
      })
      .then(({token}) => {
        if (controller.signal.aborted) return
        const socket = new WebSocket('ws://' + location.host + '/ws')
        ws.current = socket
        socket.onopen = () => {
          socket.send(token)
          heartbeat = window.setInterval(() => {
            if (socket.readyState === WebSocket.OPEN) {
              socket.send(JSON.stringify({command: 'heartbeat'}))
            }
          }, 250)
        }
        socket.onmessage = (event: MessageEvent<string>) => {
          setFrame(JSON.parse(event.data) as Frame)
          setStatus('Connesso')
        }
        socket.onclose = event => {
          window.clearInterval(heartbeat)
          if (controller.signal.aborted) return
          setFrame(null)
          setStatus(event.reason || 'Disconnesso. Ricarica lo Studio.')
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setStatus('Servizio locale non raggiungibile.')
      })
    return () => {
      controller.abort()
      window.clearInterval(heartbeat)
      ws.current?.close()
    }
  }, [])
  const send: Command = (command, payload = {}) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({...payload, command}))
    }
  }
  useEffect(() => {
    function emergency(event: KeyboardEvent) {
      if (event.key === 'Escape' && !event.defaultPrevented) send('pause')
    }
    function visibility() {
      if (document.hidden) send('tab-hidden')
    }
    window.addEventListener('keydown', emergency)
    document.addEventListener('visibilitychange', visibility)
    return () => {
      window.removeEventListener('keydown', emergency)
      document.removeEventListener('visibilitychange', visibility)
    }
  }, [])
  return { frame, status, send }
}

function Tracking({ frame }: { frame: Frame | null }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const aspect = frame?.aspect ?? 4 / 3
  useEffect(() => {
    const ctx = canvas.current?.getContext('2d')
    if (!ctx || !canvas.current) return
    const {width, height} = canvas.current
    ctx.clearRect(0, 0, width, height)
    const data = frame?.points
    if (!data) return
    ctx.lineWidth = 2.5
    ctx.strokeStyle = '#62f2d4'
    ctx.fillStyle = '#b5fff0'
    for (const [from, to] of links) {
      ctx.beginPath()
      ctx.moveTo(data[from][0] * width, data[from][1] * height)
      ctx.lineTo(data[to][0] * width, data[to][1] * height)
      ctx.stroke()
    }
    data.forEach(([x, y], index) => {
      ctx.beginPath()
      ctx.arc(x * width, y * height, index === 8 || index === 4 ? 5 : 3, 0, Math.PI * 2)
      ctx.fill()
    })
  }, [frame, aspect])
  const p = frame?.profile
  const starting = frame?.source === 'camera' && frame.frameAge == null
  return <div className="tracking" style={{ aspectRatio: aspect, '--camera-ratio': aspect } as CSSProperties}>
    {frame?.preview && <img alt="Anteprima locale della fotocamera" src={'data:image/jpeg;base64,' + frame.preview}/>}
    {p && <div className="bounds" aria-hidden="true" style={{
      left: p.x_min * 100 + '%', top: p.y_min * 100 + '%',
      width: (p.x_max - p.x_min) * 100 + '%', height: (p.y_max - p.y_min) * 100 + '%',
    }}/>}
    <canvas ref={canvas} width={640} height={Math.round(640 / aspect)} aria-label="Landmark della mano"/>
    {frame?.scanning && frame.points && <div className="scan-line" aria-hidden="true"
      style={{top: (12 + frame.armProgress * 76) + '%'}}/>}
    {!frame?.points && !frame?.preview && <div className="view-empty">
      <strong>{starting ? 'Apertura della fotocamera…' : frame?.source === 'camera' ? 'Nessuna mano rilevata' : frame?.source === 'replay' ? 'Replay completato' : 'Fotocamera spenta'}</strong>
      <span>{starting
        ? 'Attendo il primo fotogramma. Accetta la richiesta di macOS se compare.'
        : frame?.source === 'camera'
          ? 'Inquadra una mano intera e ben illuminata.'
          : frame?.source !== 'replay' && 'Avvia la scansione della mano o guarda la demo.'}</span>
    </div>}
  </div>
}

type PracticeState = {latest: number; clicked: boolean; held: boolean; dropped: boolean; tile: number[]; scroll: number}
const initialPractice: PracticeState = {latest: 0, clicked: false, held: false, dropped: false, tile: [.57,.46], scroll: 0}
function Playground({frame}: {frame: Frame | null}) {
  const [practice, setPractice] = useState(initialPractice)
  const scroll = useRef<HTMLDivElement>(null)
  const events = frame?.events
  useEffect(() => {
    if (!events?.length) {
      setPractice(initialPractice)
      return
    }
    setPractice(previous => {
      const unseen = events.filter(event => event.id > previous.latest)
      if (!unseen.length) return previous
      const next = {...previous}
      for (const event of unseen) {
        next.latest = event.id
        if (event.injected) continue
        const position = event.x !== null && event.y !== null ? [event.x, event.y] : null
        if (event.kind === 'click' && position) {
          const [x, y] = position
          next.clicked ||= x >= .30 && x <= .50 && y >= .25 && y <= .49
        }
        if (event.kind === 'down' && position) {
          next.held = Math.abs(position[0] - next.tile[0]) <= .075 && Math.abs(position[1] - next.tile[1]) <= .11
        }
        if (event.kind === 'up' && next.held) {
          next.held = false
          next.dropped ||= !event.interrupted && next.tile[0] >= .75 && next.tile[0] <= .96 && next.tile[1] >= .12 && next.tile[1] <= .42
        }
        if (event.kind === 'move' && next.held && event.x !== null && event.y !== null) {
          next.tile = [event.x, event.y]
        }
        if (event.kind === 'scroll') next.scroll = Math.max(0, Math.min(135, next.scroll - (event.amount ?? 0) * 14))
      }
      return next
    })
  }, [events])
  useEffect(() => { if (scroll.current) scroll.current.scrollTop = practice.scroll }, [practice.scroll])
  const position = frame?.position ?? [.5,.5]
  return <div className="playground" aria-label="Area prova in simulazione">
    <div className="click-target" data-complete={practice.clicked}>{practice.clicked ? '✓ Clic rilevato' : 'Clic'}</div>
    <div className="drop-target" data-complete={practice.dropped}>{practice.dropped ? '✓ Rilascio' : 'Rilascio'}</div>
    <div className="drag-tile" data-held={practice.held} style={{left: practice.tile[0]*100+'%', top: practice.tile[1]*100+'%'}}>Sposta</div>
    <div className="scroll-box">
      <span>Scorri</span>
      <div className="scroll-window" ref={scroll} aria-label="Distanza di scorrimento">
        <div className="scroll-ruler" aria-hidden="true"/>
      </div>
    </div>
    {frame?.source !== 'off' && frame && <div className="cursor" aria-hidden="true" style={{left: position[0]*100 + '%', top: position[1]*100 + '%'}}/>}
  </div>
}

const numericFields: [keyof Omit<Profile, 'mirrored'>, string, number][] = [
  ['camera', 'Indice fotocamera', 1], ['x_min', 'Bordo sinistro', .01], ['x_max', 'Bordo destro', .01],
  ['y_min', 'Bordo superiore', .01], ['y_max', 'Bordo inferiore', .01],
  ['pinch_in', 'Pinza chiusa', .01], ['pinch_out', 'Pinza aperta', .01],
  ['drag_ms', 'Soglia trascinamento (ms)', 10], ['smoothing', 'Reattività cursore', .01],
  ['scroll_gain', 'Sensibilità scorrimento', 1],
]
function Calibration({profile, frame, send}: {profile: Profile; frame: Frame; send: Command}) {
  const [draft, adjust] = useState(profile)
  const [submitted, setSubmitted] = useState(false)
  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    send('profile', {profile: draft})
    setSubmitted(true)
  }
  return <form className="calibration" onSubmit={save}>
    <h2>Calibrazione</h2>
    <p>Modifica i bordi dell’area attiva da 0 a 1. La distanza di pinza è relativa alla dimensione della mano.</p>
    {frame.source !== 'off' && <p>Ferma la sorgente prima di salvare.</p>}
    <div className="fields">{numericFields.map(([key, label, step]) =>
      <label key={key}>{label}<input type="number" step={step} value={Number.isFinite(draft[key]) ? draft[key] : ''} required
        onChange={event => { setSubmitted(false); adjust({...draft, [key]: event.target.valueAsNumber}) }}/></label>,
    )}</div>
    <label className="check"><input type="checkbox" checked={draft.mirrored} onChange={event => { setSubmitted(false); adjust({...draft, mirrored: event.target.checked}) }}/> Vista a specchio</label>
    <div className="control-buttons">
      <button className="primary" type="submit" disabled={frame.source !== 'off'}>Salva calibrazione</button>
      <button type="button" onClick={() => {setSubmitted(false); adjust(frame.defaults)}}>Ripristina valori</button>
    </div>
    {submitted && !frame.error && JSON.stringify(frame.profile) === JSON.stringify(draft) && <span role="status"> Salvata</span>}
  </form>
}

function App() {
  const {frame, status, send} = useStudio()
  const [tab, setTab] = useState<'studio' | 'calibrazione'>('studio')
  const [expanded, setExpanded] = useState(false)
  const usedFullscreen = useRef(false)
  useEffect(() => {
    function fullscreenChanged() {
      if (document.fullscreenElement === document.documentElement) {
        usedFullscreen.current = true
      } else if (usedFullscreen.current) {
        usedFullscreen.current = false
        setExpanded(false)
      }
    }
    document.addEventListener('fullscreenchange', fullscreenChanged)
    return () => document.removeEventListener('fullscreenchange', fullscreenChanged)
  }, [])

  function toggleWorkspace() {
    setExpanded(!expanded)
    if (expanded && document.fullscreenElement === document.documentElement) {
      void document.exitFullscreen().catch(() => {})
    } else if (!expanded && document.fullscreenEnabled) {
      void document.documentElement.requestFullscreen().catch(() => {})
    }
  }
  const live = frame?.source === 'camera'
  const replay = frame?.source === 'replay'
  const cameraReady = live && frame.frameAge != null
  const cameraLabel = cameraReady ? 'Fotocamera attiva' : 'Fotocamera in avvio'
  const needsAccessibility = frame?.canOpenAccessibility && !frame.device.accessibility
  const running = !!frame && frame.source !== 'off'
  const mode = !running ? 'Fermo' : frame.scanning ? 'Scansione della mano' :
    frame.trackingInterrupted ? 'Riaggancio mano…' :
    frame.desktop && frame.mode === 'armed' ? 'Puntatore attivo' : modes[frame.mode]
  const notable = [...(frame?.events ?? [])].reverse().filter(event => event.kind !== 'move').slice(0, 6)
  return <div className={expanded ? "shell expanded" : "shell"}>
    <header className="top">
      <div className="brand"><span className="logo" aria-hidden="true"><i/><i/><i/></span><span>KineticDesk</span></div>
      <nav aria-label="Sezioni">
        <button className={tab === 'studio' ? 'chosen' : ''} aria-pressed={tab === 'studio'} onClick={() => setTab('studio')}>Studio</button>
        <button className={tab === 'calibrazione' ? 'chosen' : ''} aria-pressed={tab === 'calibrazione'} onClick={() => setTab('calibrazione')}>Calibrazione</button>
      </nav>
      <span className="connection"><i className={frame ? 'online' : ''}/>{frame ? (live ? cameraLabel : 'Servizio locale') : status}</span>
    </header>
    <main>
      <div className="heading">
        <div><h1>{tab === 'studio' ? 'Studio gesti' : 'Profilo di controllo'}</h1>
        <p>Controlla il desktop con la mano. L’elaborazione avviene su questo Mac.</p></div>
        <div className="status" data-mode={running ? frame.mode : 'off'} role="status">
          <i/>{live && !cameraReady ? 'Avvio fotocamera' : mode}
          {frame && (frame.mode === 'paused' || frame.mode === 'stopped') && reasons[frame.reason] ? ' · ' + reasons[frame.reason] : ''}
        </div>
      </div>
      {frame?.error && <div className="alert" role="alert">{frame.error}</div>}
      {needsAccessibility && frame.awaitingAccessibility && <p className="session-hint" role="status">
        macOS non riconosce il permesso per questa copia. Usa Apri Accessibilità per autorizzarla, poi riprova.
      </p>}
      <div className="toolbar" aria-label="Controlli della sessione">
        <button className="primary" disabled={!frame || frame.scanning || frame.desktop}
          onClick={() => send('scan')}>{live ? 'Scansiona per controllare il Mac' : 'Avvia scansione e controllo del Mac'}</button>
        <button disabled={!frame || live} onClick={() => send('camera')}>Solo simulazione</button>
        <button disabled={!frame} onClick={() => send('demo')}>{replay ? 'Ripeti la demo' : 'Demo dei gesti'}</button>
        <span className="toolbar-gap"/>
        <button onClick={toggleWorkspace}>{expanded ? 'Riduci Studio' : 'Espandi Studio'}</button>
        <button disabled={!running || frame.mode === 'paused'} onClick={() => send('pause')}>Pausa <kbd>Esc</kbd></button>
        <button className="danger" disabled={!running} onClick={() => send('stop')}>■ Stop</button>
      </div>
      {tab === 'calibrazione' && frame && <section className="panel"><Calibration profile={frame.profile} frame={frame} send={send}/></section>}
      {tab === 'studio' && <>
        <div className="grid">
          <section className="panel monitor">
            <div className="panel-head">
              <div><h2>Tracciamento</h2><small>{live ? cameraLabel.toUpperCase() : replay ? 'REPLAY SINTETICO' : 'FOTOCAMERA SPENTA'}</small></div>
              {live && <button disabled={!cameraReady} onClick={() => send('preview', {enabled: !frame.previewEnabled})}>{frame.previewEnabled ? 'Nascondi anteprima' : 'Mostra anteprima'}</button>}
            </div>
            {frame?.scanning && <div className="scan-progress">
              <strong>{!cameraReady ? 'Apertura della fotocamera' : !frame.points ? 'Inquadra la mano' : 'Tieni fermo l’indice'}</strong>
              <span>{!cameraReady ? 'L’anteprima locale si apre durante la scansione.' :
                'Distendi l’indice verso l’alto e tienilo fermo per circa mezzo secondo.'}</span>
              <progress aria-label="Scansione della mano" max="1" value={frame.armProgress}/>
            </div>}
            <Tracking frame={frame}/>
            <div className="readings">
              <div><span>Frequenza</span><strong>{frame?.fps?.toFixed(1) ?? '—'}<small> fps</small></strong></div>
              <div><span>Mano rilevata</span><strong>{frame?.tracking != null ? (frame.tracking * 100).toFixed(0) + '%' : '—'}</strong></div>
              <div><span>Età fotogramma</span><strong>{frame?.frameAge != null && frame.frameAge < 500 ? frame.frameAge.toFixed(0) : '—'}<small> ms</small></strong></div>
            </div>
          </section>
          <aside className="panel controls">
            <div className="panel-head"><div><h2>Controllo desktop</h2>
              <small>{frame?.desktop ? 'INPUT DESKTOP ATTIVO' : frame?.scanning ? 'SCANSIONE IN CORSO' : 'SIMULAZIONE · DRY-RUN'}</small></div></div>
            <div className="control-body">
              {cameraReady && <p className="session-hint">{frame.desktop
                ? 'Muovi la mano con l’indice disteso per spostare il puntatore del Mac. Mostra il palmo per mettere in pausa.'
                : frame.scanning
                  ? 'Il puntatore si abilita appena la barra della scansione è piena.'
                  : frame.mode === 'paused'
                    ? 'Scansiona di nuovo la mano per riprendere il controllo del Mac.'
                    : 'In simulazione, chiudi il pugno e poi distendi solo l’indice per muovere il cursore nell’Area prova.'}</p>}
              {frame?.mode === 'ready' && !frame.scanning && (cameraReady || replay) &&
                <div className="arming"><span>Tieni il pugno chiuso per 750 ms</span><progress aria-label="Avanzamento armamento" max="1" value={frame.armProgress}/></div>}
              <dl className="devices">
                <div><dt>Fotocamera</dt><dd>{permissions[frame?.device.camera ?? 'unknown']}</dd></div>
                <div><dt>Accessibilità</dt><dd>{frame?.device.accessibility ? 'Concessa' : 'Da concedere'}</dd></div>
              </dl>
              {frame?.device.platform === 'macOS' ? <p className="permission">{needsAccessibility
                ? 'Per muovere il puntatore, autorizza KineticDesk in Accessibilità.'
                : 'Gestisci i permessi in Impostazioni di Sistema → Privacy e sicurezza.'}</p> :
                <p className="permission">L’input desktop è in anteprima su macOS.</p>}
              <div className="control-buttons">
                {cameraReady && (frame.desktop || frame.mode === 'paused') &&
                  <button onClick={() => send('dry-run')}>{frame.desktop ? 'Torna alla simulazione' : 'Riprendi simulazione'}</button>}
                {needsAccessibility && <button onClick={() => send('open-accessibility')}>Apri Accessibilità</button>}
                <button disabled={!frame} onClick={() => send('permissions')}>Aggiorna permessi</button>
              </div>
              <div className="activity"><h3>Ultime azioni</h3>
                {notable.length === 0 && <p>Nessuna azione ancora.</p>}
                <ul>{notable.map(event => <li key={event.id}><span>{actions[event.kind]}</span><small>{event.injected ? 'Desktop' : 'Dry-run'}{event.amount ? ' · ' + event.amount : ''}</small></li>)}</ul>
              </div>
              {frame?.latency && <p className="permission">Fotogramma → evento OS: mediana {frame.latency[0].toFixed(1)} ms · p95 {frame.latency[1].toFixed(1)} ms</p>}
            </div>
          </aside>
        </div>
        <div className="grid bottom">
          <section className="panel"><div className="panel-head"><div><h2>Area prova</h2><small>INPUT SIMULATO</small></div></div><Playground frame={frame}/></section>
          <section className="panel"><div className="panel-head"><h2>Guida ai gesti</h2></div><dl className="gesture-list">{gestures.map(([name, desc]) => <div key={name}><dt>{name}</dt><dd>{desc}</dd></div>)}</dl></section>
        </div>
      </>}
    </main>
  </div>
}

createRoot(document.getElementById('root')!).render(<App/>)
