/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_PLATEGAUGE_TEST_MODEL?: string;
  readonly VITE_SOURCE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
