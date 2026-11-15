// The same 3D station as in the pitch deck (Anna on her chair, the robot arm on its trolley), posed for each exercise in the app.
// If WebGL is not available this module stops here and the app keeps its drawn figures.
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v)), lerp = (a, b, t) => a + (b - a) * t, ease = (t) => { t = clamp(t); return t * t * (3 - 2 * t); };
const V = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);
const canvas = document.createElement('canvas'); canvas.className = 'fig3d'; canvas.setAttribute('aria-hidden', 'true');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2)); renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.05;
renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
const scene = new THREE.Scene(); scene.background = new THREE.Color('#ECF3F4');
scene.environment = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), .04).texture;
const cam = new THREE.PerspectiveCamera(30, 1, .1, 50);
const key = new THREE.DirectionalLight('#ffffff', 2.4); key.position.set(1.6, 3.4, 2.6); key.castShadow = true; key.shadow.mapSize.set(2048, 2048); key.shadow.radius = 6; key.shadow.bias = -.0004; key.shadow.normalBias = .02;
Object.assign(key.shadow.camera, { left: -2, right: 2, top: 2.2, bottom: -1, near: .5, far: 9 }); scene.add(key);
const rim = new THREE.DirectionalLight('#CFE5E9', 1.2); rim.position.set(-3, 2, -3); scene.add(rim);
