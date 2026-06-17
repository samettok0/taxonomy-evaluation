# AI4RSE Prompt Browser

A local web tool for browsing, copying, and tracking progress through 10,542 taxonomy evaluation prompts.

## Prerequisites

- Python 3 (pre-installed on macOS)
- A modern web browser (Chrome, Firefox, Safari, Edge)
- `prompts.json` must exist in the parent directory (`taxonomy-evaluation/prompts.json`)

## How to Run

1. Open a terminal and navigate to the `prompt-browser` folder:

   ```bash
   cd /path/to/taxonomy-evaluation/prompt-browser
   ```

2. Start the server using the background automation script:

   ```bash
   ./start.sh
   ```
   *(Alternatively, run `python3 server.py` directly)*

3. Open your browser and go to:

   ```
   http://localhost:8080/prompt-browser/
   ```

4. Wait a few seconds for the 18 MB `prompts.json` to load.

## Usage

### Workflow

1. **Copy** the prompt → click `Copy Prompt` or press `C`
2. **Paste** it into your AI UI (ChatGPT, Gemini, Claude, etc.)
3. **Copy** the AI's response (in JSON format)
4. **Paste** it back into the "AI Response" textarea
5. The **Review Decision** panel will auto-fill based on the AI's response. You can review and adjust the Decision, Reason, Issues, and New Path.
6. Click **Save & Next** to save and move forward

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `←` / `→` | Navigate previous / next prompt |
| `C` | Copy current prompt to clipboard |
| `N` | Skip to next pending (unanswered) prompt |
| `Cmd+S` | Save current response |

### Sidebar

- Click a category group to expand its sub-categories
- Click any sub-category to jump to its first prompt
- Use **All / Pending / Done** tabs to filter categories
- Use the search box to find categories by name

### Data & Progress

- Progress is saved to a **local file** (`prompt-browser/progress.json`) — not browser cache
- A backup (`progress.backup.json`) is kept automatically on each save
- Use the **Export CSV** button (top-right) to generate an Excel-ready CSV mapping all your decisions (`AI4RSE_Taxonomy_Decisions.csv`)
- Use the **JSON Export** button (next to CSV) to download all raw JSON responses
- Use **⚙ Settings → Import Responses** to restore from a previously exported JSON file

## Stopping the Server

If you used `./start.sh` to start the server in the background, you can stop it easily by running:

```bash
./stop.sh
```

*(If you ran `python3 server.py` manually in your terminal, press `Ctrl+C` to stop it).*
