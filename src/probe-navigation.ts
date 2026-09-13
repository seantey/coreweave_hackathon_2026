import * as THREE from "three";
import { Octree } from "three/addons/math/Octree.js";

/** Kinematic spherical probe against the current revision's triangle surfaces.
 * Units are scene units, not calibrated metres. Open mesh gaps remain traversable.
 */
export class ProbeNavigation {
  private tree = new Octree();
  triangleCount = 0;
  readonly radius = 0.12;

  rebuild(roots: THREE.Object3D[]) {
    this.tree.clear();
    this.tree.maxLevel = 8;
    this.tree.trianglesPerLeaf = 32;
    this.triangleCount = 0;
    for (const root of roots) {
      root.updateWorldMatrix(true, true);
      root.traverse(object => {
        if (!(object instanceof THREE.Mesh)) return;
        const geometry = object.geometry;
        const positions = geometry.getAttribute("position");
        const indices = geometry.index;
        for (let offset = 0; offset < (indices?.count ?? positions.count); offset += 3) {
          const vertices = [0, 1, 2].map(corner => new THREE.Vector3()
            .fromBufferAttribute(positions, indices ? indices.getX(offset + corner) : offset + corner)
            .applyMatrix4(object.matrixWorld));
          this.tree.addTriangle(new THREE.Triangle(vertices[0], vertices[1], vertices[2]));
          this.triangleCount++;
        }
      });
    }
    if (this.triangleCount) this.tree.build();
  }

  contact(position: THREE.Vector3) {
    const candidates: THREE.Triangle[] = [];
    this.tree.getSphereTriangles(new THREE.Sphere(position, this.radius), candidates);
    const closest = new THREE.Vector3();
    for (const triangle of candidates) {
      triangle.closestPointToPoint(position, closest);
      if (closest.distanceToSquared(position) < this.radius ** 2)
        return closest.clone();
    }
    return null;
  }

  move(start: THREE.Vector3, displacement: THREE.Vector3) {
    if (!this.triangleCount) return { position: start.clone(), blocked: true, reason: "No collision geometry", contact: null };
    // Substeps bound travel to half the probe radius, including low frame rates.
    const steps = Math.max(1, Math.ceil(displacement.length() / (this.radius * 0.5)));
    if (steps > 10000) throw new Error("Probe request exceeds maximum path length");
    let position = start.clone();
    const initialContact = this.contact(position);
    if (initialContact) return { position, blocked: true, reason: "Starting viewpoint intersects collision geometry; choose another camera", contact: initialContact.toArray() };
    for (let step = 1; step <= steps; step++) {
      const candidate = start.clone().addScaledVector(displacement, step / steps);
      const contact = this.contact(candidate);
      if (contact) return { position, blocked: true, reason: "Collision surface reached", contact: contact.toArray() };
      position = candidate;
    }
    return { position, blocked: false, reason: "No mesh contact along sampled path", contact: null };
  }
}
