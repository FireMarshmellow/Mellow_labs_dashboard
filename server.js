const http = require('http');
const fs = require('fs');
const path = require('path');
const Database = require('better-sqlite3');

const PORT = process.env.PORT ? Number(process.env.PORT) : 3000;
const APP_VERSION = process.env.APP_VERSION || 'dev';
const ROOT = __dirname;
const DB_PATH = path.join(ROOT, 'finance.db');

function createDatabase() {
  const db = new Database(DB_PATH);
  db.pragma('journal_mode = WAL');
  db.exec(`
    CREATE TABLE IF NOT EXISTS incomes (
      id TEXT PRIMARY KEY,
      date TEXT NOT NULL,
      source TEXT,
      processor TEXT,
      amount REAL DEFAULT 0,
      fees REAL DEFAULT 0,
      notes TEXT,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS expenses (
      id TEXT PRIMARY KEY,
      date TEXT NOT NULL,
      category TEXT,
      seller TEXT,
      items TEXT,
      order_number TEXT,
      total REAL DEFAULT 0,
      notes TEXT,
      source TEXT,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS payroll (
      id TEXT PRIMARY KEY,
      date TEXT NOT NULL,
      employee TEXT NOT NULL,
      amount REAL DEFAULT 0,
      notes TEXT,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
  `);
  return db;
}

const db = createDatabase();

function tableCount(resource){
  const row = db.prepare(`SELECT COUNT(*) as count FROM ${resource.table}`).get();
  return Number(row?.count || 0);
}

function seedFromJsonIfEmpty(){
  try {
    const file = path.join(ROOT, 'db.json');
    if (!fs.existsSync(file)) return;
    const raw = fs.readFileSync(file, 'utf8');
    const data = JSON.parse(raw || '{}');
    const kinds = ['income','expenses','payroll'];
    for (const kind of kinds) {
      const resource = resources[kind];
      if (!resource) continue;
      const count = tableCount(resource);
      const arr = Array.isArray(data[kind]) ? data[kind] : [];
      if (count === 0 && arr.length) {
        for (const rec of arr) {
          try { upsert(kind, rec); } catch {}
        }
        console.log(`[seed] Seeded ${arr.length} ${kind} records from db.json`);
      }
    }
  } catch (e) {
    console.warn('[seed] Failed to seed from db.json', e?.message || e);
  }
}

function generateId() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

function sanitizeCSV(value) {
  if (value === null || value === undefined) return '';
  const str = String(value);
  return /[",\n]/.test(str) ? '"' + str.replace(/"/g, '""') + '"' : str;
}

function buildResource(config) {
  const {
    table,
    toRow,
    map,
    csvHeader,
    csvRow
  } = config;

  return {
    table,
    toRow,
    map,
    csvHeader,
    csvRow,
    insert: db.prepare(`INSERT INTO ${table} (${config.columns.join(',')}) VALUES (${config.columns.map(c => '@' + c).join(',')})
      ON CONFLICT(id) DO UPDATE SET ${config.updatable.join(', ')} , updated_at=CURRENT_TIMESTAMP`),
    selectAll: db.prepare(`SELECT ${config.columns.join(',')}, created_at, updated_at FROM ${table} ORDER BY date DESC, updated_at DESC`),
    selectOne: db.prepare(`SELECT ${config.columns.join(',')}, created_at, updated_at FROM ${table} WHERE id = ?`),
    deleteOne: db.prepare(`DELETE FROM ${table} WHERE id = ?`),
    deleteAll: db.prepare(`DELETE FROM ${table}`)
  };
}

const resources = {
  income: buildResource({
    table: 'incomes',
    columns: ['id', 'date', 'source', 'processor', 'amount', 'fees', 'notes'],
    updatable: [
      'date = excluded.date',
      'source = excluded.source',
      'processor = excluded.processor',
      'amount = excluded.amount',
      'fees = excluded.fees',
      'notes = excluded.notes'
    ],
    toRow(data) {
      return {
        id: String(data.id || generateId()),
        date: data.date || '',
        source: data.source || '',
        processor: data.processor || '',
        amount: Number(data.amount || 0),
        fees: Number(data.fees || 0),
        notes: data.notes || ''
      };
    },
    map(row) {
      return {
        id: row.id,
        date: row.date,
        source: row.source || '',
        processor: row.processor || '',
        amount: Number(row.amount || 0),
        fees: Number(row.fees || 0),
        notes: row.notes || ''
      };
    },
    csvHeader: ['Date', 'Source', 'Processor', 'AmountGBP', 'FeesGBP', 'Notes'],
    csvRow(rec) {
      return [
        rec.date || '',
        rec.source || '',
        rec.processor || '',
        (Number(rec.amount || 0)).toFixed(2),
        (Number(rec.fees || 0)).toFixed(2),
        rec.notes || ''
      ];
    }
  }),

  expenses: buildResource({
    table: 'expenses',
    columns: ['id', 'date', 'category', 'seller', 'items', 'order_number', 'total', 'notes', 'source'],
    updatable: [
      'date = excluded.date',
      'category = excluded.category',
      'seller = excluded.seller',
      'items = excluded.items',
      'order_number = excluded.order_number',
      'total = excluded.total',
      'notes = excluded.notes',
      'source = excluded.source'
    ],
    toRow(data) {
      return {
        id: String(data.id || generateId()),
        date: data.date || '',
        category: data.category || '',
        seller: data.seller || '',
        items: data.items || '',
        order_number: data.orderNumber || data.order_number || '',
        total: Number(data.total || 0),
        notes: data.notes || '',
        source: data.source || ''
      };
    },
    map(row) {
      return {
        id: row.id,
        date: row.date,
        category: row.category || '',
        seller: row.seller || '',
        items: row.items || '',
        orderNumber: row.order_number || '',
        total: Number(row.total || 0),
        notes: row.notes || '',
        source: row.source || ''
      };
    },
    csvHeader: ['Date', 'Category', 'Seller', 'Item(s)', 'Order #', 'TotalGBP', 'Notes', 'Source'],
    csvRow(rec) {
      return [
        rec.date || '',
        rec.category || '',
        rec.seller || '',
        rec.items || '',
        rec.orderNumber || '',
        (Number(rec.total || 0)).toFixed(2),
        rec.notes || '',
        rec.source || ''
      ];
    }
  }),

  payroll: buildResource({
    table: 'payroll',
    columns: ['id', 'date', 'employee', 'amount', 'notes'],
    updatable: [
      'date = excluded.date',
      'employee = excluded.employee',
      'amount = excluded.amount',
      'notes = excluded.notes'
    ],
    toRow(data) {
      return {
        id: String(data.id || generateId()),
        date: data.date || '',
        employee: data.employee || '',
        amount: Number(data.amount || 0),
        notes: data.notes || ''
      };
    },
    map(row) {
      return {
        id: row.id,
        date: row.date,
        employee: row.employee || '',
        amount: Number(row.amount || 0),
        notes: row.notes || ''
      };
    },
    csvHeader: ['Date', 'Employee', 'AmountGBP', 'Notes'],
    csvRow(rec) {
      return [
        rec.date || '',
        rec.employee || '',
        (Number(rec.amount || 0)).toFixed(2),
        rec.notes || ''
      ];
    }
  })
};

function sendJson(res, status, data) {
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type'
  });
  res.end(JSON.stringify(data));
}

function sendCsv(res, filename, text) {
  res.writeHead(200, {
    'Content-Type': 'text/csv; charset=utf-8',
    'Content-Disposition': `attachment; filename="${filename}"`,
    'Access-Control-Allow-Origin': '*'
  });
  res.end(text);
}

function sendError(res, status, message) {
  sendJson(res, status, { error: message });
}

function notFound(res) {
  sendError(res, 404, 'Not found');
}

function readBody(req) {
  return new Promise(resolve => {
    let data = '';
    req.on('data', chunk => { data += chunk; });
    req.on('end', () => resolve(data));
  });
}

function upsert(kind, payload) {
  const resource = resources[kind];
  if (!resource) throw new Error('Unknown resource');
  const row = resource.toRow(payload || {});
  resource.insert.run(row);
  const stored = resource.selectOne.get(row.id);
  return resource.map(stored);
}

function list(kind) {
  const resource = resources[kind];
  return resource.selectAll.all().map(resource.map);
}

function remove(kind, id) {
  const resource = resources[kind];
  return resource.deleteOne.run(id).changes > 0;
}

function clear(kind) {
  const resource = resources[kind];
  resource.deleteAll.run();
}

function buildCsv(kind) {
  const resource = resources[kind];
  const rows = list(kind);
  const lines = [resource.csvHeader.join(',')];
  for (const rec of rows) {
    lines.push(resource.csvRow(rec).map(sanitizeCSV).join(','));
  }
  return lines.join('\n');
}

function serveStatic(req, res, pathname) {
  const safePath = decodeURIComponent(pathname);
  let filePath = safePath === '/' ? path.join(ROOT, 'financial_summary.html') : path.join(ROOT, safePath);
  filePath = path.normalize(filePath);
  if (!filePath.startsWith(ROOT)) return notFound(res);
  fs.stat(filePath, (err, stats) => {
    if (err || !stats.isFile()) return notFound(res);
    const ext = path.extname(filePath).toLowerCase();
    const mime = ({
      '.html': 'text/html; charset=utf-8',
      '.js': 'text/javascript; charset=utf-8',
      '.css': 'text/css; charset=utf-8',
      '.json': 'application/json; charset=utf-8',
      '.svg': 'image/svg+xml',
      '.ico': 'image/x-icon'
    })[ext] || 'text/plain; charset=utf-8';
    fs.readFile(filePath, (readErr, buf) => {
      if (readErr) return notFound(res);
      res.writeHead(200, { 'Content-Type': mime });
      res.end(buf);
    });
  });
}

// On startup, seed DB tables from db.json if they're empty
seedFromJsonIfEmpty();

const server = http.createServer(async (req, res) => {
  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type'
    });
    return res.end();
  }

  const url = new URL(req.url, `http://${req.headers.host}`);
  const pathname = url.pathname;

  try {
    if (pathname === '/api/ping') {
      const counts = Object.fromEntries(Object.entries(resources).map(([key, resource]) => {
        const { count } = db.prepare(`SELECT COUNT(*) as count FROM ${resource.table}`).get();
        return [key, count];
      }));
      return sendJson(res, 200, { ok: true, counts });
    }

    if (pathname === '/api/version') {
      return sendJson(res, 200, { version: APP_VERSION });
    }

    const csvMatch = pathname.match(/^\/api\/(income|expenses|payroll)\.csv$/);
    if (csvMatch) {
      const kind = csvMatch[1];
      const csv = buildCsv(kind);
      const filename = `${kind}-${new Date().toISOString().slice(0, 10)}.csv`;
      return sendCsv(res, filename, csv);
    }

    const apiMatch = pathname.match(/^\/api\/(income|expenses|payroll)(?:\/([^\/]+))?$/);
    if (apiMatch) {
      const kind = apiMatch[1];
      const id = apiMatch[2] ? decodeURIComponent(apiMatch[2]) : null;

      if (req.method === 'GET' && !id) {
        return sendJson(res, 200, list(kind));
      }

      if (req.method === 'GET' && id) {
        const resource = resources[kind];
        const row = resource.selectOne.get(id);
        if (!row) return notFound(res);
        return sendJson(res, 200, resource.map(row));
      }

      if (req.method === 'DELETE' && !id) {
        clear(kind);
        return sendJson(res, 200, { cleared: true });
      }

      if (req.method === 'DELETE' && id) {
        const deleted = remove(kind, id);
        return sendJson(res, deleted ? 200 : 404, deleted ? { deleted: true } : { error: 'Not found' });
      }

      if (req.method === 'POST') {
        const body = await readBody(req);
        let payload;
        try { payload = JSON.parse(body || '{}'); }
        catch { return sendError(res, 400, 'Invalid JSON'); }
        const stored = upsert(kind, payload);
        return sendJson(res, 200, stored);
      }

      if (req.method === 'PUT' && id) {
        const body = await readBody(req);
        let payload;
        try { payload = JSON.parse(body || '{}'); }
        catch { return sendError(res, 400, 'Invalid JSON'); }
        payload.id = id;
        const stored = upsert(kind, payload);
        return sendJson(res, 200, stored);
      }

      return sendError(res, 405, 'Method not allowed');
    }

    return serveStatic(req, res, pathname);
  } catch (err) {
    console.error('[server]', err);
    return sendError(res, 500, 'Internal server error');
  }
});

server.listen(PORT, () => {
  console.log(`Server running on http://localhost:${PORT}`);
});
