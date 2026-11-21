export {};

/**
 * Runtime bridge exposed by the desktop shell's preload script.
 *
 * It is absent when the client runs in a normal browser, and every use must
 * degrade to the same-origin development server in that case.
 */
declare global {
  interface Window {
    docurebuild?: {
      apiToken?: string;
      platform: "desktop";
      version: string;
    };
  }
}
