# PolicyDesk RAG frontend

Use Node.js 20.19+, 22.13+, or 24+ and npm. From this folder, run:

```sh
npm install
npm run dev
```

Open `http://localhost:5173`. The frontend expects the FastAPI service at `http://127.0.0.1:8000`. To use another API origin, copy `.env.example` to `.env.local` and set `VITE_API_URL`. The API must allow the frontend origin through CORS. Configure JWT and the database on the API server.

Sign up or sign in, upload a document, then ask a question. Citation buttons open the matching passages. Each response also has an expandable list of all retrieved passages.

```sh
npm run lint
npm run build
```

The production build is written to `dist/`. A static host should serve `index.html` for client-side routes such as `/documents` and `/insights`.
