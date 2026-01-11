# Akcion Frontend - React + TypeScript + Tailwind

Modern React frontend for the Akcion Investment Analysis Platform, featuring a premium dark fintech UI inspired by Bloomberg Terminal.

## Tech Stack

- **Framework**: React 18 with TypeScript
- **Build Tool**: Vite 7 (rolldown-vite)
- **Styling**: Tailwind CSS 3
- **HTTP Client**: Axios
- **State Management**: React Context API

## Quick Start

### 1. Install Dependencies

```bash
cd frontend
npm install
```

### 2. Configure Environment

Copy `.env.example` to `.env`:

```bash
copy .env.example .env
```

### 3. Start Development Server

```bash
npm run dev
```

The app will be available at **http://localhost:5173**

## Features

- Premium Dark Fintech UI (Bloomberg Terminal style)
- Analysis input (text, YouTube, Google Docs)
- Portfolio grid view with filtering
- Stock cards with Gomes/Conviction scoring
- Full stock detail modal
- Real-time API integration with FastAPI backend

## Documentation

See full documentation in the root README.md and PHASE2_AND_3_COMPLETE.md

## API Connection

The frontend connects to: `http://localhost:8000` (configurable via `.env`)

Make sure the FastAPI backend is running before starting the frontend.

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...

      // Remove tseslint.configs.recommended and replace with this
      tseslint.configs.recommendedTypeChecked,
      // Alternatively, use this for stricter rules
      tseslint.configs.strictTypeChecked,
      // Optionally, add this for stylistic rules
      tseslint.configs.stylisticTypeChecked,

      // Other configs...
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```

You can also install [eslint-plugin-react-x](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x'
import reactDom from 'eslint-plugin-react-dom'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...
      // Enable lint rules for React
      reactX.configs['recommended-typescript'],
      // Enable lint rules for React DOM
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```
