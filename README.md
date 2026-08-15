# blender-mcp

An MCP server that builds Blender `.blend` files. It reaches Blender two ways:

- **Headless** — every call starts a fresh `blender --background` process. Deterministic,
  always available, and the right choice for generating files.
- **Live** — a small Blender addon opens a local port so the server can drive the Blender
  window you already have open, and you watch it happen.

Both routes run the same handler code, so a script behaves identically either way. A local
web UI lets you upload reference images and run generation jobs with the same tools.

## Requirements

| | |
|---|---|
| Blender | 4.2 or newer (developed against 5.1) |
| Python | 3.12+ for the server (Blender brings its own) |
| [uv](https://docs.astral.sh/uv/) | dependency and venv management |

## Setup

```bash
uv sync                                        # create .venv and install
cp .env.example .env                           # then set BLENDER_MCP_EXECUTABLE
uv run python scripts/build_addon.py --install # build + install the Blender addon
```

If you skip `.env`, the server searches your `PATH` and the standard
`Program Files/Blender Foundation/Blender <version>` folders on every drive, preferring
the newest version it finds.

### Turning on the live bridge

The addon is installed but idle until you start it:

1. Open Blender.
2. Press <kbd>N</kbd> in the 3D viewport to show the sidebar.
3. Open the **MCP** tab and click **Start MCP Bridge**.

Tick **Start listening on launch** in the addon preferences to skip this every time.

### Connecting an MCP client

`.cursor/mcp.json` already registers the server for this project. To make it available
everywhere, copy that block into `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "blender": {
      "command": "uv",
      "args": ["run", "--directory", "C:\\Users\\josef\\Projects\\blender-mcp", "blender-mcp"]
    }
  }
}
```

## Quality workflow

Generation quality comes from looking, not from a single script dump:

1. `list_references` / `view_reference` — open guide images first
2. `create_blend` from `studio` or `product`
3. Build in small `run_script` steps; `apply_material` for metal/plastic/rubber/glass/wood
4. `preview_views` — multi-angle EEVEE previews; compare to refs with `view_image`
5. Fix, preview again
6. Final `render` / `render_and_view` (CYCLES only for finals; EEVEE while iterating)

## Local web UI

```bash
uv run blender-mcp-web
# open http://127.0.0.1:8765
```

Upload reference images, enter a prompt, and browse jobs under `output/jobs/`.

- **With** `BLENDER_MCP_LLM_API_KEY` in `.env` — the site runs a bounded multimodal agent
  that calls the same Blender tools (OpenAI-compatible or Anthropic via
  `BLENDER_MCP_LLM_PROVIDER`).
- **Without** a key — uploads and job pages still work; open the job in Cursor and ask the
  MCP agent to build from `output/jobs/<id>/refs`.

## Tools

| Tool | Purpose |
|---|---|
| `blender_status` | Install, output/refs dirs, templates, materials, live bridge |
| `list_references` / `view_reference` / `add_reference` | Guide image library under `output/refs` |
| `create_blend` | New file from a template + optional script |
| `run_script` | Arbitrary bpy Python |
| `apply_material` | Procedural presets: metal, plastic, rubber, glass, wood |
| `inspect_blend` | Scene graph / materials / cameras / lights |
| `preview_views` | Multi-angle EEVEE previews for critique |
| `render` / `render_and_view` | Still PNG; the latter returns the image to look at |
| `view_image` / `view_preview` | Load a PNG for vision |
| `viewport_screenshot` | Live viewport capture |
| `list_outputs` | Files under `output/` |
| `open_in_live_session` | Open a `.blend` in the live Blender window |

### Writing scripts

`run_script` and the `script` argument of `create_blend` execute in a namespace where
`bpy`, `mathutils`, `math`, `D` (`bpy.data`) and `C` (`bpy.context`) are already bound.
Send data back by assigning to `result` or calling `emit(value)`.

### Templates

| Name | What you get |
|---|---|
| `empty` | Nothing at all |
| `default` | Blender's startup scene: cube, camera, light |
| `studio` | Grey floor, three-point area lighting, 50mm camera, 1920×1080 |
| `product` | White seamless backdrop, soft lights, 85mm product framing |

## Layout

```
addon/blender_mcp_addon/   Blender extension + shared handlers (incl. preview_views)
src/blender_mcp/
  server.py                MCP tools
  refs.py                  reference image library
  materials.py             procedural material presets
  templates.py             starter scenes
  agent/                   bounded multimodal generation loop
  web/                     FastAPI UI (templates + static)
  headless.py / bridge.py  Blender process / live socket
scripts/                   build, install, verification
output/                    .blend files, renders, refs/, jobs/
```

## Testing

```bash
uv run pytest -m "not blender"   # fast
uv run pytest                    # includes real Blender runs
uv run python scripts/check_server.py
uv run python scripts/verify_live_bridge.py
```

## Notes and limits

- `run_script` executes arbitrary Python inside Blender. Keep the bridge on loopback.
- Long renders block the live UI until they finish.
- `viewport_screenshot` is live-only.
- Cycles uses CPU unless you enable a GPU device in Blender preferences.
- The web agent needs a multimodal model that supports tool calls and images.

## Licence

MIT
