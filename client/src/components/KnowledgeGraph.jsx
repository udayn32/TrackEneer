"use client";

import React, { useEffect, useRef, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:5000";

export default function KnowledgeGraph({ email }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [graph, setGraph] = useState({ nodes: [], edges: [] });
  const cyRef = useRef(null);

  useEffect(() => {
    const fetchGraph = async () => {
      setLoading(true);
      try {
        const res = await fetch(`${API_BASE}/api/notes/graph` + (email ? `?email=${encodeURIComponent(email)}` : ""));
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

  useEffect(() => {
    // Try to render with cytoscape if available
    if (!graph || !graph.nodes || graph.nodes.length === 0) return;

    let Cytoscape = null;
    try {
      Cytoscape = require("cytoscape");
    } catch (e) {
      Cytoscape = null;
    }

    if (!Cytoscape) return; // fallback to list rendering

    // create or reuse instance
    if (cyRef.current) {
      cyRef.current.destroy();
      cyRef.current = null;
    }

    const cy = Cytoscape({
      container: document.getElementById("ke-graph-container"),
      elements: [
        ...graph.nodes.map((n) => ({ data: { id: n.data.id, label: n.data.label } })),
        ...graph.edges.map((e, idx) => ({ data: { id: `e${idx}`, source: e.data.source, target: e.data.target, label: e.data.label } })),
      ],
      style: [
        { selector: "node", style: { "background-color": "#4fd1c5", label: "data(label)", color: "#fff", "text-valign": "center", "text-halign": "center", "font-size": 10 } },
        { selector: "edge", style: { width: 2, "line-color": "#63b3ed", "curve-style": "bezier", "target-arrow-shape": "triangle", "target-arrow-color": "#63b3ed" } },
      ],
      layout: { name: "cose" },
    });

    cyRef.current = cy;
    return () => {
      try {
        cy.destroy();
      } catch (e) {}
    };
  }, [graph]);

  if (loading) return <div className="p-6">Loading graph...</div>;
  if (error) return <div className="p-6 text-red-400">Error: {error}</div>;

  // Fallback simple rendering if cytoscape isn't installed
  if (!graph || !graph.nodes || graph.nodes.length === 0) {
    return <div className="p-6 text-slate-400">No graph data available.</div>;
  }

  let cytoscapeAvailable = true;
  try {
    require.resolve("cytoscape");
  } catch (e) {
    cytoscapeAvailable = false;
  }

  return (
    <div className="bg-slate-900/80 p-4 rounded-xl border border-cyan-500/10">
      <h3 className="text-lg font-semibold mb-3">Knowledge Graph</h3>
      {cytoscapeAvailable ? (
        <div id="ke-graph-container" style={{ width: "100%", height: 480 }} />
      ) : (
        <div>
          <p className="text-slate-400 mb-4">Cytoscape not installed — showing fallback list view.</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <h4 className="font-semibold mb-2">Topics / Nodes</h4>
              <ul className="list-disc list-inside text-sm text-slate-300">
                {graph.nodes.map((n) => (
                  <li key={n.data.id}>{n.data.label}</li>
                ))}
              </ul>
            </div>
            <div>
              <h4 className="font-semibold mb-2">Edges</h4>
              <ul className="list-disc list-inside text-sm text-slate-300">
                {graph.edges.map((e, idx) => (
                  <li key={idx}>{`${e.data.source} → ${e.data.target} (${e.data.label || "edge"})`}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
