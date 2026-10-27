// Sala dos Agentes em 3D — AURUM
// Cada agente é um boneco 3D sentado à sua mesa, com computador cuja tela mostra a sua função.
// Estados: "trabalhando" (digita, tela animada), "vigiando" (olha em volta, mexe o mouse),
// "pausa" (recosta e toma café de tempos em tempos), "erro" (tela vermelha).
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/OrbitControls.js';

const DADOS = window.SALA_DADOS;
const alvo = document.getElementById('sala3d');
const reduzir = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const COR_ESTADO = { trabalhando: '#00C176', vigiando: '#4DA3FF', pausa: '#8B919C', erro: '#FF4D4F' };
const ROTULO = { trabalhando: 'trabalhando', vigiando: 'vigiando', pausa: 'em pausa', erro: 'atenção' };

// ------------------------------------------------------------------ cena, câmera, luz
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.outputColorSpace = THREE.SRGBColorSpace;
alvo.appendChild(renderer.domElement);

const cena = new THREE.Scene();
cena.background = new THREE.Color('#0A0B0D');
cena.fog = new THREE.Fog('#0A0B0D', 22, 42);

const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
camera.position.set(0, 7.2, 13.2);
const controles = new OrbitControls(camera, renderer.domElement);
controles.target.set(0, 1, -0.5);
controles.enableDamping = true;
controles.autoRotate = !reduzir;
controles.autoRotateSpeed = 0.45;
controles.minDistance = 6;
controles.maxDistance = 26;
controles.maxPolarAngle = Math.PI * 0.47;
controles.addEventListener('start', () => { controles.autoRotate = false; });

cena.add(new THREE.HemisphereLight('#c3d3e6', '#2a2016', 1.15));
cena.add(new THREE.AmbientLight('#ffffff', 0.25));
const sol = new THREE.DirectionalLight('#fff4e0', 1.6);
sol.position.set(7, 14, 9);
sol.castShadow = true;
sol.shadow.mapSize.set(1024, 1024);
Object.assign(sol.shadow.camera, { left: -14, right: 14, top: 12, bottom: -12, near: 1, far: 40 });
cena.add(sol);
const luzOuro = new THREE.PointLight('#D4AF37', 1.2, 18);
luzOuro.position.set(0, 4.5, -6);
cena.add(luzOuro);

// ------------------------------------------------------------------ utilidades
const mat = (cor, extra = {}) => new THREE.MeshStandardMaterial({ color: cor, roughness: 0.75, metalness: 0.05, ...extra });
function caixa(w, h, d, cor, x = 0, y = 0, z = 0, pai = cena, extra = {}) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat(cor, extra));
  m.position.set(x, y, z); m.castShadow = true; m.receiveShadow = true; pai.add(m); return m;
}
function cilindro(rt, rb, h, cor, x = 0, y = 0, z = 0, pai = cena) {
  const m = new THREE.Mesh(new THREE.CylinderGeometry(rt, rb, h, 20), mat(cor));
  m.position.set(x, y, z); m.castShadow = true; pai.add(m); return m;
}
function esfera(r, cor, x = 0, y = 0, z = 0, pai = cena, extra = {}) {
  const m = new THREE.Mesh(new THREE.SphereGeometry(r, 24, 16, ...(extra.parcial || [])), mat(cor, extra.mat || {}));
  m.position.set(x, y, z); m.castShadow = true; pai.add(m); return m;
}
function canvasTextura(w, h) {
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  return { c, ctx: c.getContext('2d'), t };
}

// ------------------------------------------------------------------ sala
const piso = new THREE.Mesh(new THREE.PlaneGeometry(26, 20), mat('#14161B', { roughness: 0.95 }));
piso.rotation.x = -Math.PI / 2; piso.receiveShadow = true; cena.add(piso);
const grade = new THREE.GridHelper(26, 26, '#20242C', '#1A1D23'); grade.position.y = 0.002; cena.add(grade);
caixa(26, 6.5, 0.2, '#16181D', 0, 3.25, -9);           // parede do fundo
caixa(0.2, 6.5, 20, '#121419', -13, 3.25, 1);           // parede lateral
caixa(26, 0.15, 0.25, '#D4AF37', 0, 0.08, -8.85, cena, { metalness: 0.6, roughness: 0.3 }); // rodapé dourado

// janelas com a cidade (dia/noite pelo horário)
const noite = DADOS.hora >= 18 || DADOS.hora < 6;
function janela(x) {
  const { ctx, t, c } = canvasTextura(256, 256);
  const g = ctx.createLinearGradient(0, 0, 0, 256);
  g.addColorStop(0, noite ? '#050A16' : '#4C7FB0'); g.addColorStop(1, noite ? '#13223D' : '#9CC3E6');
  ctx.fillStyle = g; ctx.fillRect(0, 0, 256, 256);
  for (let i = 0; i < 14; i++) {
    const w = 14 + Math.random() * 22, h = 60 + Math.random() * 150, px = i * 19;
    ctx.fillStyle = noite ? '#0A1020' : '#3B5A78'; ctx.fillRect(px, 256 - h, w, h);
    if (noite) for (let k = 0; k < 10; k++) { ctx.fillStyle = Math.random() > .5 ? '#F5D76E' : '#26324A'; ctx.fillRect(px + 3 + (k % 3) * 5, 256 - h + 8 + Math.floor(k / 3) * 14, 3, 5); }
  }
  const m = new THREE.Mesh(new THREE.PlaneGeometry(4, 3), new THREE.MeshBasicMaterial({ map: t }));
  m.position.set(x, 3.6, -8.88); cena.add(m);
  caixa(4.2, 0.12, 0.12, '#2A2E36', x, 2.1, -8.85); caixa(4.2, 0.12, 0.12, '#2A2E36', x, 5.1, -8.85);
  caixa(0.12, 3.1, 0.12, '#2A2E36', x, 3.6, -8.85); caixa(0.12, 3.1, 0.12, '#2A2E36', x - 2.05, 3.6, -8.85); caixa(0.12, 3.1, 0.12, '#2A2E36', x + 2.05, 3.6, -8.85);
  c.dataset.ok = 1;
}
janela(-8.5); janela(8.5);

// painel da mesa de operações (com fita de cotações correndo)
const painel = canvasTextura(1024, 300);
const telao = new THREE.Mesh(new THREE.PlaneGeometry(9, 2.64), new THREE.MeshBasicMaterial({ map: painel.t }));
telao.position.set(0, 3.9, -8.86); cena.add(telao);
caixa(9.3, 2.9, 0.1, '#0A0B0D', 0, 3.9, -8.93);
function desenhaPainel(tempo) {
  const { ctx } = painel;
  ctx.fillStyle = '#07080A'; ctx.fillRect(0, 0, 1024, 300);
  ctx.strokeStyle = '#D4AF37'; ctx.lineWidth = 6; ctx.strokeRect(6, 6, 1012, 288);
  ctx.fillStyle = '#D4AF37'; ctx.font = '800 92px Inter, Arial, sans-serif'; ctx.textAlign = 'center';
  ctx.fillText('A U R U M', 512, 112);
  ctx.font = '600 30px "IBM Plex Mono", monospace'; ctx.fillStyle = '#8B919C';
  ctx.fillText('MESA DE OPERAÇÕES  ·', 440, 162);
  ctx.fillStyle = DADOS.pregao ? '#00C176' : '#8B919C';
  ctx.fillText(DADOS.pregao ? '● PREGÃO ABERTO' : '● PREGÃO FECHADO', 760, 162);
  // fita de cotações
  ctx.fillStyle = '#0F1114'; ctx.fillRect(14, 200, 996, 80);
  ctx.save(); ctx.beginPath(); ctx.rect(14, 200, 996, 80); ctx.clip();
  ctx.textAlign = 'left'; ctx.font = '600 34px "IBM Plex Mono", monospace';
  const itens = DADOS.fita.length ? DADOS.fita : [['AURUM', 0, 0]];
  const larg = 330, total = itens.length * larg;
  let x0 = 20 - ((tempo * 70) % total);
  for (let rep = 0; rep < 2; rep++) itens.forEach(([tk, p, v], i) => {
    const x = x0 + rep * total + i * larg;
    if (x < -larg || x > 1030) return;
    ctx.fillStyle = '#E8E6E1'; ctx.fillText(tk, x, 252);
    ctx.fillStyle = v > 0 ? '#00C176' : v < 0 ? '#FF4D4F' : '#8B919C';
    ctx.fillText(`${v > 0 ? '▲' : v < 0 ? '▼' : '■'} ${(v * 100).toFixed(2).replace('.', ',')}%`, x + 140, 252);
  });
  ctx.restore();
  painel.t.needsUpdate = true;
}

// plantas
for (const [x, z] of [[-11.5, -7.5], [11.5, -7.5], [-11.5, 8]]) {
  cilindro(0.45, 0.35, 0.8, '#3A2A1C', x, 0.4, z);
  esfera(0.75, '#2E7D5B', x, 1.35, z); esfera(0.55, '#3C9A6E', x + 0.3, 1.8, z - 0.1);
}

// ------------------------------------------------------------------ telas dos computadores (uma por função)
const TELAS = {
  aurum(ctx, t) {
    ctx.fillStyle = '#D4AF37'; ctx.font = '800 40px Inter, Arial'; ctx.textAlign = 'center'; ctx.fillText('AURUM', 128, 50);
    ['#00C176', '#D4AF37', '#FF4D4F', '#00C176', '#4DA3FF'].forEach((c, i) => {
      const h = 30 + 28 * (0.5 + 0.5 * Math.sin(t * 2 + i)); ctx.fillStyle = c; ctx.fillRect(28 + i * 42, 134 - h, 30, h);
    });
  },
  renda(ctx, t) {
    ctx.fillStyle = '#00C176'; ctx.font = '600 20px monospace'; ctx.textAlign = 'left'; ctx.fillText('R$ ↑ proventos', 14, 26);
    const fase = (t * 0.6) % 1;
    [16, 24, 31, 40, 50, 64].forEach((h, i) => { const k = Math.min(1, Math.max(0.15, fase * 1.6 - i * 0.12)); ctx.fillStyle = '#D4AF37'; ctx.fillRect(20 + i * 37, 134 - h * 1.4 * k, 26, h * 1.4 * k); });
  },
  fundamentos(ctx, t) {
    ctx.textAlign = 'left'; ctx.font = '700 22px monospace';
    for (let i = 0; i < 5; i++) {
      ctx.fillStyle = '#3B4A6B'; ctx.fillRect(18, 18 + i * 24, 140, 10);
      if ((t * 1.5) % 6 > i) { ctx.fillStyle = i === 3 ? '#FF4D4F' : '#00C176'; ctx.fillText(i === 3 ? '✗' : '✓', 175, 30 + i * 24); }
    }
    ctx.fillStyle = '#8B919C'; ctx.font = '600 18px monospace'; ctx.fillText('F-score', 196, 30);
  },
  valuation(ctx, t) {
    ctx.setLineDash([10, 7]); ctx.strokeStyle = '#00C176'; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(10, 44); ctx.lineTo(246, 44); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = '#00C176'; ctx.font = '600 16px monospace'; ctx.textAlign = 'left'; ctx.fillText('TETO', 196, 36);
    const pts = [[10, 80], [48, 70], [80, 96], [118, 86], [156, 112], [192, 100], [240, 118]];
    const n = Math.max(2, Math.floor(((t * 0.5) % 1) * pts.length * 1.3));
    ctx.strokeStyle = '#F5A623'; ctx.lineWidth = 5; ctx.beginPath();
    pts.slice(0, Math.min(n, pts.length)).forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.stroke();
  },
  tendencia(ctx, t) {
    const velas = [[80, 58, 46, 90], [58, 74, 50, 84], [74, 46, 36, 80], [46, 62, 38, 70], [62, 36, 26, 68], [36, 52, 28, 62]];
    velas.forEach(([o, c, hi, lo], i) => {
      const d = Math.sin(t * 3 + i) * 4; const x = 22 + i * 36; ctx.strokeStyle = ctx.fillStyle = c < o ? '#00C176' : '#FF4D4F';
      ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(x + 9, hi + d); ctx.lineTo(x + 9, lo + d); ctx.stroke();
      ctx.fillRect(x, Math.min(o, c) + d, 18, Math.abs(o - c) || 2);
    });
    ctx.strokeStyle = '#4DA3FF'; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(14, 82); ctx.lineTo(242, 40); ctx.stroke();
  },
  noticias(ctx, t) {
    ctx.fillStyle = '#E8E6E1'; ctx.fillRect(14, 12, 228, 18);
    ctx.save(); ctx.beginPath(); ctx.rect(0, 38, 256, 106); ctx.clip();
    const off = (t * 22) % 60;
    for (let k = 0; k < 4; k++) {
      const y = 42 + k * 60 - off; ctx.fillStyle = ['#5E4B8B', '#2E7D5B', '#7A2E4A', '#1E5F8C'][k];
      ctx.fillRect(14, y, 80, 48); ctx.fillStyle = '#8B919C';
      for (let l = 0; l < 5; l++) ctx.fillRect(104, y + 4 + l * 10, 130 - (l % 2) * 30, 5);
    }
    ctx.restore();
  },
  previsor(ctx, t) {
    ctx.beginPath(); ctx.moveTo(10, 130);
    for (let x = 10; x <= 246; x += 4) ctx.lineTo(x, 130 - 100 * Math.exp(-((x - 128) ** 2) / 2600));
    ctx.fillStyle = 'rgba(179,136,255,.25)'; ctx.fill(); ctx.strokeStyle = '#B388FF'; ctx.lineWidth = 3; ctx.stroke();
    const mx = 128 + Math.sin(t) * 60; ctx.setLineDash([5, 5]); ctx.strokeStyle = '#F5A623'; ctx.beginPath(); ctx.moveTo(mx, 20); ctx.lineTo(mx, 130); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = '#F5A623'; ctx.font = '700 22px monospace'; ctx.textAlign = 'left'; ctx.fillText(`${Math.round(50 + Math.sin(t) * 12)}%`, mx + 6, 40);
  },
  risco(ctx, t) {
    ctx.strokeStyle = 'rgba(0,193,118,.5)'; ctx.lineWidth = 2;
    [50, 30].forEach(r => { ctx.beginPath(); ctx.arc(176, 72, r, 0, Math.PI * 2); ctx.stroke(); });
    const a = t * 2.5; ctx.strokeStyle = '#00C176'; ctx.lineWidth = 4; ctx.beginPath(); ctx.moveTo(176, 72); ctx.lineTo(176 + Math.cos(a) * 50, 72 + Math.sin(a) * 50); ctx.stroke();
    ctx.fillStyle = Math.sin(t * 4) > 0 ? '#FF4D4F' : '#3a1515'; ctx.beginPath(); ctx.arc(196, 50, 5, 0, 7); ctx.fill();
    ctx.fillStyle = '#2F3B2F'; ctx.strokeStyle = '#00C176'; ctx.beginPath(); ctx.moveTo(56, 22); ctx.lineTo(96, 34); ctx.lineTo(96, 70);
    ctx.quadraticCurveTo(96, 110, 56, 124); ctx.quadraticCurveTo(16, 110, 16, 70); ctx.lineTo(16, 34); ctx.closePath(); ctx.fill(); ctx.stroke();
    ctx.fillStyle = '#00C176'; ctx.font = '700 36px Arial'; ctx.textAlign = 'center'; ctx.fillText('✓', 56, 86);
  },
  proventos(ctx, t) {
    ctx.fillStyle = 'rgba(0,193,118,.15)'; ctx.fillRect(16, 30, 224, 40); ctx.strokeStyle = '#00C176'; ctx.setLineDash([6, 4]); ctx.strokeRect(16, 30, 224, 40); ctx.setLineDash([]);
    for (let i = 0; i < 12; i++) {
      const h = 40 + 30 * (0.5 + 0.5 * Math.sin(i * 0.9)) * Math.min(1, Math.max(0, t * 0.6 - i * 0.15 + 1));
      ctx.fillStyle = '#D4AF37'; ctx.fillRect(18 + i * 19, 134 - h, 14, h);
    }
    ctx.fillStyle = '#00C176'; ctx.font = '700 18px monospace'; ctx.textAlign = 'left'; ctx.fillText('R$ 12 MESES', 20, 24);
  },
  entrada(ctx, t) {
    ctx.strokeStyle = '#4DA3FF'; ctx.lineWidth = 3; ctx.beginPath();
    for (let x = 10; x <= 246; x += 6) { const y = 60 + Math.sin(x / 18 + t * 1.5) * 22 + Math.sin(x / 7) * 6; x === 10 ? ctx.moveTo(x, y) : ctx.lineTo(x, y); }
    ctx.stroke(); ctx.setLineDash([8, 6]); ctx.strokeStyle = '#00C176'; ctx.beginPath(); ctx.moveTo(10, 96); ctx.lineTo(246, 96); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = Math.sin(t * 4) > 0 ? '#00C176' : '#0b3a24'; ctx.beginPath(); ctx.arc(170, 96, 7, 0, 7); ctx.fill();
    ctx.fillStyle = '#00C176'; ctx.font = '700 16px monospace'; ctx.textAlign = 'left'; ctx.fillText('ORDEM 80%', 14, 128);
  },
  conjunto(ctx, t) {
    ['#00C176', '#4DA3FF', '#F5A623', '#B388FF', '#FF4D4F', '#E8E6E1'].forEach((c, i) => {
      ctx.strokeStyle = c; ctx.globalAlpha = 0.5 + 0.5 * Math.abs(Math.sin(t * 2 + i)); ctx.lineWidth = 3;
      ctx.beginPath(); ctx.moveTo(14, 18 + i * 21); ctx.lineTo(150, 72); ctx.stroke();
    });
    ctx.globalAlpha = 1; ctx.fillStyle = '#234A6B'; ctx.beginPath(); ctx.arc(170, 72, 30, 0, 7); ctx.fill(); ctx.strokeStyle = '#4DA3FF'; ctx.stroke();
    ctx.fillStyle = '#E8E6E1'; ctx.font = '700 22px monospace'; ctx.textAlign = 'center'; ctx.fillText(`${Math.round(52 + Math.sin(t) * 3)}%`, 170, 80);
  },
  atlas(ctx, t) {
    ctx.fillStyle = '#1E3A5F'; ctx.beginPath(); ctx.arc(100, 72, 52, 0, 7); ctx.fill(); ctx.strokeStyle = '#4DA3FF'; ctx.lineWidth = 2; ctx.stroke();
    ctx.beginPath(); ctx.ellipse(100, 72, Math.abs(Math.cos(t)) * 52 + 2, 52, 0, 0, 7); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(48, 72); ctx.lineTo(152, 72); ctx.stroke();
    const lx = 150 + Math.cos(t * 0.9) * 50, ly = 72 + Math.sin(t * 1.3) * 30;
    ctx.strokeStyle = '#F5A623'; ctx.lineWidth = 6; ctx.beginPath(); ctx.arc(lx, ly, 20, 0, 7); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(lx + 14, ly + 14); ctx.lineTo(lx + 34, ly + 34); ctx.stroke();
  },
};

// ------------------------------------------------------------------ rótulo flutuante (nome + estado)
function rotulo(nome, cargo, estado) {
  const { c, ctx, t } = canvasTextura(512, 150);
  ctx.fillStyle = 'rgba(10,11,13,.82)'; ctx.strokeStyle = '#D4AF37'; ctx.lineWidth = 4;
  ctx.beginPath(); ctx.roundRect(6, 6, 500, 110, 14); ctx.fill(); ctx.stroke();
  ctx.fillStyle = '#E8E6E1'; ctx.font = '800 46px Inter, Arial'; ctx.textAlign = 'left'; ctx.fillText(nome, 26, 60);
  ctx.fillStyle = '#8B919C'; ctx.font = '500 26px Inter, Arial'; ctx.fillText(cargo, 26, 98);
  ctx.fillStyle = COR_ESTADO[estado] || '#8B919C'; ctx.font = '700 26px monospace'; ctx.textAlign = 'right';
  ctx.fillText(`● ${ROTULO[estado] || estado}`, 490, 60);
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, depthTest: false, transparent: true }));
  s.scale.set(3.3, 0.97, 1); s.renderOrder = 10; c.dataset.ok = 1;
  return s;
}
function balao(texto) {
  const { ctx, t } = canvasTextura(128, 64);
  ctx.fillStyle = '#20242C'; ctx.beginPath(); ctx.roundRect(4, 4, 120, 48, 20); ctx.fill();
  ctx.fillStyle = '#E8E6E1'; ctx.font = '700 30px Arial'; ctx.textAlign = 'center'; ctx.fillText(texto, 64, 40);
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, depthTest: false, transparent: true }));
  s.scale.set(1.0, 0.5, 1); s.renderOrder = 11; return s;
}

// ------------------------------------------------------------------ o agente: mesa + cadeira + boneco
function agente(dado, x, z) {
  const ap = dado.aparencia;
  const raiz = new THREE.Group(); raiz.position.set(x, 0, z); cena.add(raiz);

  // mesa
  caixa(2.6, 0.1, 1.2, '#6B4F2E', 0, 0.82, 0, raiz);
  for (const [lx, lz] of [[-1.2, -0.5], [1.2, -0.5], [-1.2, 0.5], [1.2, 0.5]]) caixa(0.08, 0.8, 0.08, '#4A361F', lx, 0.4, lz, raiz);
  const placa = rotuloMesa(dado.nome); placa.position.set(0.9, 0.9, 0.58); raiz.add(placa);
  caixa(0.9, 0.04, 0.3, '#30353F', 0, 0.89, 0.25, raiz);                 // teclado
  // monitor
  caixa(0.08, 0.35, 0.08, '#30353F', 0, 1.05, -0.35, raiz);
  caixa(0.5, 0.04, 0.3, '#30353F', 0, 0.89, -0.35, raiz);
  caixa(1.5, 0.92, 0.07, '#1A1D23', 0, 1.62, -0.38, raiz);
  const tela = canvasTextura(256, 144);
  const ativo = dado.estado === 'trabalhando' || dado.estado === 'vigiando';
  const telaMesh = new THREE.Mesh(new THREE.PlaneGeometry(1.38, 0.8), new THREE.MeshBasicMaterial({ map: tela.t }));
  telaMesh.position.set(0, 1.62, -0.343); raiz.add(telaMesh);
  const brilho = new THREE.PointLight(dado.estado === 'erro' ? '#FF4D4F' : '#6FB7FF', ativo ? 0.5 : 0, 3);
  brilho.position.set(0, 1.6, 0.2); raiz.add(brilho);

  // cadeira
  const cadeira = new THREE.Group(); cadeira.position.set(0, 0, 1.05); raiz.add(cadeira);
  caixa(0.7, 0.08, 0.66, '#2A2E36', 0, 0.55, 0, cadeira);
  const encosto = caixa(0.7, 0.85, 0.08, '#2A2E36', 0, 1.0, 0.34, cadeira);
  cilindro(0.04, 0.04, 0.5, '#2A2E36', 0, 0.28, 0, cadeira);
  cilindro(0.38, 0.38, 0.05, '#1A1C21', 0, 0.04, 0, cadeira);

  // boneco (de costas para a câmera, de frente para o monitor)
  const boneco = new THREE.Group(); boneco.position.set(0, 0, 1.05); raiz.add(boneco);
  const roupa = ap.roupa, pele = ap.pele, calca = '#2B2F38';
  for (const s of [-1, 1]) {
    caixa(0.17, 0.17, 0.55, calca, s * 0.13, 0.66, -0.22, boneco);          // coxas
    caixa(0.15, 0.55, 0.15, calca, s * 0.13, 0.36, -0.5, boneco);           // canelas
    caixa(0.17, 0.08, 0.26, '#111', s * 0.13, 0.05, -0.56, boneco);         // sapatos
  }
  const corpo = new THREE.Group(); corpo.position.set(0, 0.66, 0.02); boneco.add(corpo);
  const tronco = new THREE.Mesh(new THREE.CapsuleGeometry(0.27, 0.42, 6, 16), mat(roupa));
  tronco.position.y = 0.42; tronco.castShadow = true; corpo.add(tronco);
  if (ap.acessorio === 'gravata') caixa(0.08, 0.3, 0.02, '#D4AF37', 0, 0.55, -0.27, corpo, { metalness: 0.5 });
  const cabeca = new THREE.Group(); cabeca.position.set(0, 0.92, 0); corpo.add(cabeca);
  cilindro(0.08, 0.09, 0.14, pele, 0, 0.04, 0, cabeca);                     // pescoço
  esfera(0.24, pele, 0, 0.3, 0, cabeca);
  esfera(0.255, ap.cabelo, 0, 0.33, 0.02, cabeca, { parcial: [0, Math.PI * 2, 0, Math.PI * 0.55] });
  if (ap.estilo === 'longo') caixa(0.44, 0.5, 0.12, ap.cabelo, 0, 0.15, 0.17, cabeca);
  if (ap.acessorio === 'oculos') for (const s of [-1, 1]) {
    const lente = new THREE.Mesh(new THREE.TorusGeometry(0.06, 0.012, 8, 20), mat('#111')); lente.position.set(s * 0.09, 0.32, -0.23); cabeca.add(lente);
  }
  if (ap.acessorio === 'bone') { cilindro(0.26, 0.26, 0.12, '#2F3B2F', 0, 0.48, 0, cabeca); caixa(0.3, 0.03, 0.25, '#2F3B2F', 0, 0.43, -0.3, cabeca); }
  if (ap.acessorio === 'chapeu') { cilindro(0.42, 0.42, 0.03, '#8B6B3E', 0, 0.45, 0, cabeca); cilindro(0.22, 0.25, 0.26, '#8B6B3E', 0, 0.58, 0, cabeca); }
  if (ap.acessorio === 'tiara') { const ti = new THREE.Mesh(new THREE.TorusGeometry(0.25, 0.025, 8, 24, Math.PI), mat('#B388FF')); ti.position.set(0, 0.33, 0); ti.rotation.y = Math.PI / 2; cabeca.add(ti); }

  function braco(lado) {
    const ombro = new THREE.Group(); ombro.position.set(lado * 0.33, 0.68, 0); corpo.add(ombro);
    const b = cilindro(0.075, 0.07, 0.6, roupa, 0, -0.3, 0, ombro);
    const mao = esfera(0.08, pele, 0, -0.62, 0, ombro);
    return { ombro, b, mao };
  }
  const esq = braco(-1), dir = braco(1);
  const caneca = new THREE.Group(); dir.mao.add(caneca);
  cilindro(0.07, 0.065, 0.16, '#E8E6E1', 0, 0.02, -0.08, caneca);
  caneca.visible = dado.estado === 'pausa';

  const rot = rotulo(dado.nome, dado.cargo, dado.estado); rot.position.set(0, 3.0, 0.9); raiz.add(rot);
  const fala = balao(dado.estado === 'trabalhando' ? '• • •' : dado.estado === 'vigiando' ? '👀' : dado.estado === 'erro' ? '!' : 'zZ');
  fala.position.set(-0.55, 2.25, 1.0); raiz.add(fala);

  const fase = Math.random() * 10;
  return { dado, tela, telaMesh, ativo, corpo, cabeca, esq, dir, fala, rot, encosto, fase };
}
function rotuloMesa(nome) {
  const { ctx, t } = canvasTextura(256, 64);
  ctx.fillStyle = '#D4AF37'; ctx.fillRect(0, 0, 256, 64); ctx.fillStyle = '#111'; ctx.font = '800 34px monospace'; ctx.textAlign = 'center';
  ctx.fillText(nome.toUpperCase(), 128, 44);
  const m = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.15, 0.03), [mat('#D4AF37'), mat('#D4AF37'), mat('#D4AF37'), mat('#D4AF37'), new THREE.MeshBasicMaterial({ map: t }), mat('#D4AF37')]);
  return m;
}

// ------------------------------------------------------------------ monta a equipe
const NCOL = DADOS.agentes.length > 9 ? 4 : 3;           // equipe maior: 4 mesas por fileira
if (NCOL === 4) camera.position.set(0, 8.4, 16.2);        // afasta a câmera para caber a sala inteira
const agentes = DADOS.agentes.map((d, i) => {
  const col = i % NCOL, lin = Math.floor(i / NCOL);
  return agente(d, (col - (NCOL - 1) / 2) * (NCOL === 4 ? 5.6 : 6.4), (lin - 1) * 5.2 - 1.6);
});

// ------------------------------------------------------------------ animação
function desenhaTela(a, t) {
  const { ctx } = a.tela;
  ctx.fillStyle = a.dado.estado === 'erro' ? '#2A1010' : a.ativo ? '#0C1712' : '#07080A';
  ctx.fillRect(0, 0, 256, 144);
  if (a.ativo || a.dado.estado === 'erro') { (TELAS[a.dado.id] || (() => {}))(ctx, t); }
  else { ctx.globalAlpha = 0.25; (TELAS[a.dado.id] || (() => {}))(ctx, 0); ctx.globalAlpha = 1; ctx.fillStyle = '#3A404C'; ctx.font = '600 20px monospace'; ctx.textAlign = 'center'; ctx.fillText('em pausa', 128, 80); }
  a.tela.t.needsUpdate = true;
}

const relogio = new THREE.Clock();
const _v = new THREE.Vector3();
let quadro = 0;
function anima() {
  const t = relogio.getElapsedTime() * (reduzir ? 0.25 : 1);
  quadro++;
  for (const a of agentes) {
    const tt = t + a.fase;
    a.corpo.scale.y = 1 + 0.015 * Math.sin(tt * 2.2);                         // respiração
    const e = a.dado.estado;
    if (e === 'trabalhando') {
      a.corpo.rotation.x = -0.12;                                           // inclinado para a tela
      a.esq.ombro.rotation.x = 1.15 + 0.10 * Math.sin(tt * 15);
      a.dir.ombro.rotation.x = 1.15 + 0.10 * Math.sin(tt * 15 + Math.PI);
      a.esq.ombro.rotation.z = -0.25; a.dir.ombro.rotation.z = 0.25;
      a.cabeca.rotation.x = -0.05 + 0.05 * Math.sin(tt * 2); a.cabeca.rotation.y = 0.08 * Math.sin(tt * 0.7);
    } else if (e === 'vigiando') {
      a.corpo.rotation.x = -0.05;
      a.cabeca.rotation.y = 0.55 * Math.sin(tt * 0.8);                      // olha de um lado a outro
      a.esq.ombro.rotation.x = 1.05; a.esq.ombro.rotation.z = -0.25;
      a.dir.ombro.rotation.x = 1.0 + 0.06 * Math.sin(tt * 3); a.dir.ombro.rotation.z = 0.45 + 0.08 * Math.sin(tt * 2);   // mouse
    } else {                                                                // pausa / erro
      a.corpo.rotation.x = 0.22;                                            // recostado
      a.encosto.rotation.x = 0.18;
      const ciclo = (tt % 7) / 7;                                           // a cada 7 s um gole de café
      const gole = ciclo > 0.55 && ciclo < 0.85 ? Math.sin((ciclo - 0.55) / 0.3 * Math.PI) : 0;
      a.dir.ombro.rotation.x = 0.55 + 1.9 * gole; a.dir.ombro.rotation.z = 0.15;
      a.esq.ombro.rotation.x = 0.35; a.esq.ombro.rotation.z = -0.15;
      a.cabeca.rotation.x = 0.12 + 0.25 * gole; a.cabeca.rotation.z = 0.05 * Math.sin(tt * 0.5);
    }
    a.fala.position.y = 2.25 + 0.05 * Math.sin(tt * 2);
    // etiquetas somem quando a câmera chega perto (para ver o boneco de pertinho)
    const dist = camera.position.distanceTo(a.rot.getWorldPosition(_v));
    const op = Math.min(1, Math.max(0, (dist - 4.5) / 3));
    a.rot.material.opacity = op; a.fala.material.opacity = Math.min(1, op + 0.3);
    if (quadro % 2 === 0) desenhaTela(a, tt);
  }
  if (quadro % 2 === 0) desenhaPainel(t);
  controles.update();
  renderer.render(cena, camera);
  requestAnimationFrame(anima);
}

function ajusta() {
  const w = alvo.clientWidth, h = alvo.clientHeight;
  renderer.setSize(w, h); camera.aspect = w / h;
  camera.fov = w < 600 ? 60 : 42; camera.updateProjectionMatrix();
}
new ResizeObserver(ajusta).observe(alvo);
ajusta();
anima();
document.getElementById('sala3d-carregando')?.remove();
