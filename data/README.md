# data/

CSV files in this folder are fetched automatically by the app on every page load.
Filenames must match exactly (case-sensitive).

## Required files

| Filename | Contents |
|----------|----------|
| `roster.csv` | Ottoneu roster export (all 12 teams) |
| `proj_hitting.csv` | BatX hitting projections (current year) |
| `proj_pitching.csv` | BatX pitching projections (current year) |

## Optional files (dynasty mode)

| Filename | Contents |
|----------|----------|
| `proj_hitting_y1.csv` | BatX hitting projections (Y+1) |
| `proj_pitching_y1.csv` | BatX pitching projections (Y+1) |
| `proj_hitting_y2.csv` | BatX hitting projections (Y+2) |
| `proj_pitching_y2.csv` | BatX pitching projections (Y+2) |

## Updating data

1. Go to `github.com/[your-username]/OttoneuAI/tree/main/data`
2. Click the file you want to replace
3. Click the pencil icon → "Upload file" (or drag the new file)
4. Commit to `main`

GitHub Pages propagates changes in ~1 minute. The next page load picks up the new data automatically.

## Testing locally

The app skips auto-loading when run via `file://` protocol, so local testing
always uses whatever is in localStorage. Use the upload UI on the Data Hub to
load files locally without committing them.
