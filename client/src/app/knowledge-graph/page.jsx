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
   FORCE-DIRECTED GRAPH COMPONENT
   - Physics simulation with repulsion, attraction, centering
   - Drag nodes with mouse
   - Zoom with scroll wheel
   - Pan by dragging background
   - Smart labels: show on hover & nearby nodes
   - Click node to select
================================================================ */
function ForceGraph({ nodes: rawNodes, edges, onNodeClick }) {
    const canvasRef = useRef(null)
    const simRef = useRef(null)        // simulation state
    const rafRef = useRef(null)        // requestAnimationFrame id

    useEffect(() => {
        if (!canvasRef.current || rawNodes.length === 0) return

        const canvas = canvasRef.current
        const ctx = canvas.getContext('2d')
        const dpr = window.devicePixelRatio || 1

        // Resize canvas
        const resize = () => {
            const rect = canvas.parentElement.getBoundingClientRect()
            canvas.width = rect.width * dpr
            canvas.height = rect.height * dpr
            canvas.style.width = rect.width + 'px'
            canvas.style.height = rect.height + 'px'
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
        }
        resize()
        const W = () => canvas.width / dpr
        const H = () => canvas.height / dpr

        // Build adjacency for connected-ness scoring
        const adjacency = {}
        rawNodes.forEach(n => { adjacency[n.name] = new Set() })
        edges.forEach(e => {
            if (adjacency[e.source]) adjacency[e.source].add(e.target)
            if (adjacency[e.target]) adjacency[e.target].add(e.source)
        })

        // Initialize node positions: clustered by category
        const categories = [...new Set(rawNodes.map(n => n.category || 'default'))]
        const catAngles = {}
        categories.forEach((c, i) => { catAngles[c] = (2 * Math.PI * i) / categories.length })

        const nodes = rawNodes.map((n, i) => {
            const cat = n.category || 'default'
            const a = catAngles[cat] + (Math.random() - 0.5) * 0.8
            const spread = 120 + Math.random() * 180
            const conns = (adjacency[n.name]?.size || 0)
            return {
                ...n,
                x: W() / 2 + Math.cos(a) * spread,
                y: H() / 2 + Math.sin(a) * spread,
                vx: 0, vy: 0,
                radius: Math.max(6, Math.min(16, 6 + conns * 1.2)),
                connections: conns,
                pinned: false, // true while being dragged
            }
        })

        const nameIdx = {}
        nodes.forEach((n, i) => { nameIdx[n.name] = i })

        // Camera state
        const cam = { x: 0, y: 0, zoom: 1 }

        // Interaction state
        const mouse = { x: 0, y: 0, worldX: 0, worldY: 0, down: false, dragging: null, panning: false, panStartX: 0, panStartY: 0, camStartX: 0, camStartY: 0, hovered: null }

        // Coordinate transforms
        const screenToWorld = (sx, sy) => ({ x: (sx - cam.x) / cam.zoom, y: (sy - cam.y) / cam.zoom })
        const worldToScreen = (wx, wy) => ({ x: wx * cam.zoom + cam.x, y: wy * cam.zoom + cam.y })

        /* ── PHYSICS ── */
        const REPULSION = 4500
        const LINK_STRENGTH = 0.006
        const LINK_DISTANCE = 130
        const CENTERING = 0.002
        const DAMPING = 0.85
        const COOLING = 0.998
        let temperature = 1.0

        function tick() {
            const N = nodes.length
            // Repulsion (Barnes-Hut would be better for >500 nodes, but this is fine for <300)
            for (let i = 0; i < N; i++) {
                if (nodes[i].pinned) continue
                let fx = 0, fy = 0
                for (let j = 0; j < N; j++) {
                    if (i === j) continue
                    const dx = nodes[i].x - nodes[j].x
                    const dy = nodes[i].y - nodes[j].y
                    const dist2 = dx * dx + dy * dy + 1
                    const force = REPULSION / dist2 * temperature
                    fx += (dx / Math.sqrt(dist2)) * force
                    fy += (dy / Math.sqrt(dist2)) * force
                }
                nodes[i].vx += fx
                nodes[i].vy += fy
            }

            // Attraction along edges
            edges.forEach(e => {
                const si = nameIdx[e.source], ti = nameIdx[e.target]
                if (si === undefined || ti === undefined) return
                const s = nodes[si], t = nodes[ti]
                const dx = t.x - s.x, dy = t.y - s.y
                const dist = Math.sqrt(dx * dx + dy * dy) + 1
                const force = (dist - LINK_DISTANCE) * LINK_STRENGTH * temperature
                const fx = (dx / dist) * force, fy = (dy / dist) * force
                if (!s.pinned) { s.vx += fx; s.vy += fy }
                if (!t.pinned) { t.vx -= fx; t.vy -= fy }
            })

            // Center gravity
            const cx = W() / 2, cy = H() / 2
            for (let i = 0; i < N; i++) {
                if (nodes[i].pinned) continue
                nodes[i].vx += (cx - nodes[i].x) * CENTERING * temperature
                nodes[i].vy += (cy - nodes[i].y) * CENTERING * temperature
            }

            // Integrate
            for (let i = 0; i < N; i++) {
                if (nodes[i].pinned) continue
                nodes[i].vx *= DAMPING
                nodes[i].vy *= DAMPING
                nodes[i].x += nodes[i].vx
                nodes[i].y += nodes[i].vy
            }

            temperature = Math.max(0.02, temperature * COOLING)
        }

        /* ── DRAW ── */
        function draw() {
            const w = W(), h = H()
            ctx.clearRect(0, 0, w, h)

            ctx.save()
            ctx.translate(cam.x, cam.y)
            ctx.scale(cam.zoom, cam.zoom)

            // Draw edges
            edges.forEach(e => {
                const si = nameIdx[e.source], ti = nameIdx[e.target]
                if (si === undefined || ti === undefined) return
                const s = nodes[si], t = nodes[ti]

                const isHoveredEdge = mouse.hovered !== null && (si === mouse.hovered || ti === mouse.hovered)

                ctx.beginPath()
                ctx.moveTo(s.x, s.y)
                ctx.lineTo(t.x, t.y)
                ctx.strokeStyle = REL_COLORS[e.relation] || '#334155'
                ctx.lineWidth = isHoveredEdge ? 2.5 : 1
                ctx.globalAlpha = isHoveredEdge ? 0.9 : 0.2
                ctx.stroke()
                ctx.globalAlpha = 1

                // Arrow at midpoint
                if (isHoveredEdge || cam.zoom > 0.6) {
                    const mx = (s.x + t.x) / 2, my = (s.y + t.y) / 2
                    const angle = Math.atan2(t.y - s.y, t.x - s.x)
                    const sz = isHoveredEdge ? 6 : 4
                    ctx.beginPath()
                    ctx.moveTo(mx + sz * Math.cos(angle), my + sz * Math.sin(angle))
                    ctx.lineTo(mx - sz * Math.cos(angle - 0.5), my - sz * Math.sin(angle - 0.5))
                    ctx.lineTo(mx - sz * Math.cos(angle + 0.5), my - sz * Math.sin(angle + 0.5))
                    ctx.closePath()
                    ctx.fillStyle = REL_COLORS[e.relation] || '#334155'
                    ctx.globalAlpha = isHoveredEdge ? 0.9 : 0.35
                    ctx.fill()
                    ctx.globalAlpha = 1
                }
            })

            // Draw nodes
            nodes.forEach((n, i) => {
                const isHovered = mouse.hovered === i
                const isDragging = mouse.dragging === i
                const isConnected = mouse.hovered !== null && adjacency[n.name]?.has(nodes[mouse.hovered]?.name)
                const highlight = isHovered || isDragging || isConnected

                const r = n.radius * (isHovered ? 1.5 : isDragging ? 1.3 : 1)
                const baseColor = CAT_COLORS[n.category] || CAT_COLORS.default

                // Glow for highlighted
                if (highlight) {
                    ctx.beginPath()
                    ctx.arc(n.x, n.y, r + 6, 0, Math.PI * 2)
                    const glow = ctx.createRadialGradient(n.x, n.y, r, n.x, n.y, r + 6)
                    glow.addColorStop(0, baseColor + '60')
                    glow.addColorStop(1, 'transparent')
                    ctx.fillStyle = glow
                    ctx.fill()
                }

                // Node circle
                ctx.beginPath()
                ctx.arc(n.x, n.y, r, 0, Math.PI * 2)
                const grad = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, r)
                grad.addColorStop(0, baseColor)
                grad.addColorStop(1, baseColor + '88')
                ctx.fillStyle = grad
                ctx.fill()

                // Mastery ring
                if (n.mastery > 0) {
                    ctx.beginPath()
                    ctx.arc(n.x, n.y, r + 2, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * n.mastery)
                    ctx.strokeStyle = n.mastery >= 0.8 ? '#10b981' : n.mastery >= 0.5 ? '#f59e0b' : '#ef4444'
                    ctx.lineWidth = 2
                    ctx.stroke()
                }

                // Dim non-connected nodes when hovering
                if (mouse.hovered !== null && !highlight && mouse.hovered !== i) {
                    ctx.beginPath()
                    ctx.arc(n.x, n.y, r, 0, Math.PI * 2)
                    ctx.fillStyle = 'rgba(15,23,42,0.6)'
                    ctx.fill()
                }

                // Label logic: show if hovered, connected, or zoomed in enough
                const showLabel = isHovered || isConnected || isDragging || cam.zoom > 1.2 || (cam.zoom > 0.5 && n.connections >= 3)

                if (showLabel) {
                    const label = n.name.length > 22 ? n.name.slice(0, 20) + '…' : n.name
                    const fontSize = isHovered ? 13 : 11
                    ctx.font = `${isHovered ? '600' : '400'} ${fontSize}px Inter, system-ui, sans-serif`
                    ctx.textAlign = 'center'

                    // Background pill
                    const tw = ctx.measureText(label).width
                    const px = 5, py = 2
                    const lx = n.x, ly = n.y + r + 14
                    ctx.fillStyle = 'rgba(15,23,42,0.85)'
                    ctx.beginPath()
                    ctx.roundRect(lx - tw / 2 - px, ly - fontSize / 2 - py, tw + px * 2, fontSize + py * 2, 4)
                    ctx.fill()

                    ctx.fillStyle = isHovered ? '#e2e8f0' : '#94a3b8'
                    ctx.fillText(label, lx, ly + fontSize / 2 - 2)
                }
            })

            ctx.restore()

            // HUD: controls hint
            ctx.fillStyle = '#475569'
            ctx.font = '11px Inter, system-ui, sans-serif'
            ctx.textAlign = 'right'
            ctx.fillText(`Zoom: ${(cam.zoom * 100).toFixed(0)}%  •  Scroll to zoom  •  Drag nodes  •  Drag background to pan`, w - 12, h - 10)
        }

        /* ── ANIMATION LOOP ── */
        function animate() {
            tick()
            draw()
            rafRef.current = requestAnimationFrame(animate)
        }
        animate()

        /* ── MOUSE EVENTS ── */
        const getMousePos = (e) => {
            const rect = canvas.getBoundingClientRect()
            return { x: e.clientX - rect.left, y: e.clientY - rect.top }
        }

        const findNodeAt = (worldX, worldY) => {
            for (let i = nodes.length - 1; i >= 0; i--) {
                const dx = worldX - nodes[i].x, dy = worldY - nodes[i].y
                if (dx * dx + dy * dy < (nodes[i].radius + 4) ** 2) return i
            }
            return null
        }

        const onMouseDown = (e) => {
            const pos = getMousePos(e)
            const world = screenToWorld(pos.x, pos.y)
            const idx = findNodeAt(world.x, world.y)
            mouse.down = true

            if (idx !== null) {
                mouse.dragging = idx
                nodes[idx].pinned = true
                temperature = Math.max(temperature, 0.3) // reheat
                canvas.style.cursor = 'grabbing'
            } else {
                mouse.panning = true
                mouse.panStartX = pos.x
                mouse.panStartY = pos.y
                mouse.camStartX = cam.x
                mouse.camStartY = cam.y
                canvas.style.cursor = 'move'
            }
        }

        const onMouseMove = (e) => {
            const pos = getMousePos(e)
            mouse.x = pos.x
            mouse.y = pos.y
            const world = screenToWorld(pos.x, pos.y)
            mouse.worldX = world.x
            mouse.worldY = world.y

            if (mouse.dragging !== null) {
                nodes[mouse.dragging].x = world.x
                nodes[mouse.dragging].y = world.y
                nodes[mouse.dragging].vx = 0
                nodes[mouse.dragging].vy = 0
                temperature = Math.max(temperature, 0.15) // keep warm while dragging
            } else if (mouse.panning) {
                cam.x = mouse.camStartX + (pos.x - mouse.panStartX)
                cam.y = mouse.camStartY + (pos.y - mouse.panStartY)
            } else {
                // Hover detection
                const idx = findNodeAt(world.x, world.y)
                mouse.hovered = idx
                canvas.style.cursor = idx !== null ? 'pointer' : 'default'
            }
        }

        const onMouseUp = () => {
            if (mouse.dragging !== null) {
                nodes[mouse.dragging].pinned = false
            }
            mouse.dragging = null
            mouse.panning = false
            mouse.down = false
            canvas.style.cursor = 'default'
        }

        const onClick = (e) => {
            const pos = getMousePos(e)
            const world = screenToWorld(pos.x, pos.y)
            const idx = findNodeAt(world.x, world.y)
            if (idx !== null && onNodeClick) {
                onNodeClick(nodes[idx])
            }
        }

        const onWheel = (e) => {
            e.preventDefault()
            const pos = getMousePos(e)
            const zoomFactor = e.deltaY < 0 ? 1.12 : 0.89
            const newZoom = Math.max(0.15, Math.min(4, cam.zoom * zoomFactor))

            // Zoom towards mouse position
            cam.x = pos.x - (pos.x - cam.x) * (newZoom / cam.zoom)
            cam.y = pos.y - (pos.y - cam.y) * (newZoom / cam.zoom)
            cam.zoom = newZoom
        }

        const onResize = () => { resize() }

        canvas.addEventListener('mousedown', onMouseDown)
        canvas.addEventListener('mousemove', onMouseMove)
        canvas.addEventListener('mouseup', onMouseUp)
        canvas.addEventListener('mouseleave', onMouseUp)
        canvas.addEventListener('click', onClick)
        canvas.addEventListener('wheel', onWheel, { passive: false })
        window.addEventListener('resize', onResize)

        simRef.current = { nodes, cam }

        return () => {
            cancelAnimationFrame(rafRef.current)
            canvas.removeEventListener('mousedown', onMouseDown)
            canvas.removeEventListener('mousemove', onMouseMove)
            canvas.removeEventListener('mouseup', onMouseUp)
            canvas.removeEventListener('mouseleave', onMouseUp)
            canvas.removeEventListener('click', onClick)
            canvas.removeEventListener('wheel', onWheel)
            window.removeEventListener('resize', onResize)
        }
    }, [rawNodes, edges, onNodeClick])

    return (
        <div className="w-full h-[650px] relative">
            <canvas ref={canvasRef} className="w-full h-full rounded-xl bg-slate-900/80" />
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
        if (!email) { setLoading(false); return }
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
        try {
            const fd = new FormData()
            fd.append('file', uploadFile)
            fd.append('email', email)
            fd.append('strategy', 'llm')
            await fetch(`${API}/api/knowledge-graph/upload`, { method: 'POST', body: fd })

            // Poll until the document appears (background processing), then auto-select it
            const pollForDoc = (attempts = 0) => {
                if (attempts > 10) { // give up after ~30s
                    fetchGraph()
                    fetchDocuments()
                    return
                }
                setTimeout(async () => {
                    try {
                        const r = await fetch(`${API}/api/knowledge-graph/documents?email=${encodeURIComponent(email)}`)
                        const d = await r.json()
                        const docs = d.documents || []
                        setDocuments(docs)
                        const found = docs.find(doc => doc.document === fileName)
                        if (found) {
                            setSelectedDoc(fileName)
                            fetchGraph(fileName)
                            setTab('graph')
                        } else {
                            pollForDoc(attempts + 1) // not ready yet, try again
                        }
                    } catch (e) { pollForDoc(attempts + 1) }
                }, 3000)
            }
            pollForDoc()
        } catch (e) { console.error(e) }
        finally { setUploading(false); setUploadFile(null) }
    }

    const handleBuildText = async () => {
        if (!buildText.trim()) return
        setBuilding(true)
        try {
            const fd = new FormData()
            fd.append('text', buildText)
            fd.append('email', email)
            fd.append('strategy', 'llm')
            await fetch(`${API}/api/knowledge-graph/build`, { method: 'POST', body: fd })
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
                                    <ForceGraph nodes={filteredNodes} edges={filteredEdges} onNodeClick={handleNodeClick} />
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
                        {tab === 'concepts' && (
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                {graph.nodes.map(n => (
                                    <div key={n.id || n.name} onClick={() => { setSelected(n); fetchRootCause(n.name) }}
                                        className="bg-slate-800/60 backdrop-blur-sm rounded-xl border border-slate-700/50 p-5 cursor-pointer hover:border-cyan-500/40 hover:shadow-lg hover:shadow-cyan-500/10 transition group">
                                        <div className="flex justify-between items-start mb-2">
                                            <h3 className="text-white font-semibold group-hover:text-cyan-300 transition">{n.name}</h3>
                                            <MasteryBadge v={n.mastery} />
                                        </div>
                                        {n.description && <p className="text-slate-400 text-sm line-clamp-2 mb-3">{n.description}</p>}
                                        <div className="flex gap-2 flex-wrap">
                                            <span className="px-2 py-0.5 rounded text-xs text-white" style={{ background: CAT_COLORS[n.category] || CAT_COLORS.default }}>{n.category || 'topic'}</span>
                                            <span className="px-2 py-0.5 rounded text-xs text-white" style={{ background: DIFF_COLORS[n.difficulty] || '#3b82f6' }}>{n.difficulty}</span>
                                            <span className="px-2 py-0.5 rounded text-xs bg-indigo-900/50 text-indigo-300">{n.bloom_level}</span>
                                        </div>
                                    </div>
                                ))}
                                {graph.nodes.length === 0 && <p className="text-slate-400 col-span-full text-center py-12">No concepts found. Build your Knowledge Graph first!</p>}
                            </div>
                        )}

                        {/* ── Build Tab ── */}
                        {tab === 'build' && (
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
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
                                <div className="bg-slate-700/50 rounded-lg p-3"><p className="text-slate-400 text-xs">Mastery</p><MasteryBadge v={selected.mastery} /></div>
                                <div className="bg-slate-700/50 rounded-lg p-3"><p className="text-slate-400 text-xs">Difficulty</p><p className="text-white font-medium">{selected.difficulty}</p></div>
                                <div className="bg-slate-700/50 rounded-lg p-3"><p className="text-slate-400 text-xs">Bloom Level</p><p className="text-white font-medium capitalize">{selected.bloom_level}</p></div>
                                <div className="bg-slate-700/50 rounded-lg p-3"><p className="text-slate-400 text-xs">Category</p><p className="text-white font-medium capitalize">{selected.category}</p></div>
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
