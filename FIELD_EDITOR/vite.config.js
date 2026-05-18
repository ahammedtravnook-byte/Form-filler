import { defineConfig } from 'vite';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { mkdirSync, writeFileSync } from 'node:fs';

const __dirname = dirname(fileURLToPath(import.meta.url));

/**
 * Dev-only middleware that accepts POST /api/save-config and writes the
 * edited fields_config to  newtemplate/<template>/newfields.json
 * inside this Vite project (next to /public, /src).
 */
function saveConfigPlugin() {
  return {
    name: 'save-config-endpoint',
    configureServer(server) {
      server.middlewares.use('/api/save-config', (req, res) => {
        if (req.method !== 'POST') {
          res.statusCode = 405;
          res.end('Method Not Allowed');
          return;
        }
        let body = '';
        req.on('data', (chunk) => {
          body += chunk;
          if (body.length > 20 * 1024 * 1024) req.destroy();
        });
        req.on('end', () => {
          try {
            const { template, config } = JSON.parse(body);
            if (!template || !/^[A-Za-z0-9_-]+$/.test(template)) {
              throw new Error('Invalid template id');
            }
            if (!config || typeof config !== 'object') {
              throw new Error('Missing config');
            }
            const outDir = join(__dirname, 'newtemplate', template);
            mkdirSync(outDir, { recursive: true });
            const outPath = join(outDir, 'newfields.json');
            writeFileSync(outPath, JSON.stringify(config, null, 2), 'utf-8');
            res.statusCode = 200;
            res.setHeader('Content-Type', 'application/json');
            res.end(JSON.stringify({ ok: true, path: `newtemplate/${template}/newfields.json` }));
          } catch (err) {
            res.statusCode = 400;
            res.setHeader('Content-Type', 'application/json');
            res.end(JSON.stringify({ ok: false, error: String(err.message || err) }));
          }
        });
      });
    },
  };
}

export default defineConfig({
  plugins: [saveConfigPlugin()],
  server: { port: 5180 },
});
