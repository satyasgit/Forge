# Pipeline UI

Visual pipeline builder for AI Agent Org using React + React Flow.

## Features

- Drag-and-drop pipeline construction with React Flow
- Load YAML templates from backend API
- Customize agent configurations (model, task prompts)
- Real-time validation & cost estimation
- Preview DAG before execution
- Run pipelines async and get job ID
- Agent palette with all 10 specialist agents

## Getting Started

### Prerequisites

- Node.js 18+
- Backend API running on port 8000

### Install Dependencies

```bash
cd pipeline-ui
npm install
```

### Configure

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Edit `.env` if your backend API is on a different URL.

### Start Development Server

```bash
npm run dev
```

Open http://localhost:3000 in your browser.

## Usage

1. **Select a Template**
   - Use the dropdown to load a pre-built template (api_only, mvp, etc.)
   - The template loads into the canvas as nodes

2. **Customize**
   - Click agents in the palette to add them to the pipeline
   - Drag nodes to rearrange
   - Connect nodes by dragging from output to input handles
   - Click a node to configure: model, task prompt, enable/disable

3. **Validate**
   - Click "Validate" to check for missing dependencies, circular deps, etc.
   - Warnings shown inline

4. **Preview**
   - Click "Preview" to see estimated cost, duration, and DAG structure
   - Cost based on typical token usage per agent
   - Duration based on critical path

5. **Run**
   - Enter a project ID
   - Click "Run Pipeline"
   - Job ID returned immediately, execution happens asynchronously
   - Check backend logs for progress

## Project Structure

```
pipeline-ui/
├── src/
│   ├── components/
│   │   ├── AgentNode.tsx     # Custom React Flow node
│   │   ├── ConfigPanel.tsx   # Node configuration sidebar
│   │   ├── PipelineCanvas.tsx # React Flow canvas
│   │   ├── Sidebar.tsx       # Template selector, agent palette
│   │   └── Toolbar.tsx       # Validate/Preview/Run buttons
│   ├── hooks/
│   │   └── usePipelineStore.ts # Zustand state management
│   ├── api.ts                # API client (axios)
│   ├── types.ts              # TypeScript interfaces
│   ├── styles/
│   │   └── index.css         # Global styles
│   ├── App.tsx               # Main app component
│   ├── main.tsx              # Entry point
│   └── vite-env.d.ts         # Vite type declarations
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
└── .env.example
```

## Tech Stack

- **React 18** - UI framework
- **TypeScript** - Type safety
- **React Flow** - Node-based graph editor
- **Zustand** - Lightweight state management
- **Axios** - HTTP client
- **Vite** - Fast build tool

## API Integration

The UI connects to the Python FastAPI backend:

| Endpoint | Purpose |
|----------|---------|
| `GET /api/pipelines/templates` | List all templates |
| `GET /api/pipelines/templates/{name}` | Load template config |
| `POST /api/pipelines/validate` | Validate custom config |
| `POST /api/pipelines/preview` | Get cost/duration/DAG preview |
| `POST /api/pipelines/run` | Start pipeline execution |

All endpoints documented at http://localhost:8000/docs when backend is running.

## State Management

Zustand store (`usePipelineStore`) manages:

- Templates & selected template
- Custom pipeline config
- Graph state (nodes, edges)
- Selected node
- Validation/preview results
- Loading & error states

Store persists to React component tree and syncs with API.

## Development Tips

### Add a new agent to palette

Edit `Sidebar.tsx` → `ALL_AGENTS` array.

### Custom node styling

Edit `AgentNode.tsx`. React Flow provides full customization.

### Add new API endpoints

Update `src/api.ts` and add to Toolbar/Sidebar as needed.

### Proxy configuration

`vite.config.ts` proxies `/api` to `http://localhost:8000`. Change target if backend runs elsewhere.

## Build for Production

```bash
npm run build
```

Output in `dist/` directory. Serve with any static file server.

## Future Enhancements

- Real-time job status via WebSocket
- Pipeline run history
- Save/load custom templates
- Undo/redo support
- Export/import YAML
- Agent dependency auto-completion
- Cost optimization suggestions
- Collaborative editing

## License

Same as parent repo.
