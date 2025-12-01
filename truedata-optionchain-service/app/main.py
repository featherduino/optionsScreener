from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from app.routers.optionchain import router as optionchain_router
from app.routers.health import router as health_router

app = FastAPI(
    title="TrueData OptionChain + Greeks API",
    openapi_version="3.1.0",
)

app.include_router(optionchain_router)
app.include_router(health_router)

@app.get("/", response_class=HTMLResponse)
def index():
    return """
    <html>
    <head>
      <title>OptionChain API</title>
      <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; max-width: 800px; margin: 32px auto; line-height: 1.5; color: #0f172a; }
        code { background: #f1f5f9; padding: 2px 4px; border-radius: 4px; }
        pre { background: #0f172a; color: #e2e8f0; padding: 12px; border-radius: 8px; overflow-x: auto; }
        a { color: #2563eb; text-decoration: none; }
        a:hover { text-decoration: underline; }
      </style>
    </head>
    <body>
      <h1>OptionChain API</h1>
      <p>Base path: <code>/api</code></p>

      <h2>Endpoints</h2>
      <ul>
        <li><code>GET /api/optionchain/{symbol}</code> – nearest expiry option chain + charts</li>
        <li><code>GET /api/health</code> – liveness</li>
        <li><code>GET /api/health/auth</code> – token status (no token exposed)</li>
        <li><a href="/api/docs">Swagger UI</a> | <a href="/api/openapi.json">OpenAPI JSON</a></li>
      </ul>

      <h2>Sample</h2>
      <pre>curl -s "&lt;host&gt;/api/optionchain/RELIANCE" | jq '.'</pre>

      <p>Rendered docs: <a href="/api/docs">/api/docs</a></p>
    </body>
    </html>
    """
