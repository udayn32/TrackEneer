'use client'
import { useEffect, useState, useRef, useCallback } from 'react'
import { useSession } from 'next-auth/react'

const API = process.env.NEXT_PUBLIC_SCHEDULER_API?.replace(/\/$/, '') || 'http://localhost:5000'

const DIFF_COLORS = { easy: '#10b981', medium: '#f59e0b', hard: '#ef4444' }
const REL_COLORS = { PREREQUISITE_OF: '#f97316', PART_OF: '#8b5cf6', RELATED_TO: '#06b6d4', LEADS_TO: '#22c55e' }
const CAT_COLORS = {
    topic: '#3b82f6', subtopic: '#8b5cf6', skill: '#06b6d4', theorem: '#f59e0b',
    algorithm: '#ef4444', definition: '#10b981', formula: '#ec4899', default: '#64748b'
}

function MasteryBadge({ v }) {
    const pct = Math.round((v || 0) * 100)
    const color = pct >= 80 ? 'from-emerald-500 to-green-400' : pct >= 50 ? 'from-amber-500 to-yellow-400' : 'from-red-500 to-rose-400'
    return <span className={`px-2 py-0.5 rounded-full text-xs font-bold bg-gradient-to-r ${color} text-white`}>{pct}%</span>
}

/* ================================================================
   IEEE EduKG-STYLE KNOWLEDGE GRAPH
   Inspired by: "IEEE Guide for Architectural Framework and Application
   of Educational Knowledge Graphs"

   Ontology Layers (top → bottom):
     L0  Domain        — large diamond, gold
     L1  Topic         — rounded-rect, blue
     L2  Sub-topic     — circle, purple
     L3  Concept/Leaf  — small circle, teal/green/red by difficulty

   Edge Types with labeled arrows:
     PREREQUISITE_OF  — orange dashed
     PART_OF          — purple solid
     RELATED_TO       — cyan solid
     LEADS_TO         — green solid

   Features:
     • Layered force-directed layout: nodes attract to their tier's Y band
     • Always-visible labels inside / beside nodes
     • Curved, labeled edges with arrowheads
     • Mastery arc on outer ring
     • IEEE-style legend (bottom-left)
     • Bloom level badge on hover tooltip
     • Drag / pan / zoom
================================================================ */

// ── Ontology layer assignment ──────────────────────────────────
const LAYER_MAP = {
    domain: 0, topic: 1, subtopic: 2,
    skill: 3, theorem: 3, algorithm: 3,
    definition: 3, formula: 3, concept: 3, default: 2,
}
const LAYER_COLORS  = ['#f59e0b', '#3b82f6', '#8b5cf6', '#06b6d4']
const LAYER_NAMES   = ['Domain', 'Topic', 'Sub-topic', 'Concept']
const LAYER_RADII   = [32, 26, 18, 14]
const LAYER_Y_BANDS = [0.12, 0.35, 0.62, 0.85]   // fraction of canvas height

const REL_STYLE = {
    PREREQUISITE_OF: { color: '#f97316', dash: [6, 3], label: 'prerequisite' },
    PART_OF:         { color: '#8b5cf6', dash: [],      label: 'part of'      },
    RELATED_TO:      { color: '#06b6d4', dash: [3, 3],  label: 'related'      },
    LEADS_TO:        { color: '#22c55e', dash: [],       label: 'leads to'    },
}
const DIFF_BORDER = { easy: '#10b981', medium: '#f59e0b', hard: '#ef4444' }

function EduKGraph({ nodes: rawNodes, edges, onNodeClick }) {
    const canvasRef = useRef(null)
    const rafRef    = useRef(null)

    useEffect(() => {
        if (!canvasRef.current || rawNodes.length === 0) return
        const canvas = canvasRef.current
        const ctx    = canvas.getContext('2d')
        const dpr    = window.devicePixelRatio || 1

        const resize = () => {
            const rect = canvas.parentElement.getBoundingClientRect()
            canvas.width  = rect.width  * dpr
            canvas.height = rect.height * dpr
            canvas.style.width  = rect.width  + 'px'
            canvas.style.height = rect.height + 'px'
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
        }
        resize()
        const W = () => canvas.width  / dpr
        const H = () => canvas.height / dpr

        // Build adjacency
        const adjacency = {}
        rawNodes.forEach(n => { adjacency[n.name] = new Set() })
        edges.forEach(e => {
            adjacency[e.source]?.add(e.target)
            adjacency[e.target]?.add(e.source)
        })

        // Assign layers and initial positions (use backend layer if available)
        const layerBuckets = [[], [], [], []]
        rawNodes.forEach(n => {
            const layer = (n.layer != null && n.layer >= 0 && n.layer <= 3) ? n.layer : (LAYER_MAP[n.category] ?? LAYER_MAP.default)
            layerBuckets[layer].push(n.name)
        })

        const nodes = rawNodes.map(n => {
            const layer   = (n.layer != null && n.layer >= 0 && n.layer <= 3) ? n.layer : (LAYER_MAP[n.category] ?? LAYER_MAP.default)
            const bucket  = layerBuckets[layer]
            const pos     = bucket.indexOf(n.name)
            const total   = bucket.length || 1
            const xSpread = W() * 0.78
            const xStart  = W() * 0.11
            const yTarget = H() * LAYER_Y_BANDS[layer]
            return {
                ...n,
                layer,
                x: xStart + xSpread * ((pos + 0.5) / total) + (Math.random() - 0.5) * 30,
                y: yTarget + (Math.random() - 0.5) * 40,
                vx: 0, vy: 0,
                radius: LAYER_RADII[layer],
                connections: adjacency[n.name]?.size || 0,
                pinned: false,
            }
        })

        const nameIdx = {}
        nodes.forEach((n, i) => { nameIdx[n.name] = i })

        const cam   = { x: 0, y: 0, zoom: 1 }
        const mouse = {
            x: 0, y: 0, worldX: 0, worldY: 0,
            dragging: null, panning: false,
            panStartX: 0, panStartY: 0,
            camStartX: 0, camStartY: 0,
            hovered: null,
        }

        const screenToWorld = (sx, sy) => ({ x: (sx - cam.x) / cam.zoom, y: (sy - cam.y) / cam.zoom })

        // ── Physics ──────────────────────────────────────────────
        const REPULSION     = 7000
        const LINK_STRENGTH = 0.004
        const LINK_DIST     = 220
        const LAYER_PULL    = 0.012   // stronger vertical snapping to layer band
        const DAMPING       = 0.82
        const COOLING       = 0.997
        let   temperature   = 1.0

        function tick() {
            const N = nodes.length
            for (let i = 0; i < N; i++) {
                if (nodes[i].pinned) continue
                let fx = 0, fy = 0
                // Repulsion
                for (let j = 0; j < N; j++) {
                    if (i === j) continue
                    const dx = nodes[i].x - nodes[j].x
                    const dy = nodes[i].y - nodes[j].y
                    const d2 = dx * dx + dy * dy + 1
                    const f  = REPULSION / d2 * temperature
                    fx += (dx / Math.sqrt(d2)) * f
                    fy += (dy / Math.sqrt(d2)) * f
                }
                nodes[i].vx += fx
                nodes[i].vy += fy
            }
            // Link attraction
            edges.forEach(e => {
                const si = nameIdx[e.source], ti = nameIdx[e.target]
                if (si == null || ti == null) return
                const s = nodes[si], t = nodes[ti]
                const dx = t.x - s.x, dy = t.y - s.y
                const d  = Math.sqrt(dx * dx + dy * dy) + 1
                const f  = (d - LINK_DIST) * LINK_STRENGTH * temperature
                const fx = (dx / d) * f, fy = (dy / d) * f
                if (!s.pinned) { s.vx += fx; s.vy += fy }
                if (!t.pinned) { t.vx -= fx; t.vy -= fy }
            })
            // Layer gravity — pull each node toward its IEEE tier Y band
            const cx = W() / 2
            nodes.forEach(n => {
                if (n.pinned) return
                const targetY = H() * LAYER_Y_BANDS[n.layer]
                n.vy += (targetY - n.y) * LAYER_PULL * temperature
                n.vx += (cx - n.x) * 0.001 * temperature  // gentle horizontal centering
            })
            // Integrate
            nodes.forEach(n => {
                if (n.pinned) return
                n.vx *= DAMPING
                n.vy *= DAMPING
                n.x  += n.vx
                n.y  += n.vy
            })
            temperature = Math.max(0.015, temperature * COOLING)
        }

        // ── Drawing helpers ───────────────────────────────────────
        function drawRoundedRect(x, y, w, h, r) {
            ctx.beginPath()
            ctx.moveTo(x + r, y)
            ctx.lineTo(x + w - r, y)
            ctx.arcTo(x + w, y, x + w, y + r, r)
            ctx.lineTo(x + w, y + h - r)
            ctx.arcTo(x + w, y + h, x + w - r, y + h, r)
            ctx.lineTo(x + r, y + h)
            ctx.arcTo(x, y + h, x, y + h - r, r)
            ctx.lineTo(x, y + r)
            ctx.arcTo(x, y, x + r, y, r)
            ctx.closePath()
        }

        function drawDiamond(x, y, r) {
            ctx.beginPath()
            ctx.moveTo(x,     y - r)
            ctx.lineTo(x + r, y)
            ctx.lineTo(x,     y + r)
            ctx.lineTo(x - r, y)
            ctx.closePath()
        }

        function drawHexagon(x, y, r) {
            ctx.beginPath()
            for (let k = 0; k < 6; k++) {
                const a = (Math.PI / 3) * k - Math.PI / 6
                k === 0 ? ctx.moveTo(x + r * Math.cos(a), y + r * Math.sin(a))
                        : ctx.lineTo(x + r * Math.cos(a), y + r * Math.sin(a))
            }
            ctx.closePath()
        }

        function drawNodeShape(n, r, layer) {
            if (layer === 0) drawDiamond(n.x, n.y, r * 1.3)
            else if (layer === 1) {
                const hw = r * 2.2, hh = r * 1.2
                drawRoundedRect(n.x - hw, n.y - hh, hw * 2, hh * 2, 8)
            }
            else drawHexagon(n.x, n.y, r) // L2 + L3 → hexagon
        }

        // Word-wrap helper — splits text into max `maxLines` lines fitting `maxW`
        function wrapText(text, maxW, maxLines = 2) {
            const words = text.split(' ')
            const lines = []
            let cur = ''
            for (const word of words) {
                const test = cur ? cur + ' ' + word : word
                if (ctx.measureText(test).width <= maxW) {
                    cur = test
                } else {
                    if (cur) lines.push(cur)
                    cur = word
                    if (lines.length >= maxLines - 1) {
                        // last allowed line — append remaining words
                        const rest = words.slice(words.indexOf(word)).join(' ')
                        lines.push(rest)
                        cur = ''
                        break
                    }
                }
            }
            if (cur) lines.push(cur)
            return lines.slice(0, maxLines)
        }

        function arrowAt(tx, ty, angle, size, color, alpha) {
            ctx.save()
            ctx.globalAlpha = alpha
            ctx.fillStyle   = color
            ctx.beginPath()
            ctx.moveTo(tx + size * Math.cos(angle),       ty + size * Math.sin(angle))
            ctx.lineTo(tx + size * Math.cos(angle + 2.4), ty + size * Math.sin(angle + 2.4))
            ctx.lineTo(tx + size * Math.cos(angle - 2.4), ty + size * Math.sin(angle - 2.4))
            ctx.closePath()
            ctx.fill()
            ctx.restore()
        }

        function drawEdges() {
            edges.forEach(e => {
                const si = nameIdx[e.source], ti = nameIdx[e.target]
                if (si == null || ti == null) return
                const s = nodes[si], t = nodes[ti]
                const isHot = mouse.hovered !== null && (si === mouse.hovered || ti === mouse.hovered)
                const style = REL_STYLE[e.relation] || REL_STYLE.RELATED_TO
                const alpha = isHot ? 0.95 : 0.22

                // Bezier control point (gentle curve)
                const mx  = (s.x + t.x) / 2
                const my  = (s.y + t.y) / 2
                const perp = { x: -(t.y - s.y) * 0.18, y: (t.x - s.x) * 0.18 }
                const cpx  = mx + perp.x, cpy = my + perp.y

                ctx.save()
                ctx.setLineDash(style.dash)
                ctx.strokeStyle  = style.color
                ctx.lineWidth    = isHot ? 2.2 : 1.2
                ctx.globalAlpha  = alpha
                ctx.beginPath()
                ctx.moveTo(s.x, s.y)
                ctx.quadraticCurveTo(cpx, cpy, t.x, t.y)
                ctx.stroke()
                ctx.setLineDash([])
                ctx.restore()

                // Arrowhead near target
                const angle = Math.atan2(t.y - cpy, t.x - cpx)
                arrowAt(t.x - (t.radius + 4) * Math.cos(angle),
                        t.y - (t.radius + 4) * Math.sin(angle),
                        angle, 7, style.color, isHot ? 0.95 : 0.35)

                // Edge label on hover
                if (isHot && cam.zoom > 0.4) {
                    const lx = cpx, ly = cpy
                    const txt = style.label
                    ctx.save()
                    ctx.font      = '10px Inter, system-ui, sans-serif'
                    ctx.textAlign = 'center'
                    const tw = ctx.measureText(txt).width
                    ctx.fillStyle   = 'rgba(15,23,42,0.9)'
                    ctx.fillRect(lx - tw / 2 - 4, ly - 9, tw + 8, 14)
                    ctx.fillStyle  = style.color
                    ctx.globalAlpha = 1
                    ctx.fillText(txt, lx, ly + 1)
                    ctx.restore()
                }
            })
        }

        function drawNodes() {
            nodes.forEach((n, i) => {
                const isHov  = mouse.hovered === i
                const isDrag = mouse.dragging === i
                const isConn = mouse.hovered !== null && adjacency[n.name]?.has(nodes[mouse.hovered]?.name)
                const hot    = isHov || isDrag || isConn
                const dimmed = mouse.hovered !== null && !hot

                const layer  = n.layer
                const r      = n.radius * (isHov ? 1.35 : 1)
                const base   = LAYER_COLORS[layer]

                // Outer mastery arc (IEEE standard: learning progress ring)
                if (n.mastery > 0) {
                    ctx.beginPath()
                    ctx.arc(n.x, n.y, r + (layer <= 1 ? 6 : 4), -Math.PI / 2,
                            -Math.PI / 2 + Math.PI * 2 * n.mastery)
                    ctx.strokeStyle = n.mastery >= 0.8 ? '#10b981' : n.mastery >= 0.5 ? '#f59e0b' : '#ef4444'
                    ctx.lineWidth   = 2.5
                    ctx.globalAlpha = isHov ? 1 : 0.55
                    ctx.stroke()
                    ctx.globalAlpha = 1
                }

                // Glow halo
                if (hot) {
                    const g = ctx.createRadialGradient(n.x, n.y, r, n.x, n.y, r + 14)
                    g.addColorStop(0, base + '55')
                    g.addColorStop(1, 'transparent')
                    ctx.save()
                    drawNodeShape(n, r + 10, layer)
                    ctx.fillStyle = g; ctx.fill()
                    ctx.restore()
                }

                // Node shape fill
                ctx.save()
                ctx.globalAlpha = dimmed ? 0.28 : 1
                drawNodeShape(n, r, layer)
                const grad = ctx.createRadialGradient(n.x, n.y - r * 0.3, r * 0.1, n.x, n.y, r * 1.4)
                grad.addColorStop(0, base + 'dd')
                grad.addColorStop(1, base + '66')
                ctx.fillStyle = grad
                ctx.fill()

                // Shape border — color by difficulty
                ctx.strokeStyle = DIFF_BORDER[n.difficulty] || base
                ctx.lineWidth   = isHov ? 2.5 : 1.5
                ctx.stroke()
                ctx.restore()

                // ── Label ─────────────────────────────────────────
                // Always show for L0/L1; show for others on hover/connect/zoom
                const alwaysShow = layer <= 1
                const showLabel  = alwaysShow || isHov || isConn || isDrag || cam.zoom > 0.55

                if (showLabel) {
                    ctx.save()
                    ctx.globalAlpha  = dimmed ? 0.3 : 1
                    ctx.textAlign    = 'center'
                    ctx.textBaseline = 'middle'

                    if (layer <= 1) {
                        // ── Inside-shape label with word-wrap ──────
                        const fontSize = layer === 0 ? 12 : 11
                        ctx.font = `${layer === 0 ? '700' : '600'} ${fontSize}px Inter, system-ui, sans-serif`
                        const maxW  = layer === 0 ? r * 2.2 : r * 4.0
                        const lines = wrapText(n.name, maxW)
                        const lineH = fontSize + 3
                        const totalH = lines.length * lineH
                        ctx.fillStyle = '#f8fafc'
                        lines.forEach((line, li) => {
                            ctx.fillText(line, n.x, n.y - totalH / 2 + lineH * (li + 0.5))
                        })
                    } else {
                        // ── Full-text pill label below node ─────────
                        ctx.font = `500 11px Inter, system-ui, sans-serif`
                        const label = n.name   // no truncation — show full text
                        const tw    = ctx.measureText(label).width
                        const lx = n.x, ly = n.y + r + 16
                        ctx.fillStyle = 'rgba(15,23,42,0.88)'
                        ctx.beginPath()
                        ctx.roundRect(lx - tw / 2 - 6, ly - 8, tw + 12, 16, 5)
                        ctx.fill()
                        ctx.fillStyle = isHov ? '#e2e8f0' : '#cbd5e1'
                        ctx.fillText(label, lx, ly)
                    }
                    ctx.restore()
                }

                // Bloom level badge on hover (IEEE EduKG competency metadata)
                if (isHov && n.bloom_level) {
                    const badge  = `Bloom: ${n.bloom_level}`
                    ctx.font     = '10px Inter, system-ui, sans-serif'
                    const bw     = ctx.measureText(badge).width + 10
                    const bx     = n.x + r + 6, by = n.y - 8
                    ctx.fillStyle = 'rgba(30,41,59,0.95)'
                    ctx.beginPath()
                    ctx.roundRect(bx, by, bw, 16, 4)
                    ctx.fill()
                    ctx.fillStyle  = '#a5b4fc'
                    ctx.textAlign  = 'left'
                    ctx.textBaseline = 'top'
                    ctx.fillText(badge, bx + 5, by + 3)
                }
            })
        }

        function drawLegend() {
            const lx = 14, ly = H() - 160
            ctx.save()
            ctx.fillStyle   = 'rgba(15,23,42,0.88)'
            ctx.strokeStyle = 'rgba(99,102,241,0.35)'
            ctx.lineWidth   = 1
            ctx.beginPath()
            ctx.roundRect(lx, ly, 185, 148, 8)
            ctx.fill(); ctx.stroke()

            ctx.font      = '700 11px Inter, system-ui, sans-serif'
            ctx.fillStyle = '#e2e8f0'
            ctx.textAlign = 'left'
            ctx.textBaseline = 'top'
            ctx.fillText('IEEE EduKG Ontology', lx + 10, ly + 10)

            LAYER_NAMES.forEach((name, i) => {
                const y = ly + 30 + i * 20
                ctx.fillStyle   = LAYER_COLORS[i]
                ctx.strokeStyle = '#1e293b'
                ctx.lineWidth   = 1
                if (i === 0) { ctx.beginPath(); ctx.moveTo(lx+20, y+3); ctx.lineTo(lx+26,y-3); ctx.lineTo(lx+32,y+3); ctx.lineTo(lx+26,y+9); ctx.closePath(); ctx.fill() }
                else if (i === 1) { ctx.beginPath(); ctx.roundRect(lx+14, y-3, 24, 12, 3); ctx.fill() }
                else { ctx.beginPath(); ctx.arc(lx + 26, y + 3, i === 2 ? 7 : 5, 0, Math.PI * 2); ctx.fill() }
                ctx.fillStyle = '#94a3b8'
                ctx.font      = '500 10px Inter, system-ui, sans-serif'
                ctx.fillText(`L${i} ${name}`, lx + 42, y - 1)
            })

            // Relation lines
            let ry = ly + 112
            ctx.font = '700 10px Inter, system-ui, sans-serif'
            ctx.fillStyle = '#e2e8f0'
            ctx.fillText('Relations', lx + 10, ry)
            ry += 14
            Object.entries(REL_STYLE).forEach(([, s]) => {
                ctx.save()
                ctx.strokeStyle = s.color
                ctx.lineWidth   = 1.5
                ctx.setLineDash(s.dash)
                ctx.beginPath(); ctx.moveTo(lx + 12, ry + 4); ctx.lineTo(lx + 42, ry + 4); ctx.stroke()
                ctx.setLineDash([])
                ctx.restore()
                ctx.fillStyle    = '#94a3b8'
                ctx.font         = '500 10px Inter, system-ui, sans-serif'
                ctx.textBaseline = 'middle'
                ctx.fillText(s.label, lx + 48, ry + 4)
                ry += 16
            })

            ctx.restore()
        }

        function drawLayerBands() {
            LAYER_Y_BANDS.forEach((frac, i) => {
                const y = H() * frac
                ctx.save()
                ctx.strokeStyle = LAYER_COLORS[i] + '18'
                ctx.lineWidth   = 48
                ctx.beginPath()
                ctx.moveTo(0, y); ctx.lineTo(W(), y)
                ctx.stroke()

                ctx.font         = '600 10px Inter, system-ui, sans-serif'
                ctx.fillStyle    = LAYER_COLORS[i] + '55'
                ctx.textAlign    = 'right'
                ctx.textBaseline = 'middle'
                ctx.fillText(`L${i} ${LAYER_NAMES[i]}`, W() - 14, y)
                ctx.restore()
            })
        }

        function draw() {
            const w = W(), h = H()
            ctx.clearRect(0, 0, w, h)

            // Layer band guides (in canvas space, outside cam transform)
            drawLayerBands()

            ctx.save()
            ctx.translate(cam.x, cam.y)
            ctx.scale(cam.zoom, cam.zoom)
            drawEdges()
            drawNodes()
            ctx.restore()

            drawLegend()

            // HUD
            ctx.fillStyle    = '#475569'
            ctx.font         = '11px Inter, system-ui, sans-serif'
            ctx.textAlign    = 'right'
            ctx.textBaseline = 'alphabetic'
            ctx.fillText(`Zoom ${(cam.zoom * 100).toFixed(0)}%  •  scroll zoom  •  drag nodes/pan`, w - 12, h - 10)
        }

        function animate() { tick(); draw(); rafRef.current = requestAnimationFrame(animate) }
        animate()

        // ── Mouse events ──────────────────────────────────────────
        const getPos = (e) => { const r = canvas.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top } }
        const findAt = (wx, wy) => {
            for (let i = nodes.length - 1; i >= 0; i--) {
                const n = nodes[i]
                const dx = wx - n.x, dy = wy - n.y
                // L0 diamond / L1 round-rect are wider — use a larger hit radius
                const hitR = n.layer === 1 ? n.radius * 2.4
                           : n.layer === 0 ? n.radius * 1.5
                           : n.radius + 10
                if (dx * dx + dy * dy < hitR * hitR) return i
            }
            return null
        }

        const onDown = (e) => {
            const p = getPos(e), w = screenToWorld(p.x, p.y), idx = findAt(w.x, w.y)
            if (idx !== null) { mouse.dragging = idx; nodes[idx].pinned = true; temperature = Math.max(temperature, 0.3); canvas.style.cursor = 'grabbing' }
            else { mouse.panning = true; mouse.panStartX = p.x; mouse.panStartY = p.y; mouse.camStartX = cam.x; mouse.camStartY = cam.y; canvas.style.cursor = 'move' }
        }
        const onMove = (e) => {
            const p = getPos(e), w = screenToWorld(p.x, p.y)
            mouse.x = p.x; mouse.y = p.y; mouse.worldX = w.x; mouse.worldY = w.y
            if (mouse.dragging !== null) {
                nodes[mouse.dragging].x = w.x; nodes[mouse.dragging].y = w.y
                nodes[mouse.dragging].vx = 0;  nodes[mouse.dragging].vy = 0
                temperature = Math.max(temperature, 0.1)
            } else if (mouse.panning) {
                cam.x = mouse.camStartX + (p.x - mouse.panStartX)
                cam.y = mouse.camStartY + (p.y - mouse.panStartY)
            } else {
                mouse.hovered = findAt(w.x, w.y)
                canvas.style.cursor = mouse.hovered !== null ? 'pointer' : 'default'
            }
        }
        const onUp = () => {
            if (mouse.dragging !== null) nodes[mouse.dragging].pinned = false
            mouse.dragging = null; mouse.panning = false; canvas.style.cursor = 'default'
        }
        const onClick = (e) => {
            const p = getPos(e), w = screenToWorld(p.x, p.y), idx = findAt(w.x, w.y)
            if (idx !== null && onNodeClick) onNodeClick(nodes[idx])
        }
        const onWheel = (e) => {
            e.preventDefault()
            const p = getPos(e), factor = e.deltaY < 0 ? 1.12 : 0.89
            const nz = Math.max(0.15, Math.min(4, cam.zoom * factor))
            cam.x = p.x - (p.x - cam.x) * (nz / cam.zoom)
            cam.y = p.y - (p.y - cam.y) * (nz / cam.zoom)
            cam.zoom = nz
        }

        canvas.addEventListener('mousedown',  onDown)
        canvas.addEventListener('mousemove',  onMove)
        canvas.addEventListener('mouseup',    onUp)
        canvas.addEventListener('mouseleave', onUp)
        canvas.addEventListener('click',      onClick)
        canvas.addEventListener('wheel',      onWheel, { passive: false })
        window.addEventListener('resize',     resize)

        return () => {
            cancelAnimationFrame(rafRef.current)
            canvas.removeEventListener('mousedown',  onDown)
            canvas.removeEventListener('mousemove',  onMove)
            canvas.removeEventListener('mouseup',    onUp)
            canvas.removeEventListener('mouseleave', onUp)
            canvas.removeEventListener('click',      onClick)
            canvas.removeEventListener('wheel',      onWheel)
            window.removeEventListener('resize',     resize)
        }
    }, [rawNodes, edges, onNodeClick])

    return (
        <div className="w-full h-[780px] relative">
            <canvas ref={canvasRef} className="w-full h-full rounded-xl" style={{ background: 'linear-gradient(180deg,#0a0f1e 0%,#0f172a 60%,#0a0f1e 100%)' }} />
        </div>
    )
}


/* ================================================================
   MAIN PAGE
================================================================ */
export default function KnowledgeGraphPage() {
    const { data: session } = useSession()
    const [graph, setGraph] = useState({ nodes: [], edges: [] })
    const [loading, setLoading] = useState(true)
    const [selected, setSelected] = useState(null)
    const [uploadFile, setUploadFile] = useState(null)
    const [uploading, setUploading] = useState(false)
    const [buildText, setBuildText] = useState('')
    const [building, setBuilding] = useState(false)
    const [tab, setTab] = useState('graph')
    const [rootCause, setRootCause] = useState(null)
    const [weaknesses, setWeaknesses] = useState([])
    const [catFilter, setCatFilter] = useState('all')
    const [documents, setDocuments] = useState([])
    const [selectedDoc, setSelectedDoc] = useState('all')
    const [preprocessLog, setPreprocessLog] = useState(null)
    const [conceptSearch, setConceptSearch] = useState('')
    const [conceptSort, setConceptSort] = useState('layer')
    const email = session?.user?.email || ''

    // Fetch list of source documents
    const fetchDocuments = useCallback(async () => {
        if (!email) return
        try {
            const r = await fetch(`${API}/api/knowledge-graph/documents?email=${encodeURIComponent(email)}`)
            if (!r.ok) throw new Error('Failed to fetch docs')
            const d = await r.json()
            setDocuments(d.documents || [])
        } catch (e) {
            console.error("fetchDocuments error:", e)
            setDocuments([])
        }
    }, [email])

    const fetchGraph = useCallback(async (docFilter) => {
        if (!email) return
        try {
            setLoading(true)
            const doc = docFilter !== undefined ? docFilter : selectedDoc
            let url = `${API}/api/knowledge-graph?email=${encodeURIComponent(email)}`
            if (doc && doc !== 'all') {
                url += `&source_document=${encodeURIComponent(doc)}`
            }
            const r = await fetch(url)
            if (!r.ok) throw new Error('Failed to fetch graph')
            const d = await r.json()
            setGraph({ nodes: d.nodes || [], edges: d.edges || [] })
        } catch (e) {
            console.error("fetchGraph error:", e)
            setGraph({ nodes: [], edges: [] })
        } finally {
            setLoading(false)
        }
    }, [email, selectedDoc])

    useEffect(() => { fetchDocuments() }, [fetchDocuments])
    useEffect(() => { fetchGraph() }, [fetchGraph])

    const handleDocChange = (doc) => {
        setSelectedDoc(doc)
        fetchGraph(doc)
    }

    const fetchWeaknesses = async () => {
        try {
            const r = await fetch(`${API}/api/knowledge-graph/weaknesses?email=${encodeURIComponent(email)}`)
            const d = await r.json()
            setWeaknesses(d.weaknesses || [])
        } catch (e) { console.error(e) }
    }

    const fetchRootCause = async (name) => {
        try {
            const r = await fetch(`${API}/api/knowledge-graph/root-cause/${encodeURIComponent(name)}?email=${encodeURIComponent(email)}`)
            setRootCause(await r.json())
        } catch (e) { console.error(e) }
    }

    const handleUpload = async () => {
        if (!uploadFile) return
        const fileName = uploadFile.name
        setUploading(true)
        setPreprocessLog(null)
        try {
            const fd = new FormData()
            fd.append('file', uploadFile)
            fd.append('email', email)
            fd.append('strategy', 'llm')
            const uploadRes = await fetch(`${API}/api/knowledge-graph/upload`, { method: 'POST', body: fd })
            const uploadData = await uploadRes.json().catch(() => ({}))
            if (uploadData.preprocessing_stats) setPreprocessLog(uploadData.preprocessing_stats)

            // Upload now processes synchronously — refresh documents and graph immediately
            const docsRes = await fetch(`${API}/api/knowledge-graph/documents?email=${encodeURIComponent(email)}`)
            const docsData = await docsRes.json().catch(() => ({}))
            const docs = docsData.documents || []
            setDocuments(docs)
            const found = docs.find(doc => doc.document === fileName)
            if (found) {
                setSelectedDoc(fileName)
                fetchGraph(fileName)
                setTab('graph')
            } else {
                fetchGraph()
            }
        } catch (e) { console.error(e) }
        finally { setUploading(false); setUploadFile(null) }
    }

    const handleBuildText = async () => {
        if (!buildText.trim()) return
        setBuilding(true)
        setPreprocessLog(null)
        try {
            const fd = new FormData()
            fd.append('text', buildText)
            fd.append('email', email)
            fd.append('strategy', 'llm')
            const buildRes = await fetch(`${API}/api/knowledge-graph/build`, { method: 'POST', body: fd })
            const buildData = await buildRes.json().catch(() => ({}))
            if (buildData.preprocessing_stats) setPreprocessLog(buildData.preprocessing_stats)
            setBuildText('')
            fetchGraph()
            fetchDocuments()
        } catch (e) { console.error(e) }
        finally { setBuilding(false) }
    }

    const handleEnrich = async () => {
        const fd = new FormData(); fd.append('email', email)
        await fetch(`${API}/api/knowledge-graph/enrich`, { method: 'POST', body: fd })
        fetchGraph()
    }

    const handleNodeClick = (node) => {
        setSelected(node)
        fetchRootCause(node.name)
    }

    // Category filtering for graph view
    const categories = [...new Set(graph.nodes.map(n => n.category || 'default'))]
    const filteredNodes = catFilter === 'all' ? graph.nodes : graph.nodes.filter(n => (n.category || 'default') === catFilter)
    const filteredNodeNames = new Set(filteredNodes.map(n => n.name))
    const filteredEdges = graph.edges.filter(e => filteredNodeNames.has(e.source) && filteredNodeNames.has(e.target))

    return (
        <main className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 p-6">
            <div className="absolute inset-0 overflow-hidden pointer-events-none">
                <div className="absolute top-0 left-0 w-[500px] h-[500px] bg-gradient-to-br from-violet-500/10 via-purple-500/5 to-transparent rounded-full blur-3xl" />
                <div className="absolute bottom-0 right-0 w-[600px] h-[600px] bg-gradient-to-tl from-cyan-500/10 via-blue-500/5 to-transparent rounded-full blur-3xl" />
            </div>
            <div className="relative z-10 max-w-7xl mx-auto">
                {/* Header */}
                <div className="flex items-center justify-between mb-6">
                    <div>
                        <h1 className="text-3xl font-bold text-white flex items-center gap-3">🧠 Knowledge Graph</h1>
                        <p className="text-slate-400 mt-1">Interactive force-directed concept map — drag nodes, scroll to zoom, pan the view</p>
                    </div>
                    <div className="flex gap-3">
                        <a href="/dashboard" className="px-4 py-2 bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700 transition">← Dashboard</a>
                        <button onClick={handleEnrich} className="px-4 py-2 bg-gradient-to-r from-violet-500 to-purple-500 text-white rounded-lg hover:shadow-lg hover:shadow-violet-500/25 transition">✨ Enrich with AI</button>
                    </div>
                </div>

                {/* Tabs */}
                <div className="flex gap-2 mb-6">
                    {['graph', 'concepts', 'build', 'analysis'].map(t => (
                        <button key={t} onClick={() => { setTab(t); if (t === 'analysis') fetchWeaknesses() }}
                            className={`px-4 py-2 rounded-lg font-medium transition ${tab === t ? 'bg-gradient-to-r from-cyan-500 to-blue-500 text-white shadow-lg shadow-cyan-500/25' : 'bg-slate-800 text-slate-400 hover:text-white'}`}>
                            {t === 'graph' ? '🔗 Graph' : t === 'concepts' ? '📚 Concepts' : t === 'build' ? '🏗️ Build' : '🔍 Analysis'}
                        </button>
                    ))}
                </div>

                {loading ? (
                    <div className="flex items-center justify-center h-96">
                        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-cyan-400" />
                    </div>
                ) : (
                    <>
                        {/* ── Graph Tab ── */}
                        {tab === 'graph' && (
                            <div className="bg-slate-800/60 backdrop-blur-sm rounded-2xl border border-slate-700/50 p-4">
                                {/* Document Selector */}
                                {documents.length > 0 && (
                                    <div className="flex items-center gap-2 mb-3 p-3 bg-slate-900/60 rounded-xl border border-slate-700/40">
                                        <span className="text-slate-400 text-sm">📄 Document:</span>
                                        <select value={selectedDoc} onChange={e => handleDocChange(e.target.value)}
                                            className="flex-1 bg-slate-700 border border-slate-600 text-slate-200 text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-cyan-500">
                                            <option value="all">All Documents ({graph.nodes.length} concepts)</option>
                                            {documents.map(d => (
                                                <option key={d.document} value={d.document}>{d.document} ({d.concept_count} concepts)</option>
                                            ))}
                                        </select>
                                    </div>
                                )}
                                {/* Toolbar */}
                                <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                                    <div className="flex items-center gap-3">
                                        <p className="text-slate-300 text-sm font-medium">{filteredNodes.length} concepts · {filteredEdges.length} relations</p>
                                        {/* Category filter */}
                                        <select value={catFilter} onChange={e => setCatFilter(e.target.value)}
                                            className="bg-slate-700 border border-slate-600 text-slate-200 text-xs rounded-lg px-2 py-1 focus:outline-none focus:border-cyan-500">
                                            <option value="all">All categories</option>
                                            {categories.map(c => <option key={c} value={c}>{c}</option>)}
                                        </select>
                                    </div>
                                    <div className="flex gap-4 text-xs text-slate-400">
                                        {Object.entries(REL_COLORS).map(([k, c]) => (
                                            <span key={k} className="flex items-center gap-1.5">
                                                <span className="w-4 h-1 rounded-full" style={{ background: c }} />
                                                {k.replace(/_/g, ' ')}
                                            </span>
                                        ))}
                                    </div>
                                </div>

                                {/* Category color legend */}
                                <div className="flex gap-3 mb-3 flex-wrap text-xs text-slate-400">
                                    <span className="text-slate-500">Nodes:</span>
                                    {Object.entries(CAT_COLORS).filter(([k]) => k !== 'default').map(([k, c]) => (
                                        <span key={k} className="flex items-center gap-1">
                                            <span className="w-2.5 h-2.5 rounded-full" style={{ background: c }} />
                                            {k}
                                        </span>
                                    ))}
                                </div>

                                {filteredNodes.length > 0 ? (
                                    <EduKGraph nodes={filteredNodes} edges={filteredEdges} onNodeClick={handleNodeClick} />
                                ) : (
                                    <div className="h-96 flex flex-col items-center justify-center text-slate-400">
                                        <span className="text-6xl mb-4">📊</span>
                                        <p className="text-lg font-medium">No concepts yet</p>
                                        <p className="text-sm mt-1">Upload a syllabus or paste text to build your Knowledge Graph</p>
                                    </div>
                                )}
                            </div>
                        )}

                        {/* ── Concepts Tab ── */}
                        {tab === 'concepts' && (() => {
                            const sorted = [...graph.nodes]
                                .filter(n => !conceptSearch || n.name.toLowerCase().includes(conceptSearch.toLowerCase()))
                                .sort((a, b) => {
                                    if (conceptSort === 'layer') return (a.layer ?? 2) - (b.layer ?? 2) || (b.weight ?? 0) - (a.weight ?? 0)
                                    if (conceptSort === 'weight') return (b.weight ?? 0) - (a.weight ?? 0)
                                    if (conceptSort === 'name') return a.name.localeCompare(b.name)
                                    if (conceptSort === 'difficulty') { const o = { hard: 0, medium: 1, easy: 2 }; return (o[a.difficulty] ?? 1) - (o[b.difficulty] ?? 1) }
                                    return 0
                                })
                            return (
                            <div>
                                {/* Search + Sort toolbar */}
                                <div className="flex items-center gap-3 mb-4 flex-wrap">
                                    <div className="relative flex-1 min-w-[200px]">
                                        <input type="text" value={conceptSearch} onChange={e => setConceptSearch(e.target.value)}
                                            placeholder="Search concepts..." className="w-full bg-slate-800/60 border border-slate-700/50 text-slate-200 text-sm rounded-lg px-4 py-2 pl-9 focus:outline-none focus:border-cyan-500 placeholder-slate-500" />
                                        <span className="absolute left-3 top-2.5 text-slate-500">🔍</span>
                                    </div>
                                    <select value={conceptSort} onChange={e => setConceptSort(e.target.value)}
                                        className="bg-slate-800/60 border border-slate-700/50 text-slate-200 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-cyan-500">
                                        <option value="layer">Sort by Layer</option>
                                        <option value="weight">Sort by Weight</option>
                                        <option value="name">Sort by Name</option>
                                        <option value="difficulty">Sort by Difficulty</option>
                                    </select>
                                    <span className="text-slate-400 text-sm">{sorted.length} concepts</span>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 max-h-[70vh] overflow-y-auto pr-1">
                                    {sorted.map(n => (
                                        <div key={n.id || n.name} onClick={() => { setSelected(n); fetchRootCause(n.name) }}
                                            className="bg-slate-800/60 backdrop-blur-sm rounded-xl border border-slate-700/50 p-5 cursor-pointer hover:border-cyan-500/40 hover:shadow-lg hover:shadow-cyan-500/10 transition group">
                                            <div className="flex justify-between items-start mb-2">
                                                <h3 className="text-white font-semibold group-hover:text-cyan-300 transition">{n.name}</h3>
                                                <MasteryBadge v={n.mastery} />
                                            </div>
                                            {n.description && <p className="text-slate-400 text-sm line-clamp-2 mb-3">{n.description}</p>}
                                            <div className="flex gap-2 flex-wrap">
                                                <span className="px-2 py-0.5 rounded text-xs font-medium" style={{ background: LAYER_COLORS[n.layer ?? 2] + '33', color: LAYER_COLORS[n.layer ?? 2], border: `1px solid ${LAYER_COLORS[n.layer ?? 2]}44` }}>L{n.layer ?? '?'} {LAYER_NAMES[n.layer ?? 2]}</span>
                                                <span className="px-2 py-0.5 rounded text-xs text-white" style={{ background: CAT_COLORS[n.category] || CAT_COLORS.default }}>{n.category || 'topic'}</span>
                                                <span className="px-2 py-0.5 rounded text-xs text-white" style={{ background: DIFF_COLORS[n.difficulty] || '#3b82f6' }}>{n.difficulty}</span>
                                                <span className="px-2 py-0.5 rounded text-xs bg-indigo-900/50 text-indigo-300">{n.bloom_level}</span>
                                                {n.weight > 0 && <span className="px-2 py-0.5 rounded text-xs bg-emerald-900/40 text-emerald-300 border border-emerald-700/40">w={n.weight.toFixed(3)}</span>}
                                            </div>
                                        </div>
                                    ))}
                                    {sorted.length === 0 && <p className="text-slate-400 col-span-full text-center py-12">{graph.nodes.length === 0 ? 'No concepts found. Build your Knowledge Graph first!' : 'No concepts match your search.'}</p>}
                                </div>
                            </div>
                            )
                        })()}

                        {/* ── Build Tab ── */}
                        {tab === 'build' && (
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                            {preprocessLog && (
                                <div className="lg:col-span-2 bg-slate-900/80 rounded-2xl border border-cyan-500/20 p-5 font-mono text-xs">
                                    <div className="flex items-center justify-between mb-3">
                                        <h4 className="text-cyan-400 font-bold text-sm">🔬 Preprocessing Pipeline Log</h4>
                                        <button onClick={() => setPreprocessLog(null)} className="text-slate-500 hover:text-white text-xs">✕ dismiss</button>
                                    </div>
                                    <div className="space-y-1 text-slate-300">
                                        <p className="text-slate-400">║ INPUT&nbsp;&nbsp;&nbsp;: <span className="text-white">{preprocessLog.input_chars} chars, {preprocessLog.input_lines} lines</span></p>
                                        {preprocessLog.stages?.map((s, i) => (
                                            <p key={i} className="text-slate-400">║ <span className="text-yellow-400">{s.label}</span> : <span className="text-white">{s.detail}</span></p>
                                        ))}
                                        <p className="text-slate-400">║ OUTPUT&nbsp;&nbsp;: <span className="text-emerald-400">{preprocessLog.output_chars} chars, {preprocessLog.output_lines} lines</span></p>
                                        <p className="text-slate-400">║ TOTAL&nbsp;&nbsp;&nbsp;: <span className="text-red-400">-{preprocessLog.total_removed} chars ({preprocessLog.reduction_pct}% reduction)</span></p>
                                    </div>
                                </div>
                            )}
                                <div className="bg-slate-800/60 backdrop-blur-sm rounded-2xl border border-slate-700/50 p-6">
                                    <h3 className="text-white font-bold text-lg mb-4 flex items-center gap-2">📄 Upload PDF / File</h3>
                                    <label className="block border-2 border-dashed border-slate-600 rounded-xl p-8 text-center cursor-pointer hover:border-cyan-500/50 transition">
                                        <input type="file" accept=".pdf,.txt,.docx" className="hidden" onChange={e => setUploadFile(e.target.files?.[0] || null)} />
                                        <span className="text-4xl block mb-2">📁</span>
                                        <span className="text-slate-300">{uploadFile ? uploadFile.name : 'Click to select file'}</span>
                                    </label>
                                    <button onClick={handleUpload} disabled={!uploadFile || uploading}
                                        className="mt-4 w-full py-3 bg-gradient-to-r from-cyan-500 to-blue-500 text-white rounded-xl font-semibold disabled:opacity-50 hover:shadow-lg hover:shadow-cyan-500/25 transition">
                                        {uploading ? 'Processing…' : '🚀 Build Knowledge Graph'}
                                    </button>
                                </div>
                                <div className="bg-slate-800/60 backdrop-blur-sm rounded-2xl border border-slate-700/50 p-6">
                                    <h3 className="text-white font-bold text-lg mb-4 flex items-center gap-2">✍️ Paste Text</h3>
                                    <textarea value={buildText} onChange={e => setBuildText(e.target.value)} rows={8}
                                        placeholder="Paste your syllabus, lecture notes, or any educational text here..."
                                        className="w-full bg-slate-900/50 border border-slate-600 rounded-xl p-4 text-slate-200 placeholder-slate-500 resize-none focus:border-cyan-500 focus:outline-none" />
                                    <button onClick={handleBuildText} disabled={!buildText.trim() || building}
                                        className="mt-4 w-full py-3 bg-gradient-to-r from-violet-500 to-purple-500 text-white rounded-xl font-semibold disabled:opacity-50 hover:shadow-lg hover:shadow-violet-500/25 transition">
                                        {building ? 'Extracting…' : '🧠 Extract Concepts'}
                                    </button>
                                </div>
                            </div>
                        )}

                        {/* ── Analysis Tab ── */}
                        {tab === 'analysis' && (
                            <div className="space-y-6">
                                <div className="bg-slate-800/60 backdrop-blur-sm rounded-2xl border border-slate-700/50 p-6">
                                    <h3 className="text-white font-bold text-lg mb-4">⚠️ Weak Concepts (below 50% mastery)</h3>
                                    {weaknesses.length > 0 ? (
                                        <div className="space-y-3">
                                            {weaknesses.map(w => (
                                                <div key={w.name} onClick={() => fetchRootCause(w.name)}
                                                    className="bg-slate-900/50 rounded-xl p-4 flex items-center justify-between cursor-pointer hover:border-orange-500/40 border border-transparent transition">
                                                    <div>
                                                        <p className="text-white font-medium">{w.name}</p>
                                                        <p className="text-slate-400 text-sm">{w.category} · {w.difficulty}</p>
                                                    </div>
                                                    <MasteryBadge v={w.mastery} />
                                                </div>
                                            ))}
                                        </div>
                                    ) : <p className="text-emerald-400">✅ No weak concepts! Great work!</p>}
                                </div>
                                {rootCause && rootCause.root_cause && (
                                    <div className="bg-gradient-to-r from-orange-500/10 to-red-500/10 rounded-2xl border border-orange-500/30 p-6">
                                        <h3 className="text-orange-300 font-bold text-lg mb-2">🔍 Root Cause Analysis</h3>
                                        <p className="text-slate-200">{rootCause.message}</p>
                                        {rootCause.prerequisite_chain?.length > 0 && (
                                            <div className="mt-3 flex flex-wrap gap-2">
                                                {rootCause.prerequisite_chain.map((p, i) => (
                                                    <span key={i} className="px-3 py-1 rounded-full text-sm bg-slate-800 text-slate-300 border border-slate-600">
                                                        {p} {i < rootCause.prerequisite_chain.length - 1 ? '→' : '🎯'}
                                                    </span>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        )}
                    </>
                )}

                {/* ── Selected Concept Detail Modal ── */}
                {selected && (
                    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-6" onClick={() => setSelected(null)}>
                        <div className="bg-slate-800 rounded-2xl border border-slate-600 p-8 max-w-lg w-full shadow-2xl" onClick={e => e.stopPropagation()}>
                            <div className="flex justify-between items-start mb-4">
                                <h2 className="text-2xl font-bold text-white">{selected.name}</h2>
                                <button onClick={() => setSelected(null)} className="text-slate-400 hover:text-white text-xl">✕</button>
                            </div>
                            {selected.description && <p className="text-slate-300 mb-4">{selected.description}</p>}
                            <div className="grid grid-cols-2 gap-3 mb-4">
                                <div className="bg-slate-700/50 rounded-lg p-3"><p className="text-slate-400 text-xs">Layer</p><p className="text-white font-medium">L{selected.layer ?? '?'} {LAYER_NAMES[selected.layer ?? 2]}</p></div>
                                <div className="bg-slate-700/50 rounded-lg p-3"><p className="text-slate-400 text-xs">Mastery</p><MasteryBadge v={selected.mastery} /></div>
                                <div className="bg-slate-700/50 rounded-lg p-3"><p className="text-slate-400 text-xs">Difficulty</p><p className="text-white font-medium">{selected.difficulty}</p></div>
                                <div className="bg-slate-700/50 rounded-lg p-3"><p className="text-slate-400 text-xs">Bloom Level</p><p className="text-white font-medium capitalize">{selected.bloom_level}</p></div>
                                <div className="bg-slate-700/50 rounded-lg p-3"><p className="text-slate-400 text-xs">Category</p><p className="text-white font-medium capitalize">{selected.category}</p></div>
                                <div className="bg-slate-700/50 rounded-lg p-3"><p className="text-slate-400 text-xs">SIF Weight</p><p className="text-white font-medium">{(selected.weight || 0).toFixed(4)}</p></div>
                            </div>
                            {rootCause?.message && (
                                <div className="bg-orange-500/10 border border-orange-500/30 rounded-lg p-4">
                                    <p className="text-orange-200 text-sm">{rootCause.message}</p>
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </main>
    )
}
