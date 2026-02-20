"use client";

import React, { useEffect, useRef, useState, useCallback } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:5000";

export default function KnowledgeGraph({ email }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [graph, setGraph] = useState({ nodes: [], edges: [] });
  const [cytoscapeReady, setCytoscapeReady] = useState(false);
  const cyRef = useRef(null);
  const cytoscapeLib = useRef(null);
  const containerRef = useRef(null);

  // ── Fetch graph data ──
  useEffect(() => {
    const fetchGraph = async () => {
      setLoading(true);
      try {
        const res = await fetch(
          `${API_BASE}/api/notes/graph` +
            (email ? `?email=${encodeURIComponent(email)}` : "")
        );
        const data = await res.json();
        setGraph(data);
      } catch (err) {
        console.error("Failed to fetch notes graph:", err);
        setError(err?.message || String(err));
      } finally {
        setLoading(false);
      }
    };
    fetchGraph();
  }, [email]);

  // ── Dynamically import cytoscape (browser only) ──
  useEffect(() => {
    let cancelled = false;
    import("cytoscape")
      .then((mod) => {
        if (!cancelled) {
          cytoscapeLib.current = mod.default || mod;
          setCytoscapeReady(true);
        }
      })
      .catch((err) => {
        console.warn("Cytoscape could not be loaded:", err);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // ── Render graph when data + library are ready ──
  useEffect(() => {
    if (!cytoscapeReady || !graph?.nodes?.length || !containerRef.current) return;

    const Cytoscape = cytoscapeLib.current;
    if (!Cytoscape) return;

    // destroy previous instance
    if (cyRef.current) {
      try {
        cyRef.current.destroy();
      } catch (_) {}
      cyRef.current = null;
    }

    const cy = Cytoscape({
      container: containerRef.current,
      elements: [
        ...graph.nodes.map((n) => ({
          data: { id: n.data?.id || n.id, label: n.data?.label || n.label || n.data?.id || n.id },
        })),
        ...graph.edges.map((e, idx) => ({
          data: {
            id: `e${idx}`,
            source: e.data?.source || e.source,
            target: e.data?.target || e.target,
            label: e.data?.label || e.label || "",
          },
        })),
      ],
      style: [
        {
          selector: "node",
          style: {
            "background-color": "#4fd1c5",
            label: "data(label)",
            color: "#fff",
            "text-valign": "center",
            "text-halign": "center",
            "font-size": 10,
          },
        },
        {
          selector: "edge",
          style: {
            width: 2,
            "line-color": "#63b3ed",
            "curve-style": "bezier",
            "target-arrow-shape": "triangle",
            "target-arrow-color": "#63b3ed",
          },
        },
      ],
      layout: { name: "cose", animate: true },
    });

    cyRef.current = cy;

    return () => {
      try {
        cy.destroy();
      } catch (_) {}
    };
  }, [graph, cytoscapeReady]);

  // ── Render ──
  if (loading) return <div className="p-6">Loading graph...</div>;
  if (error) return <div className="p-6 text-red-400">Error: {error}</div>;

  if (!graph?.nodes?.length) {
    return <div className="p-6 text-slate-400">No graph data available.</div>;
  }

  return (
    <div className="bg-slate-900/80 p-4 rounded-xl border border-cyan-500/10">
      <h3 className="text-lg font-semibold mb-3">Knowledge Graph</h3>

      {/* Cytoscape container — always rendered so ref is available */}
      <div
        ref={containerRef}
        style={{
          width: "100%",
          height: 480,
          display: cytoscapeReady ? "block" : "none",
        }}
      />

      {/* Fallback list view while cytoscape loads or if it fails */}
      {!cytoscapeReady && (
        <div>
          <p className="text-slate-400 mb-4 text-sm">
            Loading interactive graph…
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <h4 className="font-semibold mb-2">Topics / Nodes</h4>
              <ul className="list-disc list-inside text-sm text-slate-300">
                {graph.nodes.map((n) => (
                  <li key={n.data?.id || n.id}>
                    {n.data?.label || n.label || n.data?.id || n.id}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h4 className="font-semibold mb-2">Edges</h4>
              <ul className="list-disc list-inside text-sm text-slate-300">
                {graph.edges.map((e, idx) => (
                  <li key={idx}>
                    {`${e.data?.source || e.source} → ${e.data?.target || e.target} (${e.data?.label || e.label || "edge"})`}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
