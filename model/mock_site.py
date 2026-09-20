"""Local mock of a public vectorizer site, used to exercise the full
scraper loop (semantic button detection -> wait-loop polling -> result
capture -> reward scoring) end to end.

Serves on :8100: a page with a file input + a "Convert image" button;
clicking convert waits 2.5s (like a real service) and then shows a large
inline SVG plus a download link.

Usage: PYTHONPATH=vendor:$PWD python -m model.mock_site
"""
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

PAGE = """<!doctype html>
<html><head><title>Mock Vectorizer</title></head>
<body>
<h1>Mock Vectorizer</h1>
<p>Upload an image to convert it to SVG.</p>
<input type="file" id="file" accept="image/*">
<button id="convertBtn" type="button">Convert image</button>
<div id="status"></div>
<div id="result" style="display:none">
  <h2>Result</h2>
  <svg id="out" width="420" height="420" viewBox="0 0 128 128" xmlns="http://www.w3.org/2000/svg">
    <path d="M10 64 L64 10 L118 64 L64 118 Z" fill="#2E60C8"/>
  </svg>
  <a id="dl" download="mock.svg" href="/result.svg">Download SVG</a>
</div>
<script>
document.getElementById('convertBtn').addEventListener('click', () => {
  const f = document.getElementById('file').files[0];
  document.getElementById('status').textContent = f ? 'Converting ' + f.name + '…' : 'Choose a file first';
  setTimeout(() => {
    document.getElementById('status').textContent = 'Done';
    document.getElementById('result').style.display = 'block';
  }, 2500);
});
</script>
</body></html>
"""


@app.get("/")
def index():
    return HTMLResponse(PAGE)


@app.get("/result.svg")
def result_svg():
    return """<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">
<path d="M10 64 L64 10 L118 64 L64 118 Z" fill="#2E60C8"/>
</svg>
"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8100)
