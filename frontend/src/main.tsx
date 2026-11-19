import { useEffect, useRef, useState, type CSSProperties, type FormEvent } from 'react'
import { createRoot } from 'react-dom/client'
import { errorText, translator, type Language, type Message, type Translate } from './i18n'
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
  language: Language; nativeWindow: boolean;
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
const modes: Record<string, Message> = {
  ready: 'waitingForFist', armed: 'ready', pinching: 'pinching', dragging: 'dragging',
  paused: 'paused', stopped: 'stopped',
}
const reasons: Record<string, Message> = {
  palm: 'palmDetected', 'tracking-lost': 'handLost', idle: 'idle',
  'ui-pause': 'pausedManually', 'tab-hidden': 'tabHidden', 'window-hidden': 'windowHidden',
  'input-error': 'inputError', 'camera-error': 'cameraError', 'camera-stalled': 'cameraInterrupted',
  'ui-timeout': 'connectionExpired', 'ui-disconnected': 'connectionEnded',
  'system-suspension': 'systemSuspension',
}
const actions: Record<string, Message> = {
  move: 'movement', click: 'leftClick', down: 'mouseDown', up: 'mouseUp', scroll: 'scrolling',
}
const permissions: Record<string, Message> = {
  authorized: 'granted', denied: 'denied', restricted: 'restricted',
  'not-requested': 'notRequested', unknown: 'unknown',
}
const gestures: [Message, Message][] = [
  ['scan', 'scanGuide'], ['move', 'moveGuide'], ['click', 'clickGuide'],
  ['drag', 'dragGuide'], ['scroll', 'scrollGuide'], ['pause', 'pauseGuide'],
]

function useStudio() {
  const [frame, setFrame] = useState<Frame | null>(null)
  const [status, setStatus] = useState<Message>('connecting')
  const ws = useRef<WebSocket | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    let heartbeat: number | undefined
    let retry: number | undefined
    let backoff = 250

    function scheduleReconnect(occupied = false) {
      if (controller.signal.aborted) return
      setStatus(occupied ? 'studioInUse' : 'reconnecting')
      retry = window.setTimeout(connect, occupied ? Math.max(backoff, 1000) : backoff)
      backoff = Math.min(backoff * 2, 4000)
    }

    async function connect() {
      try {
        const response = await fetch('/api/session', {signal: controller.signal})
        if (!response.ok) throw Error()
        const {token} = await response.json() as {token: string}
        if (controller.signal.aborted) return
        const socket = new WebSocket('ws://' + location.host + '/ws')
        ws.current = socket
        let preview: string | null = null
        socket.onopen = () => socket.send(token)
        socket.onmessage = (event: MessageEvent<string>) => {
          const snapshot = JSON.parse(event.data) as Omit<Frame, 'preview'> & {preview?: string | null}
          if (snapshot.preview !== undefined) preview = snapshot.preview
          setFrame({...snapshot, preview})
          backoff = 250
          if (!snapshot.nativeWindow && heartbeat === undefined) {
            const sendHeartbeat = () => {
              if (socket.readyState === WebSocket.OPEN) socket.send('{"command":"heartbeat"}')
            }
            sendHeartbeat()
            heartbeat = window.setInterval(sendHeartbeat, 250)
          }
        }
        socket.onclose = event => {
          window.clearInterval(heartbeat)
          heartbeat = undefined
          ws.current = null
          if (controller.signal.aborted) return
          setFrame(null)
          scheduleReconnect(event.code === 1008 && event.reason === 'studio-in-use')
        }
      } catch {
        scheduleReconnect()
      }
    }
    void connect()
    return () => {
      controller.abort()
      window.clearInterval(heartbeat)
      window.clearTimeout(retry)
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
  return {frame, status, send}
}

function Tracking({frame, t}: {frame: Frame | null; t: Translate}) {
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
    {frame?.preview && <img alt={t('previewAlt')} src={'data:image/jpeg;base64,' + frame.preview}/>}
    {p && <div className="bounds" aria-hidden="true" style={{
      left: p.x_min * 100 + '%', top: p.y_min * 100 + '%',
      width: (p.x_max - p.x_min) * 100 + '%', height: (p.y_max - p.y_min) * 100 + '%',
    }}/>}
    <canvas ref={canvas} width={640} height={Math.round(640 / aspect)} aria-label={t('handLandmarks')}/>
    {frame?.scanning && frame.points && <div className="scan-line" aria-hidden="true"
      style={{top: (12 + frame.armProgress * 76) + '%'}}/>}
    {!frame?.points && !frame?.preview && <div className="view-empty">
      <strong>{starting ? t('openingCamera') : frame?.source === 'camera' ? t('noHand') : frame?.source === 'replay' ? t('replayComplete') : t('cameraOff')}</strong>
      <span>{starting
        ? t('firstFrame')
        : frame?.source === 'camera'
          ? t('frameOneHand')
          : frame?.source !== 'replay' && t('startOrDemo')}</span>
    </div>}
  </div>
}

type PracticeState = {latest: number; clicked: boolean; held: boolean; dropped: boolean; tile: number[]; scroll: number}
const initialPractice: PracticeState = {latest: 0, clicked: false, held: false, dropped: false, tile: [.57,.46], scroll: 0}
function Playground({frame, t}: {frame: Frame | null; t: Translate}) {
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
  return <div className="playground" aria-label={t('practiceLabel')}>
    <div className="click-target" data-complete={practice.clicked}>{practice.clicked ? t('clickDetected') : t('click')}</div>
    <div className="drop-target" data-complete={practice.dropped}>{practice.dropped ? t('dropDetected') : t('drop')}</div>
    <div className="drag-tile" data-held={practice.held} style={{left: practice.tile[0]*100+'%', top: practice.tile[1]*100+'%'}}>{t('moveTile')}</div>
    <div className="scroll-box">
      <span>{t('scroll')}</span>
      <div className="scroll-window" ref={scroll} aria-label={t('scrollDistance')}>
        <div className="scroll-ruler" aria-hidden="true"/>
      </div>
    </div>
    {frame?.source !== 'off' && frame && <div className="cursor" aria-hidden="true" style={{left: position[0]*100 + '%', top: position[1]*100 + '%'}}/>}
  </div>
}

const numericFields: [keyof Omit<Profile, 'mirrored'>, Message, number][] = [
  ['camera', 'cameraIndex', 1], ['x_min', 'leftEdge', .01], ['x_max', 'rightEdge', .01],
  ['y_min', 'topEdge', .01], ['y_max', 'bottomEdge', .01],
  ['pinch_in', 'closedPinch', .01], ['pinch_out', 'openPinch', .01],
  ['drag_ms', 'dragThreshold', 10], ['smoothing', 'responsiveness', .01],
  ['scroll_gain', 'scrollSensitivity', 1],
]
function Calibration({profile, frame, send, t}: {profile: Profile; frame: Frame; send: Command; t: Translate}) {
  const [draft, adjust] = useState(profile)
  const [submitted, setSubmitted] = useState(false)
  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    send('profile', {profile: draft})
    setSubmitted(true)
  }
  return <form className="calibration" onSubmit={save}>
    <h2>{t('calibration')}</h2>
    <p>{t('calibrationDescription')}</p>
    {frame.source !== 'off' && <p>{t('stopBeforeSave')}</p>}
    <div className="fields">{numericFields.map(([key, label, step]) =>
      <label key={key}>{t(label)}<input type="number" step={step} value={Number.isFinite(draft[key]) ? draft[key] : ''} required
        onChange={event => { setSubmitted(false); adjust({...draft, [key]: event.target.valueAsNumber}) }}/></label>,
    )}</div>
    <label className="check"><input type="checkbox" checked={draft.mirrored} onChange={event => { setSubmitted(false); adjust({...draft, mirrored: event.target.checked}) }}/> {t('mirror')}</label>
    <div className="control-buttons">
      <button className="primary" type="submit" disabled={frame.source !== 'off'}>{t('saveCalibration')}</button>
      <button type="button" onClick={() => {setSubmitted(false); adjust(frame.defaults)}}>{t('resetCalibration')}</button>
    </div>
    {submitted && !frame.error && JSON.stringify(frame.profile) === JSON.stringify(draft) && <span role="status"> {t('saved')}</span>}
  </form>
}

function App() {
  const {frame, status, send} = useStudio()
  const [language, setLanguage] = useState<Language>('en')
  const t = translator(language)
  const reportedLanguage = frame?.language
  useEffect(() => {
    if (reportedLanguage) setLanguage(reportedLanguage)
  }, [reportedLanguage])
  useEffect(() => {
    document.documentElement.lang = language
    document.title = 'KineticDesk · ' + translator(language)('gestureStudio')
  }, [language])
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
  const cameraLabel = cameraReady ? t('cameraActive') : t('cameraStarting')
  const needsAccessibility = frame?.canOpenAccessibility && !frame.device.accessibility
  const running = !!frame && frame.source !== 'off'
  const mode = !running ? t('stopped') : frame.scanning ? t('handScan') :
    frame.trackingInterrupted ? t('reacquiring') :
    frame.desktop && frame.mode === 'armed' ? t('pointerActive') : t(modes[frame.mode])
  const notable = [...(frame?.events ?? [])].reverse().filter(event => event.kind !== 'move').slice(0, 6)
  return <div className={expanded ? "shell expanded" : "shell"}>
    <header className="top">
      <div className="brand"><span className="logo" aria-hidden="true"><i/><i/><i/></span><span>KineticDesk</span></div>
      <nav aria-label={t('sections')}>
        <button className={tab === 'studio' ? 'chosen' : ''} aria-pressed={tab === 'studio'} onClick={() => setTab('studio')}>{t('studio')}</button>
        <button className={tab === 'calibrazione' ? 'chosen' : ''} aria-pressed={tab === 'calibrazione'} onClick={() => setTab('calibrazione')}>{t('calibration')}</button>
      </nav>
      <select className="language" aria-label={t('language')} value={language} disabled={!frame}
        onChange={event => send('language', {language: event.target.value})}>
        <option value="en" lang="en">English</option>
        <option value="it" lang="it">Italiano</option>
      </select>
      <span className="connection"><i className={frame ? 'online' : ''}/>{frame ? (live ? cameraLabel : t('localService')) : t(status)}</span>
    </header>
    <main>
      <div className="heading">
        <div><h1>{tab === 'studio' ? t('gestureStudio') : t('profile')}</h1>
        <p>{t('intro')}</p></div>
        <div className="status" data-mode={running ? frame.mode : 'off'} role="status">
          <i/>{live && !cameraReady ? t('cameraStarting') : mode}
          {frame && (frame.mode === 'paused' || frame.mode === 'stopped') && reasons[frame.reason] ? ' · ' + t(reasons[frame.reason]) : ''}
        </div>
      </div>
      {frame?.error && <div className="alert" role="alert">{errorText(t, frame.error)}</div>}
      {needsAccessibility && frame.awaitingAccessibility && <p className="session-hint" role="status">
        {t('allowThisCopy')}
      </p>}
      <div className="toolbar" aria-label={t('sessionControls')}>
        <button className="primary" disabled={!frame || frame.scanning || frame.desktop}
          onClick={() => send('scan')}>{live ? t('scanWhileLive') : t('startScan')}</button>
        <button disabled={!frame || live} onClick={() => send('camera')}>{t('simulationOnly')}</button>
        <button disabled={!frame} onClick={() => send('demo')}>{replay ? t('replayAgain') : t('demo')}</button>
        <span className="toolbar-gap"/>
        <button onClick={toggleWorkspace}>{expanded ? t('shrink') : t('expand')}</button>
        <button disabled={!running || frame.mode === 'paused'} onClick={() => send('pause')}>{t('pause')} <kbd>Esc</kbd></button>
        <button className="danger" disabled={!running} onClick={() => send('stop')}>■ Stop</button>
      </div>
      {tab === 'calibrazione' && frame && <section className="panel"><Calibration profile={frame.profile} frame={frame} send={send} t={t}/></section>}
      {tab === 'studio' && <>
        <div className="grid">
          <section className="panel monitor">
            <div className="panel-head">
              <div><h2>{t('tracking')}</h2><small>{live ? cameraLabel.toUpperCase() : replay ? t('syntheticReplay').toUpperCase() : t('cameraOff').toUpperCase()}</small></div>
              {live && <button disabled={!cameraReady} onClick={() => send('preview', {enabled: !frame.previewEnabled})}>{frame.previewEnabled ? t('hidePreview') : t('showPreview')}</button>}
            </div>
            {frame?.scanning && <div className="scan-progress">
              <strong>{!cameraReady ? t('openingCamera') : !frame.points ? t('frameHand') : t('holdIndex')}</strong>
              <span>{!cameraReady ? t('previewDuringScan') :
                t('scanHow')}</span>
              <progress aria-label={t('handScan')} max="1" value={frame.armProgress}/>
            </div>}
            <Tracking frame={frame} t={t}/>
            <div className="readings">
              <div><span>{t('rate')}</span><strong>{frame?.fps?.toFixed(1) ?? '—'}<small> fps</small></strong></div>
              <div><span>{t('handDetected')}</span><strong>{frame?.tracking != null ? (frame.tracking * 100).toFixed(0) + '%' : '—'}</strong></div>
              <div><span>{t('frameAge')}</span><strong>{frame?.frameAge != null && frame.frameAge < 500 ? frame.frameAge.toFixed(0) : '—'}<small> ms</small></strong></div>
            </div>
          </section>
          <aside className="panel controls">
            <div className="panel-head"><div><h2>{t('desktopControl')}</h2>
              <small>{frame?.desktop ? t('desktopInput').toUpperCase() : frame?.scanning ? t('scanning').toUpperCase() : t('dryRun').toUpperCase()}</small></div></div>
            <div className="control-body">
              {cameraReady && <p className="session-hint">{frame.desktop
                ? t('desktopInstructions')
                : frame.scanning
                  ? t('scanInstructions')
                  : frame.mode === 'paused'
                    ? t('resumeInstructions')
                    : t('simulationInstructions')}</p>}
              {frame?.nativeWindow && frame.desktop && <p className="permission">{t('backgroundInstructions')}</p>}
              {frame?.mode === 'ready' && !frame.scanning && (cameraReady || replay) &&
                <div className="arming"><span>{t('holdFist')}</span><progress aria-label={t('armProgress')} max="1" value={frame.armProgress}/></div>}
              <dl className="devices">
                <div><dt>{t('camera')}</dt><dd>{t(permissions[frame?.device.camera ?? 'unknown'])}</dd></div>
                <div><dt>{t('accessibility')}</dt><dd>{frame?.device.accessibility ? t('granted') : t('needed')}</dd></div>
              </dl>
              {frame?.device.platform === 'macOS' ? <p className="permission">{needsAccessibility
                ? t('requireAccessibility')
                : t('managePermissions')}</p> :
                <p className="permission">{t('macPreview')}</p>}
              <div className="control-buttons">
                {cameraReady && (frame.desktop || frame.mode === 'paused') &&
                  <button onClick={() => send('dry-run')}>{frame.desktop ? t('toSimulation') : t('resumeSimulation')}</button>}
                {needsAccessibility && <button onClick={() => send('open-accessibility')}>{t('openAccessibility')}</button>}
                <button disabled={!frame} onClick={() => send('permissions')}>{t('refreshPermissions')}</button>
              </div>
              <div className="activity"><h3>{t('recentActions')}</h3>
                {notable.length === 0 && <p>{t('noAction')}</p>}
                <ul>{notable.map(event => <li key={event.id}><span>{t(actions[event.kind])}</span><small>{event.injected ? t('desktop') : t('dryRunAction')}{event.amount ? ' · ' + event.amount : ''}</small></li>)}</ul>
              </div>
              {frame?.latency && <p className="permission">{t('latency')}, {t('median')} {frame.latency[0].toFixed(1)} ms · p95 {frame.latency[1].toFixed(1)} ms</p>}
            </div>
          </aside>
        </div>
        <div className="grid bottom">
          <section className="panel"><div className="panel-head"><div><h2>{t('practice')}</h2><small>{t('simulatedInput').toUpperCase()}</small></div></div><Playground frame={frame} t={t}/></section>
          <section className="panel"><div className="panel-head"><h2>{t('gestureGuide')}</h2></div><dl className="gesture-list">{gestures.map(([name, desc]) => <div key={name}><dt>{t(name)}</dt><dd>{t(desc)}</dd></div>)}</dl></section>
        </div>
      </>}
    </main>
  </div>
}

createRoot(document.getElementById('root')!).render(<App/>)
