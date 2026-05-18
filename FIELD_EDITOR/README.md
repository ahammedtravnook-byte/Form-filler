# PDF Field Coordinate Editor

A small Vite app for visually verifying and correcting the `x,y` coordinates
in each template's `fields_config.json`.

## What it does

1. Pick a template from the dropdown (loaded from `public/templates/manifest.json`).
2. The real `template.pdf` renders full-size via **pdf.js**.
3. Every field is drawn as an overlay marker at its config `x,y`:
   - Text-like fields show the value from `example_data.json` (or `«field_name»`
     if no example value exists).
   - Checkboxes / checkbox-group options show a small box at each `x,y`.
4. Edit `x,y` in the right-hand panel (number inputs + `−/+` nudge buttons).
   Overlays re-position live so you can see exactly where stamping lands.
5. Click **Save newfields.json** — the edited config is written to
   `newtemplate/<template>/newfields.json` inside this project.

You then copy each `newfields.json` into your Python backend as the corrected
`fields_config.json`.

## Coordinate model

`x,y` are PDF points, origin **top-left**, `y` grows downward — the same system
PyMuPDF's `insert_text` / `insert_textbox` use in the Python engine. So an
overlay's screen position is just `left = x * zoom`, `top = y * zoom`.
The preview is a close visual approximation; font metrics differ slightly from
PyMuPDF, but the coordinate math is exact.

## Run

```bash
npm install
npm run dev      # http://localhost:5180
```

The dev server also exposes `POST /api/save-config` (see `vite.config.js`),
which is what the Save button calls. This only works under `npm run dev`.

## Layout

```
FIELD_EDITOR/
  index.html
  vite.config.js          # Vite config + /api/save-config middleware
  src/
    main.js               # app logic
    style.css
  public/templates/       # copy of the templates folder
    manifest.json         # list of template ids the dropdown reads
    <template>/template.pdf, fields_config.json, example_data.json
  newtemplate/            # OUTPUT — edited configs land here
    <template>/newfields.json
```

## Adding a template

Drop the template folder into `public/templates/` and add its id to
`public/templates/manifest.json`.
