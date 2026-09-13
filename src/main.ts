import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import {
  SparkRenderer,
  SplatMesh,
  SplatEdit,
  SplatEditSdf,
  SplatEditSdfType,
} from "@sparkjsdev/spark";
import "./style.css";

type Vector = [number, number, number];
type Transform = { position: Vector; rotation: Vector; scale: Vector };
type Bounds = { minimum: Vector; maximum: Vector };
type Asset = {
  id: string;
  label: string;
  kind: "splat" | "mesh" | "box";
  path: string | null;
  remote_url?: string | null;
  paged?: boolean;
  unlit?: boolean;
  collider_path: string | null;
  collider_matrix?: number[] | null;
  transform: Transform;
  size: Vector;
  color: string;
  provenance: string;
  initially_visible: boolean;
};
type Edit = {
  id: string;
  operation: string;
  asset_id: string;
  reason: string;
  evidence: string[];
  bounds: Bounds | null;
  transform: Transform | null;
  size: Vector | null;
  color: string;
};
type Revision = {
  id: string;
  label: string;
  status: string;
  edits: Edit[];
  evaluation: unknown;
};
type Camera = { position: Vector; target: Vector; fov: number };
type SceneData = {
  id: string;
  title: string;
  description: string;
  goal: string;
  source_kind: string;
  assets: Asset[];
  references: string[];
  video: string | null;
  cameras: Record<string, Camera>;
  bounds: Bounds;
  revisions: Revision[];
  current_revision: string;
  metric_status: string;
};
type Loaded = {
  asset: Asset;
  root: THREE.Group;
  splat?: SplatMesh;
  collider?: THREE.Object3D;
  appearance?: THREE.Object3D;
  originalIndices: Map<
    THREE.BufferGeometry,
    THREE.BufferAttribute | THREE.InterleavedBufferAttribute | null
  >;
};
const query = new URLSearchParams(location.search);
const captureMode = query.has("capture");
if (captureMode) document.body.classList.add("capture-mode");
const escape = (value: unknown) =>
  String(value).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ]!,
  );
const media = (path: string) =>
  "/media/" + path.split("/").map(encodeURIComponent).join("/");
const $ = <T extends HTMLElement = HTMLElement>(id: string) =>
  document.getElementById(id) as T;
async function api(path: string, body?: unknown) {
  const response = await fetch(
    "/api/" + path,
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  if (!response.ok) {
    let detail = await response.text();
    throw new Error(detail);
  }
  return response.json();
}

document.querySelector("#app")!.innerHTML = `
<header><a class="brand" href="/"><span class="mark">cr<span>i</span></span><span>Clean Room<br><strong>Imputation</strong></span></a><div class="project-picker"><span class="eyebrow">WORKSPACE</span><select id="scene-select" aria-label="Scene"></select></div><div class="header-status"><span class="status-dot"></span><span id="connection">Connecting</span></div><button id="export" class="quiet">Export scene record ↗</button></header>
<main><aside class="left-panel"><div class="eyebrow">THE ORIGINAL, RECONSIDERED</div><h1>Same room.<br><span>No one there.</span></h1><p class="intro">Restore what belongs. Reconstruct what was hidden.</p><section><div class="section-heading"><h2>Source evidence</h2><span id="source-count"></span></div><div id="references"></div><p id="source-note" class="small"></p></section><section><div class="section-heading"><h2>Scene objects</h2><span id="object-count"></span></div><div id="assets"></div></section><section class="goal-card"><span class="eyebrow">PRESERVATION FIRST</span><p id="goal"></p></section></aside>
<section class="stage"><div class="stage-heading"><div><span class="eyebrow" id="scene-type">RECONSTRUCTION</span><h2 id="scene-title">Loading workspace…</h2></div><span class="pill" id="revision-label">Original</span></div><div id="viewport"><div id="loading"><span class="spinner"></span><p>Opening the scene</p></div><div class="viewport-caption"><span id="camera-label">Inspection view</span><span>Drag to orbit · Scroll to explore</span></div><div id="scene-warning"></div></div><div class="toolbar"><div id="cameras"></div><div class="toggles"><label><input type="checkbox" id="appearance" checked> Appearance</label><label><input type="checkbox" id="colliders"> Collision</label><label><input type="checkbox" id="grid"> Grid</label><button id="capture" class="quiet">Capture view</button></div></div><div class="revision-bar"><div><span class="eyebrow">SCENE HISTORY</span><select id="revision-select" aria-label="Scene revision"></select></div><button id="original" class="quiet">View original</button><button id="current" class="quiet">View accepted</button></div><div id="notice" role="status">Source imagery is evidence. Reconstructed hidden surfaces remain inferred.</div></section>
<aside class="right-panel"><div class="section-heading"><h2>Restoration loop</h2><span class="pill" id="loop-state">Ready</span></div><p class="small">Inspect → propose → compare → retain or undo.</p><button id="run-loop" class="primary">Start inspection loop <span>↗</span></button><div class="run-options"><label>Maximum passes <select id="passes"><option>1</option><option selected>2</option><option>3</option></select></label><span>Uses inference credits</span></div><div class="evidence-heading"><span class="eyebrow">DECISIONS & EVIDENCE</span><button id="refresh" class="quiet">↻</button></div><div id="events" aria-live="polite"><div class="empty-state">Every change needs a reason.<br><span>Inspection evidence will appear here.</span></div></div><details class="tools"><summary>Agent tool console</summary><p class="small">Create a reversible candidate. It is not accepted automatically.</p><textarea id="edit-json" aria-label="Edit JSON" spellcheck="false"></textarea><button id="propose" class="quiet">Preview candidate</button><button id="accept" class="quiet">Accept candidate</button><button id="reject" class="quiet">Reject candidate</button></details></aside></main>`;

const canvasHost = $("viewport");
const renderer = new THREE.WebGLRenderer({
  antialias: true,
  preserveDrawingBuffer: true,
});
renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.setClearColor("#101919");
canvasHost.prepend(renderer.domElement);
const world = new THREE.Scene();
const spark = new SparkRenderer({ renderer });
world.add(spark);
const camera = new THREE.PerspectiveCamera(55, 1, 0.01, 2000);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
const light = new THREE.HemisphereLight(0xffffff, 0x41494c, 2);
world.add(light);
const sun = new THREE.DirectionalLight(0xffffff, 2);
sun.position.set(3, 6, 4);
world.add(sun);
const grid = new THREE.GridHelper(20, 40, 0x5c7773, 0x293d3a);
grid.visible = false;
world.add(grid);
const loaded: Loaded[] = [];
const repairs = new THREE.Group();
world.add(repairs);
let data: SceneData;
let activeRevision: Revision;
let activeCamera = "";
let isolatedAsset: string | null = null;
let ready = false;
let rendering = false;

function resize() {
  const w = canvasHost.clientWidth,
    h = canvasHost.clientHeight;
  renderer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(canvasHost);
renderer.setAnimationLoop(() => {
  controls.update();
  renderer.render(world, camera);
});
function transform(object: THREE.Object3D, t: Transform) {
  object.position.fromArray(t.position);
  object.rotation.fromArray([...t.rotation, "XYZ"]);
  object.scale.fromArray(t.scale);
  object.updateMatrixWorld(true);
}
function setCamera(name: string) {
  const c = data.cameras[name];
  if (!c) throw new Error("Unknown camera");
  camera.position.fromArray(c.position);
  controls.target.fromArray(c.target);
  camera.fov = c.fov;
  camera.updateProjectionMatrix();
  controls.update();
  activeCamera = name;
  $("camera-label").textContent = name;
  document
    .querySelectorAll("[data-camera]")
    .forEach((b) =>
      b.classList.toggle(
        "selected",
        (b as HTMLElement).dataset.camera === name,
      ),
    );
}
function disposeObject(root: THREE.Object3D) {
  root.traverse((child) => {
    if (child instanceof THREE.Mesh) {
      child.geometry.dispose();
      const ms = Array.isArray(child.material)
        ? child.material
        : [child.material];
      ms.forEach((m) => m.dispose());
    }
  });
}

async function loadAsset(asset: Asset) {
  const root = new THREE.Group();
  root.name = asset.label;
  transform(root, asset.transform);
  world.add(root);
  const value: Loaded = { asset, root, originalIndices: new Map() };
  if (asset.kind === "splat" && (asset.path || asset.remote_url)) {
    value.splat = new SplatMesh({
      url: asset.remote_url ?? media(asset.path!),
      ...(asset.paged ? { paged: true, lod: false } : {}),
    });
    root.add(value.splat);
    await value.splat.initialized;
  }
  if (asset.kind === "mesh" && asset.path) {
    const gltf = await new GLTFLoader().loadAsync(media(asset.path));
    if (asset.unlit)
      gltf.scene.traverse((child) => {
        if (!(child instanceof THREE.Mesh)) return;
        const original = Array.isArray(child.material)
          ? child.material
          : [child.material];
        const replacements = original.map(
          (material: THREE.MeshStandardMaterial) => {
            const replacement = new THREE.MeshBasicMaterial({
              color: material.color,
              map: material.map,
              vertexColors: material.vertexColors,
              side: THREE.DoubleSide,
            });
            material.dispose();
            return replacement;
          },
        );
        child.material = Array.isArray(child.material)
          ? replacements
          : replacements[0];
      });
    value.appearance = gltf.scene;
    gltf.scene.traverse((child) => {
      if (child instanceof THREE.Mesh)
        value.originalIndices.set(
          child.geometry,
          child.geometry.index?.clone() ?? null,
        );
    });
    root.add(gltf.scene);
  }
  if (asset.kind === "box") {
    root.add(
      new THREE.Mesh(
        new THREE.BoxGeometry(...asset.size),
        new THREE.MeshStandardMaterial({ color: asset.color, roughness: 0.9 }),
      ),
    );
  }
  if (asset.collider_path) {
    const gltf = await new GLTFLoader().loadAsync(media(asset.collider_path));
    value.collider = gltf.scene;
    if (asset.collider_matrix)
      gltf.scene.applyMatrix4(
        new THREE.Matrix4().fromArray(asset.collider_matrix),
      );
    root.add(gltf.scene);
    gltf.scene.traverse((child) => {
      if (child instanceof THREE.Mesh) {
        value.originalIndices.set(
          child.geometry,
          child.geometry.index?.clone() ?? null,
        );
        const old = Array.isArray(child.material)
          ? child.material
          : [child.material];
        old.forEach((m) => m.dispose());
        child.material = new THREE.MeshBasicMaterial({
          color: 0xc3f285,
          wireframe: true,
          side: THREE.DoubleSide,
          transparent: true,
          opacity: 0.035,
          depthWrite: false,
        });
      }
    });
    value.collider.visible = false;
  }
  loaded.push(value);
  return value;
}

function applyRevision(id: string) {
  const revision = data.revisions.find((r) => r.id === id);
  if (!revision) throw new Error("Unknown revision");
  activeRevision = revision;
  isolatedAsset = null;
  repairs.visible = true;
  for (const child of [...repairs.children]) {
    repairs.remove(child);
    disposeObject(child);
  }
  for (const entry of loaded) {
    transform(entry.root, entry.asset.transform);
    entry.root.visible = entry.asset.initially_visible !== false;
    if (entry.splat) entry.splat.edits = [];
    for (const [g, index] of entry.originalIndices)
      g.setIndex((index?.clone() as THREE.BufferAttribute) ?? null);
  }
  for (const edit of revision.edits) {
    const entry = loaded.find((a) => a.asset.id === edit.asset_id);
    if (edit.operation === "hide_asset" && entry) entry.root.visible = false;
    if (
      (edit.operation === "transform_asset" ||
        edit.operation === "place_asset") &&
      entry &&
      edit.transform
    ) {
      transform(entry.root, edit.transform);
      if (edit.operation === "place_asset") entry.root.visible = true;
    }
    if (edit.operation === "add_surface" && edit.size && edit.transform) {
      const mesh = new THREE.Mesh(
        new THREE.BoxGeometry(...edit.size),
        new THREE.MeshStandardMaterial({ color: edit.color, roughness: 0.9 }),
      );
      transform(mesh, edit.transform);
      mesh.name = edit.reason;
      repairs.add(mesh);
    }
  }
  world.updateMatrixWorld(true);
  for (const edit of revision.edits) {
    if (edit.operation !== "hide_region" || !edit.bounds) continue;
    const entry = loaded.find((a) => a.asset.id === edit.asset_id);
    if (!entry) continue;
    const bounds = new THREE.Box3(
      new THREE.Vector3().fromArray(edit.bounds.minimum),
      new THREE.Vector3().fromArray(edit.bounds.maximum),
    );
    if (entry.splat) {
      const removal = new SplatEdit({ name: edit.reason, softEdge: 0 });
      const shape = new SplatEditSdf({
        type: SplatEditSdfType.BOX,
        opacity: 0,
      });
      bounds.getCenter(shape.position);
      bounds.getSize(shape.scale).multiplyScalar(0.5);
      removal.add(shape);
      removal.sdfs = [shape];
      removal.updateMatrixWorld(true);
      entry.splat.edits = [...(entry.splat.edits ?? []), removal];
    }
    // Apply the same conservative triangle removal to appearance and collider geometry.
    for (const root of [entry.appearance, entry.collider])
      root?.traverse((child) => {
        if (!(child instanceof THREE.Mesh)) return;
        const g = child.geometry,
          p = g.getAttribute("position"),
          idx = g.index,
          kept: number[] = [];
        const tri = new THREE.Triangle();
        for (let i = 0; i < (idx?.count ?? p.count); i += 3) {
          const ids = [0, 1, 2].map((k) => (idx ? idx.getX(i + k) : i + k));
          [tri.a, tri.b, tri.c].forEach((v, k) =>
            v.fromBufferAttribute(p, ids[k]).applyMatrix4(child.matrixWorld),
          );
          if (!bounds.intersectsTriangle(tri)) kept.push(...ids);
        }
        g.setIndex(kept);
      });
  }
  $("revision-label").textContent =
    revision.status === "baseline" ? "Original" : revision.status;
  $<HTMLSelectElement>("revision-select").value = id;
  ready = true;
}

function metadata() {
  world.updateMatrixWorld(true);
  camera.updateMatrixWorld(true);
  return {
    scene_id: data.id,
    revision_id: activeRevision.id,
    camera_name: activeCamera,
    isolated_asset: isolatedAsset,
    position: camera.position.toArray(),
    target: controls.target.toArray(),
    fov: camera.fov,
    viewport: [renderer.domElement.width, renderer.domElement.height],
    camera_matrix: camera.matrixWorld.toArray(),
    projection_matrix: camera.projectionMatrix.toArray(),
    metric_status: data.metric_status,
    objects: loaded
      .filter((e) => e.root.visible)
      .map((e) => {
        const box = e.collider
          ? new THREE.Box3().setFromObject(e.collider)
          : (e.splat?.getBoundingBox()?.applyMatrix4(e.splat.matrixWorld) ??
            new THREE.Box3().setFromObject(e.root));
        return {
          id: e.asset.id,
          label: e.asset.label,
          bounds: { minimum: box.min.toArray(), maximum: box.max.toArray() },
          provenance: e.asset.provenance,
        };
      }),
  };
}
function pick(x: number, y: number) {
  const ray = new THREE.Raycaster();
  ray.setFromCamera(new THREE.Vector2(x * 2 - 1, 1 - y * 2), camera);
  const hits = loaded
    .flatMap((e) =>
      e.root.visible && e.collider
        ? ray.intersectObject(e.collider, true).map((h) => ({
            asset_id: e.asset.id,
            point: h.point.toArray(),
            distance: h.distance,
          }))
        : [],
    )
    .sort((a, b) => a.distance - b.distance);
  return hits[0] ?? null;
}
function probeRegion(region: {
  minimum: [number, number];
  maximum: [number, number];
}) {
  const { minimum, maximum } = region;
  if (
    minimum.some(
      (value, index) =>
        value < 0 || maximum[index] > 1 || value >= maximum[index],
    )
  )
    throw new Error("Invalid normalized image region");
  world.updateMatrixWorld(true);
  camera.updateMatrixWorld(true);
  const samples = [];
  for (let row = 0; row < 5; row++)
    for (let column = 0; column < 5; column++) {
      const x = minimum[0] + ((maximum[0] - minimum[0]) * column) / 4;
      const y = minimum[1] + ((maximum[1] - minimum[1]) * row) / 4;
      samples.push({ image_point: [x, y], hit: pick(x, y) });
    }
  return {
    region,
    samples,
    coordinate_frame: "world",
    metric_status: data.metric_status,
    interpretation:
      "Nearest collider intersections only. Missing hits are unknown, not free space. Hits can lie behind an unmodeled object; this is not segmentation.",
  };
}
async function settle() {
  await new Promise<void>((resolve) =>
    setTimeout(resolve, loaded.some((entry) => entry.asset.paged) ? 3000 : 500),
  );
  renderer.render(world, camera);
}
function pixelVariation() {
  renderer.render(world, camera);
  const gl = renderer.getContext(),
    pixels = new Uint8Array(64 * 64 * 4);
  gl.readPixels(
    Math.floor(renderer.domElement.width / 2) - 32,
    Math.floor(renderer.domElement.height / 2) - 32,
    64,
    64,
    gl.RGBA,
    gl.UNSIGNED_BYTE,
    pixels,
  );
  const colors = new Set<number>();
  for (let i = 0; i < pixels.length; i += 4)
    colors.add((pixels[i] << 16) | (pixels[i + 1] << 8) | pixels[i + 2]);
  return colors.size;
}
Object.assign(window, {
  cleanroom: {
    get ready() {
      return ready && !rendering;
    },
    capture: async (name: string) => {
      setCamera(name);
      await settle();
      return metadata();
    },
    isolateAsset: async (id: string | null) => {
      applyRevision(activeRevision.id);
      if (id !== null && !loaded.some((entry) => entry.asset.id === id))
        throw new Error("Unknown asset");
      isolatedAsset = id;
      if (id !== null) {
        loaded.forEach((entry) => {
          entry.root.visible = entry.asset.id === id;
        });
        repairs.visible = false;
      } else repairs.visible = true;
      await settle();
      return metadata();
    },
    metadata,
    pick,
    probeRegion,
    applyRevision,
    setCamera,
    pixelVariation,
    diagnostics: () =>
      loaded.map((e) => ({
        id: e.asset.id,
        meshes: e.root.children.map((child) => {
          const meshes: any[] = [];
          child.traverse((object) => {
            if (object instanceof THREE.Mesh)
              meshes.push({
                vertices: object.geometry.getAttribute("position")?.count,
                material: (Array.isArray(object.material)
                  ? object.material
                  : [object.material]
                ).map((m: any) => ({
                  type: m.type,
                  color: m.color?.toArray(),
                  vertexColors: m.vertexColors,
                  opacity: m.opacity,
                  side: m.side,
                })),
                colors: object.geometry
                  .getAttribute("color")
                  ?.array.slice(0, 12),
              });
          });
          return { visible: child.visible, meshes };
        }),
        splats: e.splat?.numSplats,
        bounds: e.splat?.getBoundingBox(),
        matrix: e.splat?.matrixWorld.toArray(),
        colliderTriangles: (() => {
          let count = 0;
          e.collider?.traverse((child) => {
            if (child instanceof THREE.Mesh)
              count +=
                (child.geometry.index?.count ??
                  child.geometry.getAttribute("position").count) / 3;
          });
          return count;
        })(),
      })),
  },
});

function displayAssets() {
  $("object-count").textContent = String(data.assets.length);
  $("assets").innerHTML = data.assets
    .map(
      (a) =>
        `<div class="asset-row"><span class="asset-icon">◇</span><div><strong>${escape(a.label)}</strong><span>${escape(a.kind === "splat" ? "Gaussian splat" : a.kind === "mesh" ? "Mesh asset" : "Inferred surface")}</span></div><span class="asset-tag">${a.initially_visible === false ? "LIBRARY" : a.collider_path ? "COLLIDER" : "VISUAL"}</span></div>`,
    )
    .join("");
}
function displayRevisions() {
  $("revision-select").innerHTML = data.revisions
    .map(
      (r) =>
        `<option value="${escape(r.id)}">${escape(r.status === "baseline" ? "Initial reconstruction" : r.label.slice(0, 55))} · ${escape(r.status)}</option>`,
    )
    .join("");
}
async function loadScene(id: string) {
  ready = false;
  rendering = true;
  $("loading").style.display = "flex";
  for (const e of loaded) {
    world.remove(e.root);
    e.splat?.dispose();
    disposeObject(e.root);
  }
  loaded.length = 0;
  data = await api("scenes/" + id);
  spark.visible = data.assets.some((asset) => asset.kind === "splat");
  $("scene-title").textContent = data.title;
  $("goal").textContent = data.goal;
  renderer.setClearColor(
    data.source_kind === "object_probe" ? "#66716a" : "#101919",
  );
  $("scene-type").textContent =
    data.source_kind === "object_probe"
      ? "OBJECT RECONSTRUCTION TEST"
      : data.source_kind === "synthetic_fixture"
        ? "LABELED TEST FIXTURE"
        : "OFFICE RECONSTRUCTION";
  $("scene-warning").textContent =
    data.source_kind === "captured_room"
      ? ""
      : data.source_kind === "object_probe"
        ? "Isolated object probe · The office reconstruction has not been loaded."
        : "Synthetic test fixture · Not the captured office.";
  $("references").innerHTML =
    data.references
      .map(
        (r, i) =>
          `<a class="reference" href="${media(r)}" target="_blank" rel="noreferrer"><img src="${media(r)}" alt="Original reference ${i + 1}"><span>Reference ${String(i + 1).padStart(2, "0")} ↗</span></a>`,
      )
      .join("") +
    (data.video
      ? `<video controls preload="metadata" src="${media(data.video)}" aria-label="Source video"></video>`
      : "");
  $("source-count").textContent = String(
    data.references.length + (data.video ? 1 : 0),
  );
  $("source-note").textContent = data.description;
  $("cameras").innerHTML = Object.keys(data.cameras)
    .map(
      (c) =>
        `<button class="camera-button" data-camera="${escape(c)}">${escape(c)}</button>`,
    )
    .join("");
  document
    .querySelectorAll("[data-camera]")
    .forEach((b) =>
      b.addEventListener("click", () =>
        setCamera((b as HTMLElement).dataset.camera!),
      ),
    );
  await Promise.all(data.assets.map(loadAsset));
  displayAssets();
  displayRevisions();
  applyRevision(
    query.get("revision") &&
      data.revisions.some((r) => r.id === query.get("revision"))
      ? query.get("revision")!
      : data.current_revision,
  );
  setCamera(Object.keys(data.cameras)[0]);
  rendering = false;
  ready = true;
  $("loading").style.display = "none";
  $<HTMLTextAreaElement>("edit-json").value = JSON.stringify(
    {
      id: "edit-" + Date.now(),
      operation: "transform_asset",
      asset_id: data.assets[0]?.id,
      reason: "Describe the supported correction",
      evidence: [Object.keys(data.cameras)[0]],
      transform: data.assets[0]?.transform,
    },
    null,
    2,
  );
  await refreshEvents();
}

function safeAction(action: () => Promise<unknown> | unknown) {
  return async () => {
    try {
      await action();
    } catch (e) {
      $("notice").textContent = e instanceof Error ? e.message : String(e);
      $("notice").classList.add("error");
    }
  };
}
async function refreshEvents() {
  if (!data) return;
  const events = await api("scenes/" + data.id + "/events");
  if (!events.length) return;
  $("events").innerHTML = events
    .slice()
    .reverse()
    .map((e: any) => {
      const p = e.payload;
      const text =
        p.assessment?.reason ??
        p.assessment?.evidence ??
        p.reason ??
        p.error ??
        p.revision?.label ??
        p.outcome ??
        "";
      const views = p.after ?? p.views ?? (p.image ? [p] : []);
      return `<article class="event"><div class="event-title"><span class="event-dot ${e.kind.includes("reject") || e.kind.includes("fail") ? "bad" : ""}"></span><strong>${escape(e.kind.replaceAll("_", " "))}</strong><time>${escape(new Date(e.time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }))}</time></div>${text ? `<p>${escape(text)}</p>` : ""}${views.length ? `<div class="evidence-images">${views.map((v: any) => `<a href="${media(v.image)}" target="_blank"><img src="${media(v.image)}" alt="${escape(v.camera_name ?? "Inspection")}"></a>`).join("")}</div>` : ""}<details><summary>Evidence record</summary><pre>${escape(JSON.stringify(p, null, 2))}</pre></details></article>`;
    })
    .join("");
}
$("refresh").onclick = safeAction(refreshEvents);
$("scene-select").onchange = safeAction(() =>
  loadScene($<HTMLSelectElement>("scene-select").value),
);
$("revision-select").onchange = () =>
  applyRevision($<HTMLSelectElement>("revision-select").value);
$("original").onclick = () => applyRevision(data.revisions[0].id);
$("current").onclick = () => applyRevision(data.current_revision);
$("appearance").onchange = () =>
  loaded.forEach((e) => {
    if (e.splat) e.splat.visible = $<HTMLInputElement>("appearance").checked;
  });
$("colliders").onchange = () =>
  loaded.forEach((e) => {
    if (e.collider)
      e.collider.visible = $<HTMLInputElement>("colliders").checked;
  });
$("grid").onchange = () => (grid.visible = $<HTMLInputElement>("grid").checked);
$("export").onclick = () => {
  const blob = new Blob(
    [JSON.stringify({ ...data, inspection: metadata() }, null, 2)],
    { type: "application/json" },
  );
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = data.id + "-scene-record.json";
  a.click();
  URL.revokeObjectURL(url);
};
$("capture").onclick = safeAction(async () => {
  $("notice").textContent = "Saving and capturing this viewpoint…";
  const pose = metadata();
  const saved = await api(`scenes/${data.id}/cameras`, {
    camera: { position: pose.position, target: pose.target, fov: pose.fov },
    reason: "Capture the operator's current inspection viewpoint",
  });
  data.cameras[saved.name] = saved.camera;
  activeCamera = saved.name;
  const result = await api(`scenes/${data.id}/capture`, {
    camera: activeCamera,
    revision: activeRevision.id,
  });
  $("notice").textContent = "Inspection captured with camera metadata.";
  await refreshEvents();
  return result;
});
$("propose").onclick = safeAction(async () => {
  const edit = JSON.parse($<HTMLTextAreaElement>("edit-json").value);
  const r = await api(`scenes/${data.id}/edits`, edit);
  data = await api("scenes/" + data.id);
  displayRevisions();
  applyRevision(r.id);
  await refreshEvents();
});
for (const [button, accept] of [
  ["accept", true],
  ["reject", false],
] as const)
  $(button).onclick = safeAction(async () => {
    await api(`scenes/${data.id}/revisions/${activeRevision.id}/decision`, {
      accept,
      reason: "Explicit decision by the local operator",
    });
    data = await api("scenes/" + data.id);
    displayRevisions();
    applyRevision(data.current_revision);
    await refreshEvents();
  });
$("run-loop").onclick = safeAction(async () => {
  $<HTMLButtonElement>("run-loop").disabled = true;
  $("loop-state").textContent = "Inspecting";
  try {
    const j = await api(`scenes/${data.id}/loop`, {
      max_passes: Number($<HTMLSelectElement>("passes").value),
    });
    while (true) {
      await new Promise((r) => setTimeout(r, 2500));
      await refreshEvents();
      const state = await api("jobs/" + j.id);
      if (state.status !== "running") {
        if (state.status === "failed") throw new Error(state.error);
        break;
      }
    }
    data = await api("scenes/" + data.id);
    displayRevisions();
    applyRevision(data.current_revision);
    $("loop-state").textContent = "Complete";
    $("notice").textContent =
      "Loop finished. Inspect the evidence and any retained or rejected changes.";
  } catch (error) {
    $("loop-state").textContent = "Failed";
    throw error;
  } finally {
    $<HTMLButtonElement>("run-loop").disabled = false;
  }
});

async function start() {
  const [scenes, health] = await Promise.all([api("scenes"), api("health")]);
  $("connection").textContent = health.ok ? "Local workspace" : "Disconnected";
  $("scene-select").innerHTML = scenes
    .map(
      (s: any) => `<option value="${escape(s.id)}">${escape(s.title)}</option>`,
    )
    .join("");
  if (!scenes.length) {
    $("loading").innerHTML =
      "<p>No scene imported yet.<br>Use the import command to add a reconstruction.</p>";
    return;
  }
  const id = query.get("scene") ?? scenes[0].id;
  $<HTMLSelectElement>("scene-select").value = id;
  await loadScene(id);
}
safeAction(start)();
