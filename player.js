// player.js — fetch the schedule, set up Tone.js synths, drive playback,
// fetch and inline LilyPond-rendered SVG pages, drive the UI.
//
// All audio timing comes from Tone.Transport; all UI state is derived from
// Tone.Transport.seconds in a requestAnimationFrame loop. Scheduling is
// done once, when the user first hits Play (Tone.start() requires a user
// gesture for the AudioContext).
//
// Sheet music: SVG pages are fetched as text and inlined into the DOM so
// (a) they style cleanly under our CSS, and (b) Milestone 6e can attach
// click/highlight behaviour to individual <g class="NoteHead"> elements.

'use strict';

// ── Globals ──────────────────────────────────────────────────────────────────

let SCHEDULE = null;          // the dict returned by /api/score
let SYNTHS = null;            // built lazily on first Play
let SCHEDULED = false;        // have we already pushed events to Transport?
let RAF_ID = null;            // animation frame handle for UI loop
let TEMPO_INDEX = 0;          // hint for sequential tempo lookup during play
let MEASURE_INDEX = 0;        // ditto for measures

const GRACE_V8_OFFSET_SECONDS = 0.030;  // play v8 acciaccaturas 30ms early

// ── DOM handles ──────────────────────────────────────────────────────────────

const $ = (id) => document.getElementById(id);
const elTitle = $('title');
const elArtist = $('artist');
const elBtnPlay = $('btn-play');
const elBtnPause = $('btn-pause');
const elBtnStop = $('btn-stop');
const elBar = $('status-bar');
const elMarker = $('status-marker');
const elTimeSig = $('status-timesig');
const elTempo = $('status-tempo');
const elPosition = $('status-position');
const elProgress = $('progress');
const elError = $('error');
const elSheet = $('sheet');
const elSheetStatus = $('sheet-status');

// ── Bootstrap ────────────────────────────────────────────────────────────────

async function init() {
  try {
    const resp = await fetch('/api/score');
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    SCHEDULE = await resp.json();
  } catch (err) {
    showError(`Failed to load score: ${err.message}`);
    return;
  }

  elTitle.textContent = SCHEDULE.title || '(untitled)';
  elArtist.textContent = SCHEDULE.artist || '';
  elTimeSig.textContent = formatTimeSig(SCHEDULE.measures[0]?.time_sig);
  elTempo.textContent = formatTempo(SCHEDULE.tempos[0]?.bpm);
  elBar.textContent = `1 / ${SCHEDULE.measures.length}`;
  elPosition.textContent = `0:00 / ${formatTime(SCHEDULE.total_seconds)}`;

  elBtnPlay.disabled = false;
  elBtnPlay.addEventListener('click', onPlay);
  elBtnPause.addEventListener('click', onPause);
  elBtnStop.addEventListener('click', onStop);

  // Sheet music is not on the audio critical path; load it in parallel and
  // let the user start playing as soon as the schedule is up.
  loadSheetMusic(SCHEDULE.svg_pages || 0);
}

// ── Sheet music ──────────────────────────────────────────────────────────────

async function loadSheetMusic(pageCount) {
  if (pageCount <= 0) {
    elSheetStatus.textContent =
      'Sheet music not available (LilyPond compilation skipped or failed).';
    return;
  }

  // Fetch all pages in parallel — they're independent, and most scores
  // are 1–4 pages so the total payload is small.
  let texts;
  try {
    const responses = await Promise.all(
      Array.from({ length: pageCount }, (_, i) =>
        fetch(`/svg/${i}`).then(r => {
          if (!r.ok) throw new Error(`page ${i}: HTTP ${r.status}`);
          return r.text();
        })
      )
    );
    texts = responses;
  } catch (err) {
    elSheetStatus.textContent = `Failed to load sheet music: ${err.message}`;
    return;
  }

  // Replace the loading placeholder with the inlined SVG pages.
  elSheet.innerHTML = '';
  for (let i = 0; i < texts.length; i++) {
    const wrapper = document.createElement('div');
    wrapper.className = 'sheet-page';
    wrapper.dataset.pageIndex = String(i);
    // innerHTML on an SVG string is the simplest way to get it into the DOM
    // as proper SVG nodes (rather than escaped text). The browser parses
    // the <svg> root and creates the element tree.
    wrapper.innerHTML = texts[i];
    elSheet.appendChild(wrapper);
  }
}

// ── Synth construction ───────────────────────────────────────────────────────

function buildSynths() {
  const masterVol = new Tone.Volume(-6).toDestination();

  return {
    kick: new Tone.MembraneSynth({
      pitchDecay: 0.05, octaves: 4,
      envelope: { attack: 0.001, decay: 0.4, sustain: 0.0, release: 0.4 }
    }).connect(masterVol),

    snare: new Tone.NoiseSynth({
      noise: { type: 'white' },
      envelope: { attack: 0.001, decay: 0.18, sustain: 0.0, release: 0.05 }
    }).connect(new Tone.Filter(2200, 'highpass').connect(masterVol)),

    sidestick: new Tone.MembraneSynth({
      pitchDecay: 0.008, octaves: 1,
      envelope: { attack: 0.001, decay: 0.05, sustain: 0.0, release: 0.02 }
    }).connect(masterVol),

    hatClosed: new Tone.NoiseSynth({
      noise: { type: 'white' },
      envelope: { attack: 0.001, decay: 0.04, sustain: 0.0, release: 0.02 }
    }).connect(new Tone.Filter(7000, 'highpass').connect(masterVol)),

    hatOpen: new Tone.NoiseSynth({
      noise: { type: 'white' },
      envelope: { attack: 0.001, decay: 0.30, sustain: 0.0, release: 0.10 }
    }).connect(new Tone.Filter(6000, 'highpass').connect(masterVol)),

    tom: new Tone.MembraneSynth({
      pitchDecay: 0.08, octaves: 3,
      envelope: { attack: 0.001, decay: 0.35, sustain: 0.0, release: 0.30 }
    }).connect(masterVol),

    crash: new Tone.MetalSynth({
      frequency: 250, harmonicity: 4.1, modulationIndex: 24,
      resonance: 4000, octaves: 1.4,
      envelope: { attack: 0.001, decay: 1.2, release: 0.2 }
    }).connect(new Tone.Volume(-12).connect(masterVol)),

    ride: new Tone.MetalSynth({
      frequency: 350, harmonicity: 5.4, modulationIndex: 32,
      resonance: 6000, octaves: 1.0,
      envelope: { attack: 0.001, decay: 0.7, release: 0.15 }
    }).connect(new Tone.Volume(-14).connect(masterVol)),
  };
}

function dispatch(midi) {
  switch (midi) {
    case 35: case 36:        return { synth: 'kick',      note: 'C1' };
    case 37:                 return { synth: 'sidestick', note: 'C4' };
    case 38: case 40:        return { synth: 'snare' };
    case 39:                 return { synth: 'snare' };
    case 41:                 return { synth: 'tom',  note: 'F1' };
    case 43:                 return { synth: 'tom',  note: 'A1' };
    case 45:                 return { synth: 'tom',  note: 'D2' };
    case 47:                 return { synth: 'tom',  note: 'F2' };
    case 48:                 return { synth: 'tom',  note: 'A2' };
    case 50:                 return { synth: 'tom',  note: 'C3' };
    case 42: case 44:        return { synth: 'hatClosed' };
    case 46:                 return { synth: 'hatOpen' };
    case 92:                 return { synth: 'hatOpen' };
    case 49: case 57: case 52: case 55: case 59:
                             return { synth: 'crash' };
    case 51: case 53:        return { synth: 'ride' };
    default:                 return { synth: 'snare' };
  }
}

function playDrum(midi, time) {
  const d = dispatch(midi);
  const synth = SYNTHS[d.synth];
  if (!synth) return;
  if (d.note) {
    synth.triggerAttackRelease(d.note, '8n', time);
  } else {
    synth.triggerAttackRelease('8n', time);
  }
}

// ── Scheduling ───────────────────────────────────────────────────────────────

function scheduleAll() {
  for (const ev of SCHEDULE.events) {
    const t = ev.grace_v8
      ? Math.max(0, ev.seconds - GRACE_V8_OFFSET_SECONDS)
      : ev.seconds;
    const midiList = ev.midi;
    Tone.Transport.schedule((audioTime) => {
      for (const m of midiList) playDrum(m, audioTime);
    }, t);
  }
  Tone.Transport.schedule(() => onStop(), SCHEDULE.total_seconds + 0.5);
  SCHEDULED = true;
}

// ── Controls ─────────────────────────────────────────────────────────────────

async function onPlay() {
  await Tone.start();
  if (!SYNTHS) SYNTHS = buildSynths();
  if (!SCHEDULED) scheduleAll();

  Tone.Transport.start();
  elBtnPlay.disabled = true;
  elBtnPause.disabled = false;
  elBtnStop.disabled = false;
  startUiLoop();
}

function onPause() {
  Tone.Transport.pause();
  elBtnPlay.disabled = false;
  elBtnPause.disabled = true;
}

function onStop() {
  Tone.Transport.stop();
  Tone.Transport.position = 0;
  elBtnPlay.disabled = false;
  elBtnPause.disabled = true;
  elBtnStop.disabled = true;
  TEMPO_INDEX = 0;
  MEASURE_INDEX = 0;
  if (RAF_ID) cancelAnimationFrame(RAF_ID);
  RAF_ID = null;
  updateUi(0);
}

// ── UI loop ──────────────────────────────────────────────────────────────────

function startUiLoop() {
  if (RAF_ID) cancelAnimationFrame(RAF_ID);
  const tick = () => {
    updateUi(Tone.Transport.seconds);
    RAF_ID = requestAnimationFrame(tick);
  };
  RAF_ID = requestAnimationFrame(tick);
}

function updateUi(t) {
  if (MEASURE_INDEX > 0 &&
      t < SCHEDULE.measures[MEASURE_INDEX].seconds_start) {
    MEASURE_INDEX = 0;
  }
  if (TEMPO_INDEX > 0 && t < SCHEDULE.tempos[TEMPO_INDEX].seconds) {
    TEMPO_INDEX = 0;
  }
  while (MEASURE_INDEX + 1 < SCHEDULE.measures.length &&
         SCHEDULE.measures[MEASURE_INDEX + 1].seconds_start <= t) {
    MEASURE_INDEX++;
  }
  while (TEMPO_INDEX + 1 < SCHEDULE.tempos.length &&
         SCHEDULE.tempos[TEMPO_INDEX + 1].seconds <= t) {
    TEMPO_INDEX++;
  }

  const m = SCHEDULE.measures[MEASURE_INDEX];
  const tc = SCHEDULE.tempos[TEMPO_INDEX];

  elBar.textContent = `${m.index} / ${SCHEDULE.measures.length}`;
  elMarker.textContent = m.marker || '—';
  elTimeSig.textContent = formatTimeSig(m.time_sig);
  elTempo.textContent = formatTempo(tc?.bpm);
  elPosition.textContent =
    `${formatTime(t)} / ${formatTime(SCHEDULE.total_seconds)}`;

  const pct = SCHEDULE.total_seconds > 0
    ? Math.min(100, 100 * t / SCHEDULE.total_seconds)
    : 0;
  elProgress.style.width = `${pct}%`;
}

// ── Formatters ───────────────────────────────────────────────────────────────

function formatTimeSig(ts) {
  if (!ts) return '—';
  return `${ts[0]}/${ts[1]}`;
}

function formatTempo(bpm) {
  if (bpm == null) return '—';
  return `\u2669 = ${Math.round(bpm * 10) / 10}`;
}

function formatTime(s) {
  if (!isFinite(s)) return '0:00';
  const mins = Math.floor(s / 60);
  const secs = Math.floor(s % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function showError(msg) {
  elError.textContent = msg;
  console.error(msg);
}

// ── Go ───────────────────────────────────────────────────────────────────────

init();
