import './demo.css';

type Chapter = {title: string; label: string; description: string; before: string; after: string; before_label: string; after_label: string; evidence: string; trace?: string; scope: string};
type Demo = {chapters: Chapter[]; world: {scene_id: string | null; status: string; detail: string}};
const root = document.getElementById('demo')!;
const escape = (s: string) => s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));
const media = (s: string) => '/media/' + s.split('/').map(encodeURIComponent).join('/');
let record: Demo;
let current = 0;
let playing: ReturnType<typeof setInterval> | undefined;

function stop() {
  clearInterval(playing);
  playing = undefined;
  document.getElementById('play')!.textContent = 'Play recorded sequence';
}
function chapter(index: number) {
  current = index;
  const step = record.chapters[index];
  document.getElementById('chapter-title')!.textContent = step.title;
  document.getElementById('chapter-description')!.textContent = step.description;
  document.getElementById('chapter-label')!.textContent = `${String(index + 1).padStart(2, '0')} / ${String(record.chapters.length).padStart(2, '0')} · ${step.label}`;
  document.getElementById('evidence')!.textContent = step.evidence;
  document.getElementById('scope')!.textContent = step.scope;
  document.getElementById('image-stage')!.innerHTML = `<img class="comparison-image" src="${media(step.after)}" alt="${escape(step.after_label)}"><img id="before-image" class="comparison-image" src="${media(step.before)}" alt="${escape(step.before_label)}"><div id="divider"></div><span class="image-label before-label">${escape(step.before_label)}</span><span class="image-label after-label">${escape(step.after_label)}</span>`;
  const slider = document.getElementById('comparison') as HTMLInputElement;
  slider.value = '50';
  compare(50);
  document.querySelectorAll<HTMLButtonElement>('[data-chapter]').forEach(button => {
    button.classList.toggle('active', Number(button.dataset.chapter) === index);
    button.setAttribute('aria-current', Number(button.dataset.chapter) === index ? 'step' : 'false');
  });
  const trace = document.getElementById('trace') as HTMLAnchorElement;
  trace.hidden = !step.trace;
  trace.href = step.trace ?? '#';
  (document.getElementById('previous') as HTMLButtonElement).disabled = index === 0;
  (document.getElementById('next') as HTMLButtonElement).disabled = index === record.chapters.length - 1;
}
function compare(value: number) {
  document.getElementById('before-image')!.style.clipPath = `inset(0 ${100 - value}% 0 0)`;
  document.getElementById('divider')!.style.left = `${value}%`;
}
function worldStatus() {
  document.getElementById('world-status')!.textContent = record.world.status;
  document.getElementById('world-detail')!.textContent = record.world.detail;
  const link = document.getElementById('world-link') as HTMLAnchorElement;
  link.hidden = !record.world.scene_id;
  link.href = '/?scene=' + encodeURIComponent(record.world.scene_id ?? '');
}
async function fetchRecord(): Promise<Demo> {
  const response = await fetch('/api/demo');
  if (!response.ok) throw new Error('No recorded demo is prepared yet. Run the demo preparation command.');
  return response.json();
}
async function start() {
  record = await fetchRecord();
  root.innerHTML = `<header><a class="brand" href="/demo.html"><span class="mark">cri</span>Clean Room <strong>Imputation</strong></a><span class="recorded"><i></i> Recorded tool runs</span><a class="secondary" href="/">Open workspace ↗</a></header>
  <main><section class="heading"><div><span class="eyebrow">AN AGENT THAT CHECKS ITS OWN CLEANUP</span><h1>Same room.<br><em>No one there.</em></h1></div><p>Remove the people.<br>Keep what makes the room, the room.</p></section>
  <nav aria-label="Recorded demo chapters">${record.chapters.map((s, i) => `<button data-chapter="${i}"><span>${String(i+1).padStart(2,'0')}</span>${escape(s.label)}</button>`).join('')}</nav>
  <section class="presentation"><div class="visual"><div id="image-stage"></div><div class="comparison-controls"><span>Before</span><input id="comparison" aria-label="Before and after comparison" type="range" min="0" max="100" value="50"><span>After</span></div><p id="scope"></p></div><aside><span id="chapter-label" class="eyebrow"></span><h2 id="chapter-title"></h2><p id="chapter-description"></p><div class="evidence-card"><span class="eyebrow">RECORDED EVIDENCE</span><p id="evidence"></p><a id="trace" target="_blank" rel="noreferrer">Inspect Weave trace ↗</a></div><div class="navigation"><button id="previous" aria-label="Previous chapter">←</button><button id="play">Play recorded sequence</button><button id="next" aria-label="Next chapter">→</button></div></aside></section>
  <footer><div><span class="eyebrow">3D RECONSTRUCTION</span><strong id="world-status"></strong><p id="world-detail"></p></div><a id="world-link" class="primary">Explore the room ↗</a></footer><p class="attribution">W&B Inference + Weave · fal image tools + SAM · Hunyuan world generation · Three.js viewer</p></main>`;
  document.querySelectorAll<HTMLButtonElement>('[data-chapter]').forEach(button => button.onclick = () => {stop(); chapter(Number(button.dataset.chapter));});
  document.getElementById('comparison')!.oninput = e => compare(Number((e.target as HTMLInputElement).value));
  document.getElementById('previous')!.onclick = () => {stop(); chapter(Math.max(0, current - 1));};
  document.getElementById('next')!.onclick = () => {stop(); chapter(Math.min(record.chapters.length - 1, current + 1));};
  document.getElementById('play')!.onclick = () => {
    if (playing) {stop(); return;}
    if (current === record.chapters.length - 1) chapter(0);
    document.getElementById('play')!.textContent = 'Pause replay';
    playing = setInterval(() => {if (current === record.chapters.length - 1) stop(); else chapter(current + 1);}, 10000);
  };
  window.addEventListener('keydown', e => {
    if ((e.target as HTMLElement).matches('input,button,a')) return;
    if (e.key === 'ArrowRight') {stop(); chapter(Math.min(record.chapters.length - 1, current + 1));}
    if (e.key === 'ArrowLeft') {stop(); chapter(Math.max(0, current - 1));}
  });
  chapter(0); worldStatus();
  setInterval(async () => {try {record = await fetchRecord(); worldStatus();} catch {/* Keep the last verified record available during a transient connection failure. */}}, 8000);
}
start().catch(error => {root.textContent = error.message;});
