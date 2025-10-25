"""
generate_diagrams.py

Programmatically generate module flowcharts for the TrackEneer report.
This version supports configurable output format (png/svg/pdf), DPI and larger layouts
so the produced images are suitable for embedding at large sizes in PDFs or Overleaf.

Dependencies:
  - python-graphviz (pip install graphviz)
  - Graphviz system binary (https://graphviz.org/download/)

Usage examples:
  # generate large PNGs (300 DPI) into ./flowcharts
  python generate_diagrams.py --format png --dpi 300

  # generate vector SVGs (scalable) into ./flowcharts
  python generate_diagrams.py --format svg

  # generate only scheduling diagram
  python generate_diagrams.py --modules scheduling --format png --dpi 300

"""
import os
import argparse
from graphviz import Digraph


def ensure_outdir(outdir):
    os.makedirs(outdir, exist_ok=True)
    return outdir


def render_dot(dot: Digraph, filename: str, outdir: str, out_format: str, dpi: int):
    path = os.path.join(outdir, filename)
    dot.format = out_format
    # Instruct Graphviz rasterizer about DPI (affects PNG output)
    if dpi:
        dot.graph_attr['dpi'] = str(dpi)
    # Try to make layout large (inches) so nodes and text scale up nicely
    # Keep aspect ratio when rendering
    dot.graph_attr.setdefault('size', '11,8.5')
    dot.graph_attr.setdefault('ratio', 'fill')
    dot.render(filename=path, cleanup=True)
    ext = out_format
    print(f"Wrote: {path}.{ext}")


def scheduling_flowchart():
    dot = Digraph('scheduling', comment='Scheduling Module Flowchart', graph_attr={'rankdir': 'LR'})
    dot.attr('node', shape='box', style='rounded,filled', color='lightblue', fontsize='16')
    dot.attr('edge', fontsize='12')

    dot.node('U', 'User Input\n(deadlines, availability)')
    dot.node('P', 'Parser\n(syllabus / tasks)')
    dot.node('G', 'Graph Store\n(Neo4j: topics, pre-reqs)')
    dot.node('S', 'Scheduler\n(heuristics + topo orders)')
    dot.node('N', 'Notification Service\n(WebSocket)')
    dot.node('UI', 'Frontend\n(Calendar / Tasks)')

    dot.edge('U', 'P', label='upload / add tasks')
    dot.edge('P', 'G', label='topic dependencies')
    dot.edge('G', 'S', label='query dependencies')
    dot.edge('U', 'S', label='constraints & prefs')
    dot.edge('S', 'UI', label='generated schedule')
    dot.edge('S', 'N', label='reminders / events')
    dot.edge('N', 'UI', label='live update')

    return dot


def study_flowchart():
    dot = Digraph('study', comment='Study Module Flowchart', graph_attr={'rankdir': 'LR'})
    dot.attr('node', shape='box', style='rounded,filled', color='lightgreen', fontsize='16')
    dot.attr('edge', fontsize='12')

    dot.node('U', 'User Notes / Uploads')
    dot.node('OCR', 'Preprocessor\n(OCR / parsing)')
    dot.node('EMB', 'Embeddings\n(all-mpnet-base-v2)')
    dot.node('VS', 'Vector Store\n(Chroma)')
    dot.node('SR', 'Semantic Search / QA')
    dot.node('UI', 'Frontend\n(Notes / Search)')

    dot.edge('U', 'OCR', label='upload')
    dot.edge('OCR', 'EMB', label='text -> embeddings')
    dot.edge('EMB', 'VS', label='index vectors')
    dot.edge('UI', 'SR', label='query')
    dot.edge('SR', 'VS', label='ANN search')
    dot.edge('SR', 'UI', label='results / snippets')

    return dot


def placement_flowchart():
    dot = Digraph('placement', comment='Placement Module Flowchart', graph_attr={'rankdir': 'LR'})
    dot.attr('node', shape='box', style='rounded,filled', color='lightyellow', fontsize='16')
    dot.attr('edge', fontsize='12')

    dot.node('U', 'User Profile\n(resume, skills)')
    dot.node('R', 'Resume Parser\n(NER / features)')
    dot.node('E', 'Embeddings\n(profiles & companies)')
    dot.node('KB', 'Company Knowledge\n(aggregated web data)')
    dot.node('LM', 'Large Model\n(Gemini / Cohere)')
    dot.node('UI', 'Frontend\n(Insights / Company Report)')

    dot.edge('U', 'R', label='upload resume')
    dot.edge('R', 'E', label='vectorize profile')
    dot.edge('KB', 'E', label='company vectors')
    dot.edge('E', 'LM', label='candidates + context')
    dot.edge('LM', 'UI', label='detailed research / prompts')

    return dot


def insights_flowchart():
    dot = Digraph('insights', comment='Insights Module Flowchart', graph_attr={'rankdir': 'LR'})
    dot.attr('node', shape='box', style='rounded,filled', color='lightcoral', fontsize='16')
    dot.attr('edge', fontsize='12')

    dot.node('D', 'Student Data\n(grades, logs)')
    dot.node('F', 'Feature Engine\n(aggregate signals)')
    dot.node('M', 'Modeling\n(Cohere/Gemini scoring)')
    dot.node('R', 'Recommender\n(roadmaps, topics)')
    dot.node('UI', 'Frontend\n(Recommendations)')

    dot.edge('D', 'F', label='ingest / aggregate')
    dot.edge('F', 'M', label='scoring')
    dot.edge('M', 'R', label='rank & recommend')
    dot.edge('R', 'UI', label='personalized plans')

    return dot


def architecture_flowchart():
    """Generate a system-level architecture diagram showing frontend, unified backend routers,
    notification service, databases, vector store, and AI model integrations."""
    dot = Digraph('architecture', comment='System Architecture', graph_attr={'rankdir': 'TB', 'splines': 'ortho'})
    dot.attr('node', shape='rect', style='rounded,filled', fontsize='16')

    # Layer clusters
    dot.node('FE', 'Frontend\n(Next.js 15, React 19)')
    dot.node('API', 'Unified FastAPI\nrouters on port 5000\n(Scheduler, Study, Placement, Insights)')
    dot.node('NOTIF', 'Notification Service\n(Express/TS)\nWeb Push / WebSockets on 3001')
    dot.node('AI', 'AI Layer\n(Gemini, Cohere)')
    dot.node('VS', 'Vector Store\n(Chroma/FAISS)')
    dot.node('DB', 'Databases\nMongoDB (notes), Neo4j (graph)')
    dot.node('CACHE', '24h JSON Cache (dev)')

    # Edges
    dot.edge('FE', 'API', label='REST / GraphQL / OAuth')
    dot.edge('API', 'DB', label='CRUD')
    dot.edge('API', 'VS', label='index / query vectors')
    dot.edge('API', 'AI', label='prompts / results')
    dot.edge('AI', 'CACHE', label='store generated content')
    dot.edge('API', 'NOTIF', label='schedule events / push')
    dot.edge('NOTIF', 'FE', label='live updates / push')

    # Optional auxiliary nodes
    dot.node('AUTH', 'OAuth (NextAuth.js)')
    dot.edge('FE', 'AUTH', label='signin')
    dot.edge('AUTH', 'API', label='tokens / sessions')

    return dot


def generate_all(outdir: str, out_format: str, dpi: int, modules_list=None):
    outdir = ensure_outdir(outdir)

    maps = [
        (scheduling_flowchart, 'trackeneer_scheduling_flowchart'),
        (study_flowchart, 'study_module_flowchart'),
        (placement_flowchart, 'placement_module_flowchart'),
        (insights_flowchart, 'insights_module_flowchart'),
        (architecture_flowchart, 'architecture_system_diagram'),
    ]

    for func, name in maps:
        if modules_list and name.split('_')[0] not in modules_list:
            continue
        dot = func()
        render_dot(dot, name, outdir, out_format, dpi)


def parse_args():
    p = argparse.ArgumentParser(description='Generate TrackEneer module flowcharts')
    p.add_argument('--outdir', default=os.path.join(os.path.dirname(__file__), 'flowcharts'), help='Output directory')
    p.add_argument('--modules', default='all', help='Comma-separated list: scheduling,study,placement,insights or all')
    p.add_argument('--format', default='png', choices=['png', 'svg', 'pdf'], help='Output image format')
    p.add_argument('--dpi', type=int, default=200, help='DPI for raster outputs (png)')
    return p.parse_args()


def main():
    args = parse_args()
    outdir = os.path.abspath(args.outdir)
    ensure_outdir(outdir)

    modules = None if args.modules == 'all' else [m.strip().lower() for m in args.modules.split(',')]

    generate_all(outdir, args.format, args.dpi, modules)

    print('\nAll requested diagrams generated.')


if __name__ == '__main__':
    main()
