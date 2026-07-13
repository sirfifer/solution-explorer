// Frontend entry point for the multi-repo fixture.

export interface Config {
  apiUrl: string;
}

export function start(config: Config): void {
  console.log(`starting against ${config.apiUrl}`);
}
