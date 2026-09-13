import './demo.css';

type Comparison = {label: string; before: string; after: string; scope: string; trace?: string};
type Demo = {chapters: Comparison[]; repair?: Comparison; world: {scene_id: string | null}};
const root = document.getElementById('demo')!;
const media = (path: string) => '/media/' + path.split('/').map(encodeURIComponent).join('/');

async function start() {
  const response = await fetch('/api/demo');
  if (!response.ok) throw new Error('The recorded demo is unavailable. Please check the local server.');
  const record: Demo = await response.json();
  const comparisons: Comparison[] = [{...record.chapters[0], label: 'Remove people', scope: 'Source-image cleanup · unseen surfaces are inferred.'}];
  if (record.repair) comparisons.push(record.repair);
  root.innerHTML = `<header><a class="brand" href="/">Clean Room Imputation<span class="brand-dot">.</span></a><a class="workspace" href="/?workspace=1&scene=office-rebuild">Workspace ↗</a></header>
  <main><div class="intro"><h1>The same room.<br><span>Ready for a fresh start.</span></h1><p>Remove people. Rebuild furniture. Check every change.</p></div>
  <div class="toolbar"><div class="switcher" role="group" aria-label="Demo comparisons">${comparisons.map((item, index) => `<button data-comparison="${index}" aria-pressed="false">${item.label}</button>`).join('')}</div><a id="world-link" class="explore">Explore in 3D <span aria-hidden="true">↗</span></a></div>
  <section aria-label="Recorded before and after"><div id="image-stage"><img id="after-image" alt="After repair"><img id="before-image" alt="Before repair"><div id="divider" aria-hidden="true"><span>↔</span></div><span class="image-label before-label">Before</span><span class="image-label after-label">After</span><input id="comparison" aria-label="Before and after comparison" type="range" min="0" max="100" value="50"></div><div class="caption"><span id="scope"></span><span class="drag-hint">Drag to compare</span></div></section>
  <details id="loop"><summary>How it works <span aria-hidden="true">+</span></summary><div class="loop-content"><ol class="loop-diagram" aria-label="Inspect, repair, check, then keep or retry"><li><strong>Inspect</strong><span>Find a specific defect</span></li><li><strong>Repair</strong><span>Make a reversible edit</span></li><li><strong>Check</strong><span>Compare the same views</span></li><li><strong>Keep or retry</strong><span>Undo changes that fail</span></li></ol><div class="return-arrow" aria-hidden="true">↶ Reinspect when the result falls short</div><p>Recorded experiments, including assistant-led 3D repairs. W&B Inference supports visual review; Weave records calls and decisions.</p><a id="trace" target="_blank" rel="noreferrer">View repair trace ↗</a></div></details>
  <footer>Office reconstruction prototype · geometry still has defects</footer></main>`;
  const slider = document.getElementById('comparison') as HTMLInputElement;
  const before = document.getElementById('before-image') as HTMLImageElement;
  const after = document.getElementById('after-image') as HTMLImageElement;
  function compare() {
    before.style.clipPath = `inset(0 ${100 - Number(slider.value)}% 0 0)`;
    document.getElementById('divider')!.style.left = `${slider.value}%`;
  }
  function select(index: number) {
    const item = comparisons[index];
    before.src = media(item.before); after.src = media(item.after);
    document.getElementById('scope')!.textContent = item.scope;
    document.querySelectorAll<HTMLButtonElement>('[data-comparison]').forEach(button => button.setAttribute('aria-pressed', String(Number(button.dataset.comparison) === index)));
    slider.value = '50'; compare();
  }
  document.querySelectorAll<HTMLButtonElement>('[data-comparison]').forEach(button => button.onclick = () => select(Number(button.dataset.comparison)));
  slider.oninput = compare;
  const link = document.getElementById('world-link') as HTMLAnchorElement;
  link.hidden = !record.world.scene_id;
  link.href = '/?immersive=1&scene=' + encodeURIComponent(record.world.scene_id ?? '');
  const trace = document.getElementById('trace') as HTMLAnchorElement;
  trace.hidden = !record.repair?.trace;
  trace.href = record.repair?.trace ?? '#';
  select(comparisons.length - 1);
}
start().catch(error => {root.textContent = error.message;});
