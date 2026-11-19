/**
 * TTS no navegador — faz o orb reagir à voz REAL do JARVIS.
 *
 * O problema que isto resolve:
 *
 * O orb do app.js já é reativo, mas só ao microfone. Quando o JARVIS fala, a
 * amplitude vinha de uma senoide falsa:
 *
 *     tal = m > 0.01 ? m : (speaking ? 0.16 + Math.sin(t*18)*0.22 : 0);
 *                                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^
 *
 * Isso acontecia porque o TTS tocava no BACKEND, pelo alto-falante do
 * servidor. O navegador nunca via aquele áudio, então não tinha o que
 * analisar — e o orb pulsava num ritmo fixo, sem relação com as palavras.
 *
 * Aqui o áudio passa a tocar no navegador. A Web Audio API analisa, e o orb
 * responde às vogais, às pausas, ao fim da frase. É a diferença entre pulsar
 * e falar.
 *
 * Uso:
 *     import { falar, nivelTTS, estaFalando } from '/static/tts-voice.js';
 *     await falar('Sistemas operacionais, senhor.');
 *     nivelTTS();  // 0..1 — ligue isto no 'tal' do drawOrb
 */

const ENDPOINT = '/tts-iron/tts';
const SUAVIZACAO = 0.84;   // mesmo valor do analisador de microfone do app.js

let ctx = null;
let analisador = null;
let bins = null;
let elemento = null;
let fonteLigada = false;
let falando = false;
let nivel = 0;

/** Cria o contexto de áudio na primeira chamada. */
function _garantir() {
  if (ctx) return;
  const AC = window.AudioContext || window.webkitAudioContext;
  ctx = new AC();
  analisador = ctx.createAnalyser();
  analisador.fftSize = 512;
  analisador.smoothingTimeConstant = SUAVIZACAO;
  bins = new Uint8Array(analisador.frequencyBinCount);

  elemento = new Audio();
  elemento.crossOrigin = 'anonymous';
  elemento.preload = 'auto';
}

/**
 * Nível atual da voz, 0..1.
 *
 * Usa só os primeiros 40% dos bins: a voz humana vive nos graves e nos médios,
 * e incluir o resto do espectro diluiria o sinal com silêncio.
 */
export function nivelTTS() {
  if (!falando || !analisador) {
    nivel += (0 - nivel) * 0.12;
    return nivel;
  }
  analisador.getByteFrequencyData(bins);
  const uteis = Math.floor(bins.length * 0.4);
  let soma = 0;
  for (let i = 0; i < uteis; i++) soma += bins[i];
  const bruto = (soma / uteis) / 255;
  // Ganho: fala normalizada raramente passa de 0.45 no médio.
  nivel += (Math.min(bruto * 1.9, 1) - nivel) * 0.30;
  return nivel;
}

export function estaFalando() {
  return falando;
}

/** Espectro cru, para quem quiser desenhar banda a banda. */
export function espectroTTS() {
  if (!falando || !analisador) return null;
  analisador.getByteFrequencyData(bins);
  return bins;
}

/**
 * Sintetiza e toca no navegador.
 * @param {string} texto
 * @returns {Promise<boolean>} true se chegou a tocar
 */
export async function falar(texto) {
  if (!texto || !texto.trim()) return false;
  _garantir();

  // Navegador mantém o contexto suspenso até um gesto do usuário.
  if (ctx.state === 'suspended') {
    try { await ctx.resume(); } catch { /* segue sem análise */ }
  }

  // createMediaElementSource só pode ser chamado uma vez por elemento.
  if (!fonteLigada) {
    try {
      const fonte = ctx.createMediaElementSource(elemento);
      fonte.connect(analisador);
      analisador.connect(ctx.destination);
      fonteLigada = true;
    } catch (err) {
      console.warn('[TTS] análise indisponível; tocando sem reação', err);
    }
  }

  const url = `${ENDPOINT}?text=${encodeURIComponent(texto.slice(0, 500))}&lang=pt`;

  return new Promise((resolve) => {
    let encerrado = false;
    const encerrar = (ok) => {
      if (encerrado) return;
      encerrado = true;
      falando = false;
      elemento.removeEventListener('ended', aoTerminar);
      elemento.removeEventListener('error', aoFalhar);
      resolve(ok);
    };
    const aoTerminar = () => encerrar(true);
    const aoFalhar = () => {
      console.warn('[TTS] falha ao carregar áudio de', url);
      encerrar(false);
    };

    elemento.addEventListener('ended', aoTerminar);
    elemento.addEventListener('error', aoFalhar);

    elemento.src = url;
    falando = true;
    elemento.play().catch((err) => {
      // Política de autoplay: sem gesto prévio, o navegador recusa.
      console.warn('[TTS] navegador bloqueou a reprodução', err);
      encerrar(false);
    });
  });
}

/** Interrompe a fala no meio. */
export function calar() {
  if (elemento && !elemento.paused) {
    elemento.pause();
    elemento.currentTime = 0;
  }
  falando = false;
}

// Exposto também em window: o app.js é script clássico, não módulo.
window.JarvisTTS = { falar, calar, nivelTTS, espectroTTS, estaFalando };
