import './demo.css';

type Comparison = {before: string; after: string; trace?: string};
type Demo = {repair?: Comparison; world: {scene_id: string | null}};
const root = document.getElementById('demo')!;
const media = (path: string) => '/media/' + path.split('/').map(encodeURIComponent).join('/');

async function start() {
  const response = await fetch('/api/demo');
  if (!response.ok) throw new Error('The demo is unavailable. Please check the local server.');
  const record: Demo = await response.json();
  root.innerHTML = `<header><a class="brand" href="/">Clean Room Imputation<span class="brand-dot">.</span></a><a class="workspace" href="/?workspace=1&scene=office-rebuild">Workspace ↗</a></header>
  <main><div class="intro"><h1>Repair the room.<br><span>Then step inside.</span></h1><p>An agent inspects a 3D room, repairs broken furniture, and checks the result.</p></div>
  <div class="toolbar"><div class="switcher" role="group" aria-label="Demo views"><button id="explore-tab" aria-pressed="true">Explore the room</button><button id="compare-tab" aria-pressed="false">Quick comparison</button></div><span class="explore">Your office · 3D reconstruction</span></div>
  <section id="world-stage" aria-label="Interactive 3D office"><iframe id="office-viewer" title="Explore the office and compare furniture repairs" allow="fullscreen" allowfullscreen></iframe></section>
  <section id="comparison-panel" aria-label="Recorded furniture comparison" hidden><div id="image-stage"><img id="after-image" alt="Office after table and chair repairs"><img id="before-image" alt="Office before table and chair repairs"><div id="divider" aria-hidden="true"><span>↔</span></div><span class="image-label before-label">Before</span><span class="image-label after-label">After</span><input id="comparison" aria-label="Before and after comparison" type="range" min="0" max="100" value="50"></div></section>
  <div class="caption"><span id="scope">Move through the room. Switch before / after without changing your viewpoint.</span><button id="fullscreen" class="text-button">Full screen ↗</button></div>
  <details id="loop"><summary>How the repair loop works <span aria-hidden="true">+</span></summary><div class="loop-content"><ol class="loop-diagram" aria-label="Inspect, repair, check, then keep or retry"><li><strong>Inspect</strong><span>Find broken room geometry</span></li><li><strong>Repair</strong><span>Rebuild and place furniture</span></li><li><strong>Check</strong><span>Compare multiple 3D views</span></li><li><strong>Keep or retry</strong><span>Undo changes that fail</span></li></ol><div class="return-arrow" aria-hidden="true">↶ Reinspect when the result falls short</div><p>This recorded example repairs a table and two chairs, with paired collision meshes. The 3D repairs were assistant-led; W&B Inference supported review and Weave recorded calls and decisions.</p><a id="trace" target="_blank" rel="noreferrer">View repair trace ↗</a></div></details>
  <footer>Prototype · free-flight exploration · room geometry still has defects</footer></main>`;
  const frame = document.getElementById('office-viewer') as HTMLIFrameElement;
  if (record.world.scene_id) frame.src = '/?immersive=1&presentation=1&scene=' + encodeURIComponent(record.world.scene_id);
  else document.getElementById('world-stage')!.textContent = 'No reconstructed office is available yet.';
  const slider = document.getElementById('comparison') as HTMLInputElement;
  const before = document.getElementById('before-image') as HTMLImageElement;
  if (record.repair) {
    before.src = media(record.repair.before);
    (document.getElementById('after-image') as HTMLImageElement).src = media(record.repair.after);
  } else (document.getElementById('compare-tab') as HTMLButtonElement).hidden = true;
  function compare() {
    before.style.clipPath = `inset(0 ${100 - Number(slider.value)}% 0 0)`;
    document.getElementById('divider')!.style.left = `${slider.value}%`;
  }
  slider.oninput = compare; compare();
  function select(explore: boolean) {
    document.getElementById('world-stage')!.hidden = !explore;
    document.getElementById('comparison-panel')!.hidden = explore;
    document.getElementById('explore-tab')!.setAttribute('aria-pressed', String(explore));
    document.getElementById('compare-tab')!.setAttribute('aria-pressed', String(!explore));
    document.getElementById('scope')!.textContent = explore ? 'Move through the room. Switch before / after without changing your viewpoint.' : 'Table and chair repairs · the same 3D camera, before and after.';
    document.getElementById('fullscreen')!.hidden = !explore;
  }
  document.getElementById('explore-tab')!.onclick = () => select(true);
  document.getElementById('compare-tab')!.onclick = () => select(false);
  document.getElementById('fullscreen')!.onclick = async () => {
    try { await frame.requestFullscreen(); } catch { document.getElementById('scope')!.textContent = 'Full screen is unavailable in this browser. You can still explore here.'; }
  };
  const trace = document.getElementById('trace') as HTMLAnchorElement;
  trace.hidden = !record.repair?.trace;
  trace.href = record.repair?.trace ?? '#';
}
start().catch(error => {root.textContent = error.message;});
